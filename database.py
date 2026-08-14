import os
import asyncio
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, LargeBinary
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from datetime import datetime
from config import DATABASE_URL

Base = declarative_base()

class User(Base):
    __tablename__ = 'users'
    
    id = Column(Integer, primary_key=True)
    telegram_id = Column(Integer, unique=True)
    username = Column(String)
    balance = Column(Float, default=0.0)
    created_at = Column(DateTime, default=datetime.now)
    is_admin = Column(Boolean, default=False)

class Account(Base):
    __tablename__ = 'accounts'
    
    id = Column(Integer, primary_key=True)
    phone = Column(String, unique=True)
    name = Column(String)
    price = Column(Float)
    session_data = Column(LargeBinary)
    owner_id = Column(Integer)
    sold = Column(Boolean, default=False)
    sold_at = Column(DateTime, nullable=True)
    sold_to = Column(Integer, nullable=True)
    created_at = Column(DateTime, default=datetime.now)

class TelethonSession(Base):
    __tablename__ = 'telethon_sessions'
    
    id = Column(Integer, primary_key=True)
    phone = Column(String, unique=True)
    session_string = Column(String)
    created_at = Column(DateTime, default=datetime.now)

class Transaction(Base):
    __tablename__ = 'transactions'
    
    id = Column(Integer, primary_key=True)
    user_id = Column(Integer)
    account_id = Column(Integer)
    amount = Column(Float)
    status = Column(String)
    created_at = Column(DateTime, default=datetime.now)

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(bind=engine)

def init_db():
    Base.metadata.create_all(engine)

def get_session() -> Session:
    return SessionLocal()
