from fastapi import FastAPI, Depends, HTTPException, status, Form, Request, UploadFile, File
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates
from fastapi.responses import RedirectResponse, StreamingResponse
from sqlalchemy.orm import Session
from starlette.middleware.sessions import SessionMiddleware
from fastapi.middleware.cors import CORSMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded
import os
import pathlib
import shutil
from datetime import datetime, timedelta
from fpdf import FPDF
from io import BytesIO
from dotenv import load_dotenv

# Resolve absolute paths so it works from any working directory (Railway, local, etc.)
BACKEND_DIR = pathlib.Path(__file__).resolve().parent
PROJECT_DIR = BACKEND_DIR.parent

import sys
sys.path.insert(0, str(BACKEND_DIR))

from app.infrastructure import database
from app.domain import models
from app.schemas import schemas
from app.core import security

load_dotenv(dotenv_path=BACKEND_DIR / ".env")

# Create database tables
models.Base.metadata.create_all(bind=database.engine)

limiter = Limiter(key_func=get_remote_address)
app = FastAPI()
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

# CORS Configuration
origins = ["*"]
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Session middleware
app.add_middleware(
    SessionMiddleware, 
    secret_key=os.getenv("SECRET_KEY", "dev_secret_key_123"),
    session_cookie="maxipagos_session",
    max_age=3600 * 12,
    same_site="lax",
    https_only=False
)

# Directories setup (absolute paths)
UPLOADS_DIR = PROJECT_DIR / "uploads"
os.makedirs(str(UPLOADS_DIR), exist_ok=True)
app.mount("/static", StaticFiles(directory=str(PROJECT_DIR / "frontend" / "static")), name="static")
templates = Jinja2Templates(directory=str(PROJECT_DIR / "frontend" / "templates"))

def log_action(db: Session, user_id: int, action: str, details: str):
    db.add(models.AuditLog(user_id=user_id, action=action, details=details))
    db.commit()

# --- ROUTES ---

@app.get("/")
async def index(request: Request):
    if request.session.get("user_id"):
        return RedirectResponse(url="/admin")
    return templates.TemplateResponse("index.html", {"request": request})

@app.get("/admin")
async def admin_page(request: Request):
    if not request.session.get("user_id"):
        return RedirectResponse(url="/")
    return templates.TemplateResponse("admin.html", {"request": request})

@app.post("/login")
@limiter.limit("5/minute")
async def login(request: Request, username: str = Form(...), password: str = Form(...), db: Session = Depends(database.get_db)):
    user = db.query(models.User).filter(models.User.username == username).first()
    if not user or not security.verify_password(password, user.hashed_password):
        return templates.TemplateResponse("index.html", {"request": request, "error": "Credenciales inválidas"})
    
    request.session["user_id"] = user.id
    request.session["username"] = user.username
    request.session["role"] = user.role
    return RedirectResponse(url="/admin", status_code=status.HTTP_303_SEE_OTHER)

@app.get("/logout")
async def logout(request: Request):
    request.session.clear()
    return RedirectResponse(url="/")

# --- API ENDPOINTS ---

