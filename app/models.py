import datetime
from hashlib import md5
from abc import abstractmethod
from werkzeug.security import generate_password_hash
from werkzeug.security import check_password_hash
from flask_login import UserMixin
from flask_sqlalchemy import BaseQuery

from app import db

class LastMonthQuery(BaseQuery):
  def last_month(self, user_id):
    now, result = datetime.datetime.now(), []
    for item in self.filter_by(user_id=user_id).all():
      delta = now - item.creation_time
      if delta.days < 30:
        result.append(item)
    return result

class TimeModel(db.Model):
  __abstract__ = True
  query_class = LastMonthQuery

  @property
  @abstractmethod
  def creation_time(self):
    """Returns the creation date."""

class Session(TimeModel):
  __tablename__ = 'sessions'

  id = db.Column(db.Integer, primary_key=True)
  words = db.Column(db.Integer)
  chars = db.Column(db.Integer)
  accuracy = db.Column(db.Float)
  created_date = db.Column(db.DateTime, default=datetime.datetime.utcnow)
  user_id = db.Column(db.Integer, db.ForeignKey('users.id'))

  @property
  def creation_time(self):
    return self.created_date

  def __repr__(self):
    return '<Session {!r}>'.format(self.words)


class User(db.Model, UserMixin):
  __tablename__ = 'users'

  id = db.Column(db.Integer, primary_key=True)
  social_id = db.Column(db.String(128), unique=True)
  email = db.Column(db.String(64), unique=True, index=True)
  username = db.Column(db.String(64), unique=True, index=True)
  password_hash = db.Column(db.String(128))

  @property
  def password(self):
    raise AttributeError('password is not readable')

  @password.setter
  def password(self, password):
    self.password_hash = generate_password_hash(password)

  def avatar(self, size):
    digest = md5(self.email.lower().encode('utf-8')).hexdigest()
    return 'https://www.gravatar.com/avatar/{}?d=identicon&s={}'.format(digest, size)

  def verify_password(self, password):
    # if the user signed up with a provider, deny
    if not self.password_hash:
      return False
    return check_password_hash(self.password_hash, password)

  def __repr__(self):
    return '<User {!r}>'.format(self.username)
