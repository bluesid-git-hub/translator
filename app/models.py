from flask.ext.sqlalchemy import SQLAlchemy
from flask.ext.login import UserMixin
from sqlalchemy.orm import relationship
from sqlalchemy.ext.declarative import DeclarativeMeta
from sqlalchemy.sql.expression import and_, or_
from sqlalchemy.dialects.postgresql import UUID
from sqlalchemy.schema import CreateTable
from datetime import datetime
from __init__ import app

import uuid
import base62

db = SQLAlchemy(app)

def serialize(obj):
    import json
    if isinstance(obj.__class__, DeclarativeMeta):
        # an SQLAlchemy class
        fields = {}
        for field in [x for x in dir(obj) if not x.startswith('_') and x != 'metadata']:
            data = obj.__getattribute__(field)
            try:
                json.dumps(data) # this will fail on non-encodable values, like other classes
                fields[field] = data
            except TypeError:
                fields[field] = None
        # a json-encodable dict
        return fields


class BaseModel:
    @property
    def id_b62(self):
        return base62.encode(uuid.UUID(self.id).int)

    def serialize(self):
        # Synthesized property
        #self.id_b62 = base62.encode(uuid.UUID(self.id).int)

        return serialize(self)

    @classmethod
    def insert(cls, commit=True, **kwargs):
        print type(cls), cls
        record = cls(id=str(uuid.uuid4()))
        record.timestamp = datetime.now()

        for key, value in kwargs.iteritems():
            setattr(record, key, value);

        db.session.add(record)
        if commit: db.session.commit()

        return record


class TranslationRequest(db.Model, BaseModel):
    __table_args__ = ( db.UniqueConstraint('source', 'target', 'original_text_hash'), )

    id = db.Column(UUID, primary_key=True)
    user_id = db.Column(UUID)
    timestamp = db.Column(db.DateTime(timezone=True))
    source = db.Column(db.String(16))
    target = db.Column(db.String(16))
    original_text = db.Column(db.Text)
    original_text_hash = db.Column(db.String(255))

    @staticmethod
    def fetch(id=None, id_b62=None, original_text_hash=None, source=None, target=None):
        if id != None:
            return TranslationRequest.query.get(id)

        elif id_b62 != None:
            translation_id = base62.decode(id_b62)
            return TranslationRequest.query.get(str(uuid.UUID(int=translation_id)))

        else:
            return TranslationRequest.query.filter_by(
                original_text_hash=original_text_hash,
                source=source, target=target).first()


class TranslationResponse(db.Model, BaseModel):
    __table_args__ = ( db.UniqueConstraint('user_id', 'source', 'target', 'mode', 'original_text_hash'), )

    id = db.Column(UUID, primary_key=True)
    request_id = db.Column(UUID, db.ForeignKey('translation_request.id'))
    user_id = db.Column(UUID, db.ForeignKey('user.id'))
    timestamp = db.Column(db.DateTime(timezone=True))
    source = db.Column(db.String(16))
    target = db.Column(db.String(16))
    # mode
    # 1: regular translation
    # 2: better translation (use Japanese as an intermediate langauge)
    # 3: human translation
    mode = db.Column(db.Integer)
    original_text_hash = db.Column(db.String(255))
    intermediate_text = db.Column(db.Text)
    translated_text = db.Column(db.Text)

    request = relationship('TranslationRequest')
    user = relationship('User')

    @staticmethod
    def fetch(id_b62=None, user_id=None, original_text_hash=None, source=None, target=None, mode=None):
        if id_b62 != None:
            translation_id = base62.decode(id_b62)
            return TranslationResponse.query.get(str(uuid.UUID(int=translation_id)))

        else:
            return TranslationResponse.query.filter_by(
                user_id=user_id, original_text_hash=original_text_hash,
                source=source, target=target, mode=mode).first()


class TranslationHelpRequest(db.Model, BaseModel):
    id = db.Column(UUID, primary_key=True)
    request_id = db.Column(UUID, db.ForeignKey('translation_request.id'))
    user_id = db.Column(UUID, db.ForeignKey('user.id'))
    timestamp = db.Column(db.DateTime(timezone=True))

    request = relationship('TranslationRequest')
    user = relationship('User')