@app.get("/api/dashboard-stats")
async def get_stats(request: Request, db: Session = Depends(database.get_db)):
    user_id = request.session.get("user_id")
    role = request.session.get("role")
    if not user_id: raise HTTPException(status_code=401)
    
    if role == "client":
        client = db.query(models.Client).filter(models.Client.user_id == user_id).first()
        if not client: return {"total_loans": 0, "total_paid": 0, "total_pending": 0}
        
        loans = client.loans
        total_loans = len(loans)
        total_paid = sum(p.amount for l in loans for p in l.payments)
        total_pending = sum(q.amount - q.paid_amount for l in loans for q in l.quotas if q.status != "paid")
        
        return {
            "role": "client",
            "total_loans": total_loans,
            "total_paid": total_paid,
            "total_pending": total_pending,
            "client_name": client.name
        }
    
    # Existing Admin/Investor stats logic
    total_clients = db.query(models.Client).count()
    query_loans = db.query(models.Loan)
    if role == "investor":
        investor = db.query(models.Investor).filter(models.Investor.user_id == user_id).first()
        if investor:
            query_loans = query_loans.filter(models.Loan.investor_id == investor.id)
    
    active_loans = query_loans.filter(models.Loan.status == "active").all()
    total_lent = sum(l.amount for l in active_loans)
    
    today = datetime.utcnow()
    pending_quotas = db.query(models.Quota).filter(models.Quota.status != "paid", models.Quota.due_date < today)
    total_mora = 0
    if role == "investor":
        investor = db.query(models.Investor).filter(models.Investor.user_id == user_id).first()
        if investor:
            pending_quotas = pending_quotas.join(models.Loan).filter(models.Loan.investor_id == investor.id)
            total_mora = sum(q.amount - q.paid_amount for q in pending_quotas.all())
    else:
        total_mora = sum(q.amount - q.paid_amount for q in pending_quotas.all())
    
    if role == "admin":
        expenses = db.query(models.Expense).all()
        total_expenses = sum(e.amount for e in expenses)
        total_interest_earned = sum(p.interest_paid for p in db.query(models.Payment).all())
        net_profit = total_interest_earned - total_expenses
    else:
        # Investor profit is based on their loans
        investor = db.query(models.Investor).filter(models.Investor.user_id == user_id).first()
        total_expenses = 0
        net_profit = sum(p.interest_paid for l in investor.loans for p in l.payments) if investor else 0

    projections = []
    curr_date = today.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    profitability_trend = []
    
    for i in range(6):
        month_end = (curr_date + timedelta(days=32)).replace(day=1)
        
        # Projections
        p_query = db.query(models.Quota).filter(models.Quota.due_date >= curr_date, models.Quota.due_date < month_end)
        if role == "investor":
            investor = db.query(models.Investor).filter(models.Investor.user_id == user_id).first()
            if investor:
                p_query = p_query.join(models.Loan).filter(models.Loan.investor_id == investor.id)
        month_total = sum(q.amount for q in p_query.all())
        projections.append({"month": curr_date.strftime("%b"), "amount": month_total})
        
        # Historical Profitability (Past 6 months)
        hist_start = curr_date - timedelta(days=180) # This is a bit complex for a simple loop, let's simplify
        
        curr_date = month_end

    # Real profitability (Past 6 months trend)
    for i in range(5, -1, -1):
        m_start = (today.replace(day=1) - timedelta(days=30*i)).replace(day=1, hour=0, minute=0)
        m_end = (m_start + timedelta(days=32)).replace(day=1)
        
        inc = sum(p.interest_paid for p in db.query(models.Payment).filter(models.Payment.payment_date >= m_start, models.Payment.payment_date < m_end).all())
        exp = sum(e.amount for e in db.query(models.Expense).filter(models.Expense.date >= m_start, models.Expense.date < m_end).all())
        profitability_trend.append({"month": m_start.strftime("%b"), "income": inc, "expenses": exp})
        
    return {
        "role": role,
        "total_clients": total_clients, "total_lent": total_lent, "total_mora": total_mora,
        "net_profit": net_profit, "total_expenses": total_expenses, 
        "projections": projections,
        "profitability_trend": profitability_trend
    }

@app.get("/api/clients")
async def get_clients(request: Request, db: Session = Depends(database.get_db)):
    if not request.session.get("user_id"): raise HTTPException(status_code=401)
    return db.query(models.Client).all()

@app.get("/consultar")
async def consultar_page(request: Request):
    return templates.TemplateResponse("consultar.html", {"request": request})

@app.get("/api/public/consultar/{cedula}")
async def public_consult(cedula: str, db: Session = Depends(database.get_db)):
    client = db.query(models.Client).filter(models.Client.cedula == cedula).first()
    if not client: raise HTTPException(status_code=404, detail="Cédula no encontrada")
    
    loans = []
    for l in client.loans:
        total_paid = sum(p.amount for p in l.payments)
        total_principal = sum(p.principal_paid for p in l.payments)
        total_interest = sum(p.interest_paid for p in l.payments)
        
        loans.append({
            "id": l.id, 
            "amount": l.amount, 
            "status": l.status,
            "total_paid": total_paid,
            "total_principal": total_principal,
            "total_interest": total_interest,
            "quotas": [{"number": q.number, "amount": q.amount, "due": q.due_date.strftime("%Y-%m-%d"), "status": q.status, "paid": q.paid_amount} for q in l.quotas]
        })
    return {"name": client.name, "loans": loans}

