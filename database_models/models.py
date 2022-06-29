import enum
import json

from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy import Column, String, Integer, Boolean, Float, ForeignKey, BigInteger, DateTime, func, Enum

Base = declarative_base()


class Band(Base):
    __tablename__ = 'band'
    id = Column(Integer, primary_key=True, autoincrement=True)
    name = Column(String)
    location = Column(String)
    longitude = Column(Float)
    latitude = Column(Float)


class User(Base):
    __tablename__ = 'user'
    id = Column(Integer, primary_key=True, autoincrement=True)
    first_name = Column(String)
    last_name = Column(String)
    email = Column(String)
    password_hash = Column(String(60))
    location = Column(String)
    longitude = Column(Float)
    latitude = Column(Float)
    email_verified = Column(Boolean, default=False)
    email_notifications_opt_in = Column(Boolean, default=False)


class EmailVerification(Base):
    __tablename__ = "email_verification"
    user_id = Column(Integer, ForeignKey("user.id"), primary_key=True)
    code = Column(String(8))


class BandMember(Base):
    __tablename__ = 'band_member'
    band_id = Column(Integer, ForeignKey("band.id"), primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"), primary_key=True)
    admin = Column(Boolean, default=False)


class BandInvite(Base):
    __tablename__ = "band_invite"
    band_id = Column(Integer, ForeignKey("band.id"), primary_key=True)
    user_id = Column(Integer, ForeignKey("user.id"), primary_key=True, nullable=True)
    code = Column(String(8), primary_key=True)
    # 30 days
    expiration = Column(BigInteger, default=func.now()+30*24*60*60)


class NotificationPriority(enum.Enum):
    high = 3
    normal = 2
    low = 1


class DBNotification(Base):
    __tablename__ = "notification"
    id = Column(Integer, primary_key=True, autoincrement=True)
    recipient_user_id = Column(Integer, ForeignKey("user.id"), nullable=True)
    message = Column(String, nullable=False)
    read = Column(Boolean, nullable=False, default=False)
    date_sent = Column(BigInteger, nullable=False)
    priority = Column(Enum(NotificationPriority), nullable=False)
    expiration = Column(BigInteger)

class LookingForBand(Base):
    __tablename__ = "looking_for_band"
    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    talent = Column(String, nullable=False)

class LookingForMember(Base):
    __tablename__ = "looking_for_member"
    id = Column(Integer, primary_key=True, autoincrement=True)
    band_id = Column(Integer, ForeignKey("band.id"), nullable=False)
    talent = Column(String, nullable=False)


class LocationCache(Base):
    __tablename__ = "location_cache"
    id = Column(Integer, primary_key=True, autoincrement=True)
    lng = Column(Float, nullable=False)
    lat = Column(Float, nullable=False)
    location = Column(String, nullable=False)

class BandInviteByEmail(Base):
    __tablename__ = "band_invite_by_email"
    id = Column(Integer, primary_key=True, autoincrement=True)
    email = Column(String, nullable=False)
    band_id = Column(Integer, ForeignKey("band.id"), nullable=False)
    expiration = Column(BigInteger)


class DBMessage(Base):
    __tablename__ = "message"
    id = Column(Integer, primary_key=True, autoincrement=True)
    sender_user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    recipient_user_id = Column(Integer, ForeignKey("user.id"), nullable=False)
    message = Column(String, nullable=False)
    sent = Column(BigInteger, nullable=False, default=func.now())
    read = Column(BigInteger, nullable=False, default=False)

    def json(self):
        return {
            "sender_user_id": self.sender_user_id,
            "recipient_user_id": self.recipient_user_id,
            "message": self.message,
            "date_sent": self.sent,
            "read": self.read
        }