# -*- coding: future_fstrings -*-
import collections
import datetime
from flask_jwt_extended import (create_access_token, create_refresh_token)
from flask import current_app
from app.database import (TimeModelMixin, Model,
    relationship, Column, db, SurrogatePK)
from abc import abstractmethod, ABCMeta
from six import add_metaclass
from hashlib import md5
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash


USER_ONLINE_TIMEOUT = 300


@add_metaclass(ABCMeta)
class Statistics(object):
  def __init__(self, user):
    self.user = user

  @abstractmethod
  def _generate_stat(self, field_getter):
    """Return max statistics for a specified category
     within a specified period of time."""

  @property
  def words(self):
    return self._generate_stat(
      field_getter=lambda s: s.words
    )

  @property
  def accuracy(self):
    return self._generate_stat(
      field_getter=lambda s: s.accuracy
    )

  @property
  def chars(self):
    return self._generate_stat(
      field_getter=lambda s: s.chars
    )

  @property
  def scores(self):
    format = lambda data: [
        dict(zip(('time', 'value'), (t, v)))
          for t, v in data.items()
      ]
    return ScoresModel(
      words=format(self.words),
      chars=format(self.chars),
      accuracy=format(self.accuracy)
    )

  def __repr__(self):
    name = self.__class__.__name__
    words = f'words: {self.words}'
    chars = f'chars: {self.chars}'
    accuracy = f'accuracy: {self.accuracy}'
    return f'<{name} \n {words} \n {chars} \n {accuracy}>'


class DailyStats(Statistics):
  def _generate_stat(self, field_getter):
    def _format_time(time):
      if time < 10:
        return f'0{time}'
      return time
    sessions, result = Session.query.today(self.user.id), {}
    for session in sessions:
      time = session.created_date
      time = '{hours}:{minutes}'.format(
        hours=_format_time(time.hour),
        minutes=_format_time(time.minute)
      )
      result[time] = max(result.get(time, -1), field_getter(session))
    strptime = datetime.datetime.strptime
    result = sorted(result.items(),
      key=lambda x: strptime(x[0],'%H:%M').time())
    return result


class WeeklyStats(Statistics):
  def _generate_stat(self, field_getter):
    sessions, result = Session.query.last_week(self.user.id), {}
    for session in sessions:
      day = session.created_date.day
      result[day] = max(result.get(day, -1), field_getter(session))
    return result.items()


class MonthlyStats(Statistics):
  def _generate_stat(self, field_getter):
    sessions, result = Session.query.last_month(self.user.id), {}
    for session in sessions:
      day = session.created_date.day
      result[day] = max(result.get(day, -1), field_getter(session))
    return result.items()


class UserStatisticsModel(object):
  __slots__ = ('daily', 'weekly', 'monthly',)

  def __init__(self, daily, weekly, monthly):
    self.daily = daily
    self.weekly = weekly
    self.monthly = monthly


class User(Model, SurrogatePK):
  __tablename__ = 'users'

  social_id = Column(db.String(128), unique=True)
  email = Column(db.String(64), unique=True, index=True)
  username = Column(db.String(64), unique=True, index=True)
  password_hash = Column(db.String(128))
  last_seen = Column(db.DateTime, default=datetime.datetime.utcnow)
  sessions = relationship('Session', backref='user', lazy='dynamic')

  @property
  def password(self):
    raise AttributeError('Password is not readable')

  @property
  def is_online(self):
    if self.last_seen:
      now = datetime.datetime.now()
      delta = datetime.timedelta(seconds=USER_ONLINE_TIMEOUT)
      return (now - self.last_seen) < delta
    return False

  @password.setter
  def password(self, password):
    self.password_hash = generate_password_hash(password)

  def _get_average(self, getter):
    if self.sessions.count() != 0:
      return sum(
        getter(s) for s in self.sessions
      ) / self.sessions.count()
    return 0

  @property
  def total_sessions(self):
    return self.sessions.count()

  @property
  def scores(self):
    return ScoresModel(
      words=self.words,
      chars=self.chars,
      accuracy=self.accuracy
    )

  @property
  def words(self):
    return self._get_average(
      getter=lambda x: x.words
    )

  @property
  def accuracy(self):
    score = round(self._get_average(
      getter=lambda x: x.accuracy
    ))
    return int(score)

  @property
  def chars(self):
    return self._get_average(
      getter=lambda x: x.chars
    )

  @property
  def statistics(self):
    if not hasattr(self, '_stats'):
      daily = DailyStats(self)
      monthly = MonthlyStats(self)
      weekly = WeeklyStats(self)
      self._stats = UserStatisticsModel(
        daily=daily,
        weekly=weekly,
        monthly=monthly
      )
    return self._stats

  def avatar(self, size):
    digest = md5(self.email.lower().encode('utf-8')).hexdigest()
    return f'https://www.gravatar.com/avatar/{digest}?d=identicon&s={size}'

  def verify_password(self, password):
    # if the user signed up with a provider, deny
    if not self.password_hash:
      return False
    return check_password_hash(self.password_hash, password)

  def __repr__(self):
    return f'<User {self.username}>'


class TokenizedUser(object):
  __slots__ = ('user', 'auth', )

  def __init__(self, user, auth):
    self.user = user
    self.auth = auth


class PaginationModel(object):
  __slots__ = ('data', 'total_pages',
            'total_results', 'page', )

  def __init__(self, data, page, total_pages, total_results):
    self.data = data
    self.page = page
    self.total_pages = total_pages
    self.total_results = total_results


class ScoresModel(object):
  __slots__ = ('words', 'chars', 'accuracy',)

  def __init__(self, words, chars, accuracy):
    self.words = words
    self.chars = chars
    self.accuracy = accuracy


class Session(TimeModelMixin, SurrogatePK):
  __tablename__ = 'sessions'

  words = Column(db.Integer, default=0)
  chars = Column(db.Integer, default=0)
  accuracy = Column(db.Float, default=0.0)
  created_date = Column(db.DateTime, default=datetime.datetime.utcnow)
  user_id = Column(db.Integer, db.ForeignKey('users.id'))

  @property
  def creation_time(self):
    return self.created_date

  @property
  def scores(self):
    return ScoresModel(
      words=self.words,
      chars=self.chars,
      accuracy=self.accuracy
    )

  def __repr__(self):
    return f'<Session {self.words}>'


class AuthModel(object):
  __slots__ = ('access_token', 'refresh_token', 'expires_at')

  def __init__(self, access_token, refresh_token, expires_at):
    self.access_token = access_token
    self.refresh_token = refresh_token
    self.expires_at = expires_at

  @classmethod
  def create(cls, identity):
    kwargs, config = {}, current_app.config
    kwargs['access_token']= create_access_token(identity=identity)
    kwargs['refresh_token'] = create_refresh_token(identity=identity)
    kwargs['expires_at'] = datetime.datetime.utcnow() + config['JWT_ACCESS_TOKEN_EXPIRES']
    return cls(**kwargs)
