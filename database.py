import os
from sqlalchemy import (
    create_engine,
    Column,
    Integer,
    BigInteger,
    String,
    Float,
    DateTime,
    Boolean
)
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime


Base = declarative_base()


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)

    # Telegram ID может быть больше 2.1 млрд
    telegram_id = Column(BigInteger, unique=True, nullable=False)

    username = Column(String)
    balance = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.now)
    is_admin = Column(Boolean, default=False)


class Category(Base):
    __tablename__ = 'categories'

    id = Column(Integer, primary_key=True)
    name = Column(String, nullable=False)
    emoji = Column(String)
    price = Column(Float, nullable=False)
    created_at = Column(DateTime, default=datetime.now)


class Account(Base):
    __tablename__ = 'accounts'

    id = Column(Integer, primary_key=True)
    category_id = Column(Integer, nullable=False)
    phone = Column(String, unique=True, nullable=False)
    available = Column(Boolean, default=True)

    # Telegram ID владельца
    sold_to = Column(BigInteger)

    created_at = Column(DateTime, default=datetime.now)


class UserAccount(Base):
    __tablename__ = 'user_accounts'

    id = Column(Integer, primary_key=True)

    # Telegram ID пользователя
    user_id = Column(BigInteger, nullable=False)

    account_id = Column(Integer, nullable=False)
    purchased_at = Column(DateTime, default=datetime.now)


class Transaction(Base):
    __tablename__ = 'transactions'

    id = Column(Integer, primary_key=True)

    # Telegram ID пользователя
    user_id = Column(BigInteger, nullable=False)

    type = Column(String)
    amount = Column(Float, nullable=False)
    status = Column(String, default='completed')
    created_at = Column(DateTime, default=datetime.now)


DATABASE_URL = os.getenv('DATABASE_URL')

if not DATABASE_URL:
    raise ValueError("DATABASE_URL not set!")


engine = create_engine(
    DATABASE_URL,
    pool_pre_ping=True
)

SessionLocal = sessionmaker(
    bind=engine,
    expire_on_commit=False
)


def init_db():
    Base.metadata.create_all(engine)


def get_session() -> Session:
    return SessionLocal()


init_db()