@app.post("/api/clients")
@limiter.limit("10/minute")
async def create_client(request: Request, client: schemas.ClientCreate, db: Session = Depends(database.get_db)):
    admin_id = request.session.get("user_id")
    if not admin_id or request.session.get("role") != "admin": raise HTTPException(status_code=401)
    
    db_user = None
    if client.username and client.password:
        db_user = models.User(username=client.username, hashed_password=security.get_password_hash(client.password), role="client")
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
    db_client = models.Client(
        name=client.name, cedula=client.cedula, phone=client.phone, email=client.email, address=client.address,
        user_id=db_user.id if db_user else None
    )
    db.add(db_client)
    db.commit()
    db.refresh(db_client)
    log_action(db, admin_id, "CREATE_CLIENT", f"Cliente creado: {client.name} (ID: {client.cedula})")
    return db_client

@app.get("/api/investors")
async def get_investors(request: Request, db: Session = Depends(database.get_db)):
    if not request.session.get("user_id"): raise HTTPException(status_code=401)
    return db.query(models.Investor).all()

@app.post("/api/investors")
async def create_investor(request: Request, investor: schemas.InvestorCreate, db: Session = Depends(database.get_db)):
    admin_id = request.session.get("user_id")
    if not admin_id or request.session.get("role") != "admin": raise HTTPException(status_code=401)
    
    db_user = None
    if investor.username and investor.password:
        db_user = models.User(username=investor.username, hashed_password=security.get_password_hash(investor.password), role="investor")
        db.add(db_user)
        db.commit()
        db.refresh(db_user)
        
    db_investor = models.Investor(
        name=investor.name, phone=investor.phone, email=investor.email, 
        balance=investor.balance, user_id=db_user.id if db_user else None
    )
    db.add(db_investor)
    db.commit()
    db.refresh(db_investor)
    log_action(db, admin_id, "CREATE_INVESTOR", f"Inversionista creado: {investor.name}")
    return db_investor

@app.get("/api/investors/{id}/history")
async def get_investor_history(id: int, request: Request, db: Session = Depends(database.get_db)):
    if not request.session.get("user_id"): raise HTTPException(status_code=401)
    investor = db.query(models.Investor).filter(models.Investor.id == id).first()
    if not investor: raise HTTPException(status_code=404)
    
    total_earnings = 0
    total_capital_lent = 0
    for l in investor.loans:
        total_capital_lent += l.amount
        for p in l.payments:
            total_earnings += p.interest_paid
            
    return {
        "name": investor.name,
        "balance": investor.balance,
        "total_earnings": total_earnings,
        "total_capital_lent": total_capital_lent,
        "loans": [{"id": l.id, "client": l.client.name, "amount": l.amount, "status": l.status} for l in investor.loans]
    }

@app.get("/api/loans")
async def get_loans(request: Request, db: Session = Depends(database.get_db)):
    if not request.session.get("user_id"): raise HTTPException(status_code=401)
    user_id = request.session.get("user_id")
    role = request.session.get("role")
    
    query = db.query(models.Loan)
    if role == "investor":
        investor = db.query(models.Investor).filter(models.Investor.user_id == user_id).first()
        if investor:
            query = query.filter(models.Loan.investor_id == investor.id)
    elif role == "client":
        client = db.query(models.Client).filter(models.Client.user_id == user_id).first()
        if client:
            query = query.filter(models.Loan.client_id == client.id)
    
    loans = query.all()
    results = []
    today = datetime.utcnow().date()
    for l in loans:
        is_late = False
        due_today = False
        for q in l.quotas:
            if q.status != "paid":
                q_date = q.due_date.date()
                if q_date < today: is_late = True
                if q_date == today: due_today = True
        
        results.append({
            "id": l.id, "client_name": l.client.name, "client_id": l.client_id, "amount": l.amount, "interest_rate": l.interest_rate, 
            "status": l.status, "start_date": l.start_date.strftime("%Y-%m-%d"), "investor": l.investor.name if l.investor else "Negocio",
            "is_late": is_late, "due_today": due_today
        })
    return results

