from pydantic import BaseModel
from typing import List, Optional
from datetime import datetime

class UserBase(BaseModel):
    username: str
    role: str

class InvestorCreate(BaseModel):
    name: str
    phone: Optional[str] = None
    email: Optional[str] = None
    balance: float = 0.0
    username: Optional[str] = None
    password: Optional[str] = None

class ClientCreate(BaseModel):
    name: str
    cedula: str
    phone: Optional[str] = None
    email: Optional[str] = None
    address: Optional[str] = None
    username: Optional[str] = None
    password: Optional[str] = None

class LoanCreate(BaseModel):
    client_id: int
    investor_id: Optional[int] = None
    amount: float
    interest_rate: float
    duration_months: int
    interest_type: str = "fixed"
    late_fee_per_day: float = 0.0

class PaymentCreate(BaseModel):
    amount: float
    is_abono_capital: bool = False

class QuotaUpdate(BaseModel):
    amount: float
    due_date: datetime

class ExpenseCreate(BaseModel):
    description: str
    amount: float
