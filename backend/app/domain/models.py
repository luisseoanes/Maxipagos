from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Boolean, Text
from sqlalchemy.orm import relationship
from app.infrastructure.database import Base
import datetime

class User(Base):
    __tablename__ = "users"
    id = Column(Integer, primary_key=True, index=True)
    username = Column(String, unique=True, index=True)
    hashed_password = Column(String)
    role = Column(String, default="admin") # 'admin', 'investor', or 'client'

class Investor(Base):
    __tablename__ = "investors"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    phone = Column(String)
    email = Column(String)
    balance = Column(Float, default=0.0)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    loans = relationship("Loan", back_populates="investor")

class Client(Base):
    __tablename__ = "clients"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    cedula = Column(String, unique=True, index=True)
    phone = Column(String)
    email = Column(String)
    address = Column(String)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    
    loans = relationship("Loan", back_populates="client")

class Loan(Base):
    __tablename__ = "loans"
    id = Column(Integer, primary_key=True, index=True)
    client_id = Column(Integer, ForeignKey("clients.id"))
    investor_id = Column(Integer, ForeignKey("investors.id"), nullable=True)
    amount = Column(Float)
    interest_rate = Column(Float)
    duration_months = Column(Integer)
    interest_type = Column(String, default="fixed") # 'fixed' or 'reducing'
    late_fee_per_day = Column(Float, default=0.0)
    start_date = Column(DateTime, default=datetime.datetime.utcnow)
    status = Column(String, default="active") # 'active', 'paid', 'late'
    
    client = relationship("Client", back_populates="loans")
    investor = relationship("Investor", back_populates="loans")
    quotas = relationship("Quota", back_populates="loan", cascade="all, delete-orphan")
    attachments = relationship("Attachment", back_populates="loan", cascade="all, delete-orphan")
    payments = relationship("Payment", back_populates="loan", cascade="all, delete-orphan")

class Quota(Base):
    __tablename__ = "quotas"
    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"))
    number = Column(Integer)
    amount = Column(Float)
    principal = Column(Float, default=0.0)
    interest = Column(Float, default=0.0)
    due_date = Column(DateTime)
    paid_amount = Column(Float, default=0.0)
    status = Column(String, default="pending")
    
    loan = relationship("Loan", back_populates="quotas")

class Attachment(Base):
    __tablename__ = "attachments"
    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"))
    filename = Column(String)
    label = Column(String)
    
    loan = relationship("Loan", back_populates="attachments")

class AuditLog(Base):
    __tablename__ = "audit_logs"
    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"))
    action = Column(String)
    details = Column(String)
    timestamp = Column(DateTime, default=datetime.datetime.utcnow)

class Payment(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    loan_id = Column(Integer, ForeignKey("loans.id"))
    quota_id = Column(Integer, ForeignKey("quotas.id"), nullable=True)
    amount = Column(Float)
    principal_paid = Column(Float, default=0.0)
    interest_paid = Column(Float, default=0.0)
    payment_date = Column(DateTime, default=datetime.datetime.utcnow)
    
    loan = relationship("Loan", back_populates="payments")

class Expense(Base):
    __tablename__ = "expenses"
    id = Column(Integer, primary_key=True, index=True)
    description = Column(String)
    amount = Column(Float)
    date = Column(DateTime, default=datetime.datetime.utcnow)