class Translation(db.Model, BaseModel):
    """
    CREATE VIEW translation AS
        SELECT tres.id, treq.id AS request_id, tres.user_id,
            tres.timestamp, tres.source, tres.target, tres.mode,
            treq.original_text, tres.original_text_hash, tres.intermediate_text,
            tres.translated_text, coalesce(r.rating, 0) AS rating,
            coalesce(r.count, 0) AS count
        FROM translation_response AS tres
        LEFT JOIN translation_request AS treq ON
            tres.source = treq.source AND
            tres.target = treq.target AND
            tres.original_text_hash = treq.original_text_hash
        LEFT JOIN
            (SELECT translation_id, sum(rating) AS rating, count(id) AS count
            FROM rating GROUP BY translation_id) AS r ON
            r.translation_id = tres.id
    """
    id = db.Column(UUID, primary_key=True) # response_id
    request_id = db.Column(UUID)
    user_id = db.Column(UUID, db.ForeignKey('user.id'))
    timestamp = db.Column(db.DateTime(timezone=True))
    source = db.Column(db.String(16))
    target = db.Column(db.String(16))
    mode = db.Column(db.Integer)
    original_text = db.Column(db.Text)
    original_text_hash = db.Column(db.String(255))
    intermediate_text = db.Column(db.Text)
    translated_text = db.Column(db.Text)
    
    rating = db.Column(db.Integer)
    count = db.Column(db.Integer)

    user = relationship('User')

    @property
    def request_id_b62(self):
        return base62.encode(uuid.UUID(self.request_id).int)

    # FIXME: This may be a cause for degraded performance 
    @property
    def plus_ratings(self):
        return Rating.query.filter_by(translation_id=self.id, rating=1).count()

    # FIXME: This may be a cause for degraded performance 
    @property
    def minus_ratings(self):
        return Rating.query.filter_by(translation_id=self.id, rating=-1).count()

    @staticmethod
    def fetch(id_b62=None, original_text_hash=None, source=None, target=None, mode=None):
        if id_b62 != None:
            translation_id = base62.decode(id_b62)
            return Translation.query.get(str(uuid.UUID(int=translation_id)))

        else:
            return Translation.query.filter_by(
                original_text_hash=original_text_hash,
                source=source, target=target, mode=mode).first()


class TranslationPostLog(db.Model, BaseModel):
    id = db.Column(UUID, primary_key=True)
    request_id = db.Column(UUID)
    user_id = db.Column(UUID)
    timestamp = db.Column(db.DateTime(timezone=True))
    target = db.Column(db.String(32)) # facebook, twitter, etc.
    post_id = db.Column(db.String(128))


class TranslationAccessLog(db.Model, BaseModel):
    """
    flag
    0001: Created: This flag is on upon creation of a TranslationResponse record
    0002:
    0004:
    ...

    translation_access_log_translation_id_fkey  
    FOREIGN KEY (translation_id) REFERENCES translation_response(id)
    """

    FLAG_CREATED = 1
    
    id = db.Column(UUID, primary_key=True)
    translation_id = db.Column(UUID)
    user_id = db.Column(UUID)
    timestamp = db.Column(db.DateTime(timezone=True))
    user_agent = db.Column(db.String(255))
    remote_address = db.Column(db.String(64))
    flag = db.Column(db.Integer, default=0)


class Rating(db.Model):
    __table_args__ = ( db.UniqueConstraint('translation_id', 'user_id'), )

    id = db.Column(UUID, primary_key=True)
    translation_id = db.Column(UUID)
    user_id = db.Column(UUID)
    timestamp = db.Column(db.DateTime(timezone=True))
    rating = db.Column(db.Integer)

    # FIXME: This may be a cause for degraded performance 
    @property
    def plus_ratings(self):
        return Rating.query.filter_by(translation_id=self.translation_id, rating=1).count()

    # FIXME: This may be a cause for degraded performance 
    @property
    def minus_ratings(self):
        return Rating.query.filter_by(translation_id=self.translation_id, rating=-1).count()

    def serialize(self):
        r = serialize(self)
        r['plus_ratings'] = self.plus_ratings
        r['minus_ratings'] = self.minus_ratings

        return r


class User(db.Model, UserMixin, BaseModel):
    __table_args__ = ( db.UniqueConstraint('oauth_provider', 'oauth_id'), {} )

    id = db.Column(UUID, primary_key=True)

    oauth_provider = db.Column(db.String(255))
    oauth_id = db.Column(db.String(255), unique=True)
    oauth_username = db.Column(db.String(255))

    family_name = db.Column(db.String(255))
    given_name = db.Column(db.String(255))
    email = db.Column(db.String(255))

    gender = db.Column(db.String(6))
    locale = db.Column(db.String(16))

    @property
    def name(self):
        # FIXME: i18n
        return '{} {}'.format(self.given_name, self.family_name)

    @staticmethod
    def insert(**kwargs):
        user = User.query.filter_by(oauth_id=kwargs['oauth_id']).first()

        if user == None:
            user = User(id=str(uuid.uuid4()))
            #user.timestamp = datetime.now()

            for key, value in kwargs.iteritems():
                setattr(user, key, value);

            db.session.add(user)
            db.session.commit()

        return user


class GeoIP(db.Model):
    """The primary purpose of this table is to hold IP-geolocation pairs.
    The table name itself is pretty mucy self-explanatory."""

    __tablename__ = 'geoip'

    address = db.Column(db.String(40), primary_key=True) # We may hold IPv6 addresses as well
    timestamp = db.Column(db.DateTime(timezone=True))
    latitude = db.Column(db.Float)
    longitude = db.Column(db.Float)


#
# Generating SQL from declarative model definitions:
#
#     print CreateTable(User.__table__).compile(db.engine)
#

if __name__ == '__main__':
    tables = (User, TranslationRequest, TranslationResponse, Rating, )
    for table in tables:
        print '{};'.format(CreateTable(table.__table__).compile(db.engine))
    
    #db.create_all(tables=[TranslationRequest, TranslationResponse,])