@app.post("/api/loans")
@limiter.limit("5/minute")
async def create_loan(request: Request, loan: schemas.LoanCreate, db: Session = Depends(database.get_db)):
    user_id = request.session.get("user_id")
    if not user_id: raise HTTPException(status_code=401)
    
    db_loan = models.Loan(**loan.dict())
    db.add(db_loan)
    
    if loan.investor_id:
        investor = db.query(models.Investor).filter(models.Investor.id == loan.investor_id).first()
        if investor:
            if investor.balance < loan.amount:
                raise HTTPException(status_code=400, detail="El inversionista no tiene fondos suficientes.")
            investor.balance -= loan.amount
    
    db.commit()
    db.refresh(db_loan)
    
    # Amortization Logic
    if loan.interest_type == "fixed":
        total_interest = loan.amount * (loan.interest_rate / 100) * loan.duration_months
        total_to_pay = loan.amount + total_interest
        quota_amount = total_to_pay / loan.duration_months
        principal_per_quota = loan.amount / loan.duration_months
        interest_per_quota = total_interest / loan.duration_months
        
        for i in range(1, loan.duration_months + 1):
            db.add(models.Quota(
                loan_id=db_loan.id, number=i, amount=round(quota_amount, 2), 
                principal=round(principal_per_quota, 2), interest=round(interest_per_quota, 2),
                due_date=datetime.utcnow() + timedelta(days=30 * i)
            ))
    else: # Reducing
        monthly_rate = (loan.interest_rate / 100)
        p = loan.amount
        n = loan.duration_months
        quota_amount = (p * monthly_rate * (1 + monthly_rate)**n) / ((1 + monthly_rate)**n - 1) if monthly_rate > 0 else p / n
        remaining_balance = p
        for i in range(1, n + 1):
            interest_part = remaining_balance * monthly_rate
            principal_part = quota_amount - interest_part
            remaining_balance -= principal_part
            db.add(models.Quota(
                loan_id=db_loan.id, number=i, amount=round(quota_amount, 2), 
                principal=round(principal_part, 2), interest=round(interest_part, 2),
                due_date=datetime.utcnow() + timedelta(days=30 * i)
            ))

    db.commit()
    log_action(db, user_id, "CREATE_LOAN", f"Préstamo #{db_loan.id} creado")
    return db_loan

@app.get("/api/clients/{id}/history")
async def get_client_history(id: int, request: Request, db: Session = Depends(database.get_db)):
    if not request.session.get("user_id"): raise HTTPException(status_code=401)
    client = db.query(models.Client).filter(models.Client.id == id).first()
    if not client: raise HTTPException(status_code=404)
    
    loans = []
    for l in client.loans:
        loans.append({
            "id": l.id, "amount": l.amount, "status": l.status, "interest": l.interest_rate, "type": l.interest_type,
            "date": l.start_date.strftime("%Y-%m-%d"),
            "quotas": [{"id": q.id, "number": q.number, "amount": q.amount, "principal": q.principal, "interest": q.interest, "paid_amount": q.paid_amount, "due": q.due_date.strftime("%Y-%m-%d"), "status": q.status} for q in l.quotas],
            "attachments": [{"filename": a.filename, "label": a.label} for a in l.attachments],
            "payments": [{"id": p.id, "amount": p.amount, "principal_paid": p.principal_paid, "interest_paid": p.interest_paid, "date": p.payment_date.strftime("%Y-%m-%d %H:%M")} for p in l.payments],
            "late_fee_per_day": l.late_fee_per_day
        })
    return {"name": client.name, "loans": loans}

@app.put("/api/quotas/{id}")
async def update_quota(id: int, update: schemas.QuotaUpdate, request: Request, db: Session = Depends(database.get_db)):
    user_id = request.session.get("user_id")
    if not user_id: raise HTTPException(status_code=401)
    db_quota = db.query(models.Quota).filter(models.Quota.id == id).first()
    db_quota.amount = update.amount
    db_quota.due_date = update.due_date
    db.commit()
    log_action(db, user_id, "UPDATE_QUOTA", f"Cuota #{id} modificada")
    return db_quota

