import os
from sqlalchemy import create_engine, Column, Integer, BigInteger, String, Float, DateTime, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime

Base = declarative_base()


class User(Base):
    __tablename__ = 'users'

    id = Column(Integer, primary_key=True)
    telegram_id = Column(BigInteger, unique=True, nullable=False)
    username = Column(String)
    balance = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.now)
    is_admin = Column(Boolean, default=False)


class Account(Base):
    __tablename__ = 'accounts'

    id = Column(Integer, primary_key=True)
    phone = Column(String, unique=True, nullable=False)
    name = Column(String, nullable=False)
    price = Column(Float, nullable=False)
    owner_id = Column(Integer)
    sold = Column(Boolean, default=False)
    sold_at = Column(DateTime)
    sold_to = Column(Integer)
    created_at = Column(DateTime, default=datetime.now)


class TelethonSession(Base):
    __tablename__ = 'telethon_sessions'

    id = Column(Integer, primary_key=True)
    phone = Column(String, unique=True, nullable=False)
    session_string = Column(String, nullable=False)
    created_at = Column(DateTime, default=datetime.now)


class Transaction(Base):
    __tablename__ = 'transactions'

    id = Column(Integer, primary_key=True)
    user_id = Column(Integer, nullable=False)
    account_id = Column(Integer, nullable=False)
    amount = Column(Float, nullable=False)
    status = Column(String, default='pending')
    created_at = Column(DateTime, default=datetime.now)


DATABASE_URL = os.getenv(
    'DATABASE_URL',
    'postgresql://localhost/shopdb'
)

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
