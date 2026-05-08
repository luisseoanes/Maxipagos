import bcrypt
from fastapi import Request, HTTPException, status
from typing import Optional

def verify_password(plain_password, hashed_password):
    return bcrypt.checkpw(plain_password.encode('utf-8'), hashed_password.encode('utf-8'))

def get_password_hash(password):
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')

# Simple session check (for local development)
async def get_current_user(request: Request):
    user_id = request.session.get("user_id")
    if not user_id:
        return None
    return user_id