@app.post("/api/loans/{id}/attachments")
async def upload_attachment(id: int, request: Request, label: str = Form(...), file: UploadFile = File(...), db: Session = Depends(database.get_db)):
    user_id = request.session.get("user_id")
    if not user_id: raise HTTPException(status_code=401)
    file_path = str(UPLOADS_DIR / f"{id}_{file.filename}")
    with open(file_path, "wb") as buffer: shutil.copyfileobj(file.file, buffer)
    db_attachment = models.Attachment(loan_id=id, filename=f"{id}_{file.filename}", label=label)
    db.add(db_attachment)
    db.commit()
    log_action(db, user_id, "UPLOAD_FILE", f"Archivo {file.filename} subido")
    return {"status": "success"}

@app.get("/api/audit-logs")
async def get_logs(request: Request, db: Session = Depends(database.get_db)):
    if not request.session.get("user_id") or request.session.get("role") != "admin": raise HTTPException(status_code=403)
    logs = db.query(models.AuditLog).order_by(models.AuditLog.timestamp.desc()).limit(50).all()
    return [{"user": log.user_id, "action": log.action, "details": log.details, "time": log.timestamp.strftime("%Y-%m-%d %H:%M:%S")} for log in logs]

@app.post("/api/loans/{id}/payments")
async def register_payment(id: int, payment: schemas.PaymentCreate, request: Request, db: Session = Depends(database.get_db)):
    user_id = request.session.get("user_id")
    if not user_id: raise HTTPException(status_code=401)
    loan = db.query(models.Loan).filter(models.Loan.id == id).first()
    db_payment = models.Payment(loan_id=id, amount=payment.amount)
    db.add(db_payment)
    if loan.investor_id:
        investor = db.query(models.Investor).filter(models.Investor.id == loan.investor_id).first()
        if investor: investor.balance += payment.amount

    if payment.is_abono_capital:
        db_payment.principal_paid = payment.amount
        loan.amount -= payment.amount
        pending_quotas = db.query(models.Quota).filter(models.Quota.loan_id == id, models.Quota.status != "paid").all()
        if pending_quotas:
            red = payment.amount / len(pending_quotas)
            for q in pending_quotas: 
                q.amount = max(0, q.amount - red)
                q.principal = max(0, q.principal - red)
    else:
        pending_quotas = db.query(models.Quota).filter(models.Quota.loan_id == id, models.Quota.status != "paid").order_by(models.Quota.number).all()
        rem = payment.amount
        today = datetime.utcnow()
        for q in pending_quotas:
            if rem <= 0: break
            base_debt = q.amount - (q.paid_amount or 0)
            days_late = (today - q.due_date).days
            late_fee = (days_late * loan.late_fee_per_day) if (days_late > 0 and loan.late_fee_per_day) else 0
            total_debt = base_debt + late_fee
            pay_this = min(rem, total_debt)
            rem_p = pay_this
            fee_p = min(rem_p, late_fee)
            rem_p -= fee_p
            int_pend = max(0, q.interest - (q.paid_amount if q.paid_amount < q.interest else q.interest))
            int_p = min(rem_p, int_pend)
            db_payment.interest_paid += int_p
            rem_p -= int_p
            db_payment.principal_paid += rem_p
            if rem >= total_debt:
                rem -= total_debt
                q.paid_amount = q.amount
                q.status = "paid"
            else:
                q.paid_amount = (q.paid_amount or 0) + rem
                rem = 0
                q.status = "partial"
    
    if not db.query(models.Quota).filter(models.Quota.loan_id == id, models.Quota.status != "paid").first():
        loan.status = "paid"
    db.commit()
    return {"status": "success"}

@app.get("/api/payments/{id}/receipt")
async def generate_receipt(id: int, request: Request, db: Session = Depends(database.get_db)):
    if not request.session.get("user_id"): raise HTTPException(status_code=401)
    payment = db.query(models.Payment).filter(models.Payment.id == id).first()
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 16)
    pdf.cell(190, 10, "MaxiPagos - Recibo", ln=True, align='C')
    pdf.set_font("Arial", size=12)
    pdf.cell(50, 10, f"Cliente: {payment.loan.client.name}", ln=True)
    pdf.cell(50, 10, f"Monto: ${payment.amount:,.2f}", ln=True)
    # ... Simplified for PDF generation
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    return StreamingResponse(BytesIO(pdf_bytes), media_type="application/pdf")

@app.get("/api/expenses")
async def get_expenses(request: Request, db: Session = Depends(database.get_db)):
    if not request.session.get("user_id") or request.session.get("role") != "admin": raise HTTPException(status_code=403)
    return db.query(models.Expense).order_by(models.Expense.date.desc()).all()

@app.post("/api/expenses")
@limiter.limit("10/minute")
async def create_expense(expense: schemas.ExpenseCreate, request: Request, db: Session = Depends(database.get_db)):
    if not request.session.get("user_id") or request.session.get("role") != "admin": raise HTTPException(status_code=403)
    db_expense = models.Expense(**expense.dict())
    db.add(db_expense)
    db.commit()
    db.refresh(db_expense)
    return db_expense

@app.get("/api/loans/{id}/contract")
async def generate_contract(id: int, request: Request, db: Session = Depends(database.get_db)):
    if not request.session.get("user_id"): raise HTTPException(status_code=401)
    loan = db.query(models.Loan).filter(models.Loan.id == id).first()
    if not loan: raise HTTPException(status_code=404)
    
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", 'B', 20)
    pdf.cell(190, 15, "CONTRATO DE MUTUO ACUERDO", ln=True, align='C')
    pdf.ln(10)
    
    pdf.set_font("Arial", size=11)
    text = f"""En la ciudad de Bogotá, a los {loan.start_date.strftime('%d')} días del mes de {loan.start_date.strftime('%B')} del año {loan.start_date.strftime('%Y')}, se celebra el presente contrato entre:
    
    EL PRESTAMISTA: MAXIPAGOS S.A.S.
    EL PRESTATARIO: {loan.client.name.upper()}, identificado con Cédula No. {loan.client.cedula}.
    
    CLÁUSULAS:
    PRIMERA - OBJETO: El prestamista entrega en calidad de préstamo la suma de ${loan.amount:,.2f} COP.
    SEGUNDA - INTERESES: El prestatario se obliga a pagar un interés del {loan.interest_rate}% mensual, bajo la modalidad de {loan.interest_type}.
    TERCERA - PLAZO: El préstamo tendrá una duración de {loan.duration_months} meses, divididos en {len(loan.quotas)} cuotas.
    CUARTA - MORA: En caso de incumplimiento, se generará un recargo diario de ${loan.late_fee_per_day:,.2f} COP.
    QUINTA - COMPROMISO: El prestatario declara recibir el dinero a entera satisfacción y se compromete a pagarlo en las fechas pactadas.
    
    Para constancia de lo anterior, se firma el presente documento.
    """
    pdf.multi_cell(0, 8, text)
    pdf.ln(30)
    
    pdf.cell(95, 10, "__________________________", ln=0, align='C')
    pdf.cell(95, 10, "__________________________", ln=1, align='C')
    pdf.cell(95, 10, "EL PRESTAMISTA", ln=0, align='C')
    pdf.cell(95, 10, "EL PRESTATARIO", ln=1, align='C')
    
    pdf_bytes = pdf.output(dest='S').encode('latin1')
    return StreamingResponse(BytesIO(pdf_bytes), media_type="application/pdf", headers={"Content-Disposition": f"attachment; filename=Contrato_Prestamo_{id}.pdf"})

@app.get("/api/reports/export")
async def export_data(request: Request, db: Session = Depends(database.get_db)):
    if not request.session.get("user_id") or request.session.get("role") != "admin": raise HTTPException(status_code=403)
    import xlsxwriter
    output = BytesIO()
    workbook = xlsxwriter.Workbook(output)
    # ... Simplified for Excel generation
    workbook.close()
    output.seek(0)
    return StreamingResponse(output, media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

if __name__ == "__main__":
    import uvicorn
    uvicorn.run("main:app", host="0.0.0.0", port=8000, reload=True)
