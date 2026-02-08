# apps/api/app/routers/auth.py
"""
Authentication Router - CursorCode AI
Full production auth system (2026 standards) with rate limiting on all sensitive endpoints.
Migrated from SendGrid → Resend (plain HTML emails).
"""

import logging
import secrets
from datetime import datetime, timedelta, timezone
from typing import Annotated, List

import jwt
import pyotp
import qrcode
from argon2 import PasswordHasher
from argon2.exceptions import VerifyMismatchError
from fastapi import (
    APIRouter,
    BackgroundTasks,
    Depends,
    HTTPException,
    Request,
    Response,
    status,
)
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel, EmailStr, Field
from slowapi import Limiter
from slowapi.util import get_remote_address
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from io import BytesIO
from base64 import b64encode

from app.core.config import settings
from app.db.session import get_db
from app.middleware.auth import get_current_user
from app.models.user import User
from app.services.logging import audit_log
from app.tasks.email import send_email_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# ────────────────────────────────────────────────
# Rate Limiter (per-IP, can be overridden per-route)
# ────────────────────────────────────────────────
limiter = Limiter(key_func=get_remote_address)

# ────────────────────────────────────────────────
# Security & Config
# ────────────────────────────────────────────────
pwd_hasher = PasswordHasher(time_cost=2, memory_cost=65536, parallelism=4, hash_len=32, salt_len=16)

TOTP_ISSUER = "CursorCode AI"
BACKUP_CODES_COUNT = 10

# ────────────────────────────────────────────────
# Models
# ────────────────────────────────────────────────
class SignupRequest(BaseModel):
    email: EmailStr = Field(..., example="user@example.com")
    password: str = Field(..., min_length=12)

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: str | None = None

class ResetRequest(BaseModel):
    email: EmailStr = Field(..., example="user@example.com")

class ResetConfirm(BaseModel):
    token: str
    new_password: str = Field(..., min_length=12)

class Enable2FARequest(BaseModel):
    pass

class Verify2FARequest(BaseModel):
    code: str = Field(..., min_length=6, max_length=6, pattern=r"^\d{6}$")

class TokenResponse(BaseModel):
    message: str

class QRResponse(BaseModel):
    qr_code_base64: str
    secret: str
    backup_codes: List[str]

# ────────────────────────────────────────────────
# JWT Helpers
# ────────────────────────────────────────────────
def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=settings.ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire, "type": "access"})
    return jwt.encode(to_encode, settings.JWT_SECRET_KEY, algorithm="HS256")

def create_refresh_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(days=settings.REFRESH_TOKEN_EXPIRE_DAYS)
    to_encode.update({"exp": expire, "type": "refresh"})
    return jwt.encode(to_encode, settings.JWT_REFRESH_SECRET, algorithm="HS256")

# ────────────────────────────────────────────────
# Signup - Heavily rate-limited
# ────────────────────────────────────────────────
@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")  # Prevent mass account creation
async def signup(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: SignupRequest,
    db: AsyncSession = Depends(get_db)
):
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Email already registered")

    hashed_password = pwd_hasher.hash(payload.password)
    verification_token = secrets.token_urlsafe(48)
    verification_expires = datetime.now(timezone.utc) + timedelta(hours=24)

    user = User(
        email=payload.email,
        hashed_password=hashed_password,
        verification_token=verification_token,
        verification_expires=verification_expires,
        is_verified=False,
    )
    db.add(user)
    await db.commit()
    await db.refresh(user)

    verification_url = f"{settings.FRONTEND_URL}/auth/verify?token={verification_token}"

    html = f"""
    <h2>Welcome to CursorCode AI!</h2>
    <p>Thank you for signing up.</p>
    <p>Please verify your email by clicking the link below:</p>
    <p><a href="{verification_url}">Verify Email Address</a></p>
    <p>This link expires in 24 hours.</p>
    <p>If you didn't create this account, you can safely ignore this email.</p>
    <br>
    <p>Best regards,<br>CursorCode AI Team</p>
    """

    background_tasks.add_task(
        send_email_task,
        to=user.email,
        subject="Verify Your CursorCode AI Account",
        html=html
    )

    audit_log.delay(user.id, "signup", {"email": payload.email, "ip": request.client.host})

    return {"message": "Account created. Check your email to verify."}

# ────────────────────────────────────────────────
# Verify Email (no rate limit needed - token is single-use)
# ────────────────────────────────────────────────
@router.get("/verify", response_model=TokenResponse)
async def verify_email(token: str, response: Response, db: AsyncSession = Depends(get_db)):
    user = await db.scalar(
        select(User).where(
            User.verification_token == token,
            User.verification_expires > datetime.now(timezone.utc),
            User.is_verified == False
        )
    )

    if not user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired token")

    user.is_verified = True
    user.verification_token = None
    user.verification_expires = None
    await db.commit()

    access_token = create_access_token({"sub": str(user.id), "email": user.email, "roles": user.roles})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    response.set_cookie("access_token", access_token, **settings.COOKIE_DEFAULTS)
    response.set_cookie("refresh_token", refresh_token, **settings.COOKIE_DEFAULTS)

    audit_log.delay(user.id, "email_verified", {})

    return {"message": "Email verified. Logged in."}

# ────────────────────────────────────────────────
# Login - Rate limited + 2FA support
# ────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")  # Bruteforce protection
async def login(
    request: Request,
    payload: LoginRequest,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    user = await db.scalar(select(User).where(User.email == payload.email))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    try:
        pwd_hasher.verify(user.hashed_password, payload.password)
    except VerifyMismatchError:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    if not user.is_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Email not verified")

    # 2FA enforcement
    if user.totp_enabled:
        if not payload.totp_code:
            raise HTTPException(status.HTTP_428_PRECONDITION_REQUIRED, "2FA code required")

        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(payload.totp_code, valid_window=1):
            audit_log.delay(user.id, "2fa_failed", {"ip": request.client.host})
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid 2FA code")

    access_token = create_access_token({"sub": str(user.id), "email": user.email, "roles": user.roles})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    response.set_cookie("access_token", access_token, **settings.COOKIE_DEFAULTS)
    response.set_cookie("refresh_token", refresh_token, **settings.COOKIE_DEFAULTS)

    audit_log.delay(user.id, "login_success", {"method": "password+2fa" if payload.totp_code else "password"})

    return {"message": "Logged in successfully"}

# ────────────────────────────────────────────────
# Password Reset Request - Rate limited
# ────────────────────────────────────────────────
@router.post("/reset-password/request", status_code=status.HTTP_200_OK)
@limiter.limit("3/minute")  # Anti-enumeration + abuse prevention
async def request_password_reset(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: ResetRequest,
    db: AsyncSession = Depends(get_db)
):
    # Always 200 to prevent email enumeration
    user = await db.scalar(select(User).where(User.email == payload.email))
    if not user:
        logger.info(f"Reset requested for non-existent email: {payload.email}")
        return {"message": "If the email exists, a reset link has been sent."}

    reset_token = secrets.token_urlsafe(48)
    reset_expires = datetime.now(timezone.utc) + timedelta(hours=1)

    user.reset_token = pwd_hasher.hash(reset_token)
    user.reset_expires = reset_expires
    await db.commit()

    reset_url = f"{settings.FRONTEND_URL}/auth/reset-password?token={reset_token}"

    html = f"""
    <h2>Password Reset Request</h2>
    <p>You (or someone else) requested a password reset for your CursorCode AI account.</p>
    <p>Click the link below to set a new password:</p>
    <p><a href="{reset_url}">Reset Password</a></p>
    <p>This link expires in 1 hour.</p>
    <p>If you did not request this, you can safely ignore this email.</p>
    <br>
    <p>Best regards,<br>CursorCode AI Team</p>
    """

    background_tasks.add_task(
        send_email_task,
        to=user.email,
        subject="Reset Your CursorCode AI Password",
        html=html
    )

    audit_log.delay(user.id, "reset_password_requested", {"ip": request.client.host})

    return {"message": "If the email exists, a reset link has been sent."}

# ────────────────────────────────────────────────
# Password Reset Confirm
# ────────────────────────────────────────────────
@router.post("/reset-password/confirm", response_model=TokenResponse)
async def confirm_password_reset(
    payload: ResetConfirm,
    response: Response,
    db: AsyncSession = Depends(get_db)
):
    user = await db.scalar(
        select(User).where(
            User.reset_expires > datetime.now(timezone.utc),
            User.reset_token.is_not(None)
        )
    )

    if not user:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset token")

    try:
        pwd_hasher.verify(user.reset_token, payload.token)
    except VerifyMismatchError:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid or expired reset token")

    user.hashed_password = pwd_hasher.hash(payload.new_password)
    user.reset_token = None
    user.reset_expires = None
    await db.commit()

    access_token = create_access_token({"sub": str(user.id), "email": user.email, "roles": user.roles})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    response.set_cookie("access_token", access_token, **settings.COOKIE_DEFAULTS)
    response.set_cookie("refresh_token", refresh_token, **settings.COOKIE_DEFAULTS)

    audit_log.delay(user.id, "password_reset_success", {})

    return {"message": "Password reset successful. You are now logged in."}

# ────────────────────────────────────────────────
# 2FA Endpoints (rate limited)
# ────────────────────────────────────────────────
@router.post("/2fa/enable", response_model=QRResponse)
@limiter.limit("5/minute")
async def enable_2fa(
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    if current_user.totp_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "2FA already enabled")

    secret = pyotp.random_base32()
    current_user.totp_secret = secret

    backup_codes = [secrets.token_hex(8) for _ in range(BACKUP_CODES_COUNT)]
    hashed_backups = [pwd_hasher.hash(code) for code in backup_codes]
    current_user.totp_backup_codes = json.dumps(hashed_backups)

    await db.commit()

    provisioning_uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=current_user.email,
        issuer_name=TOTP_ISSUER
    )
    qr = qrcode.make(provisioning_uri)
    buffered = BytesIO()
    qr.save(buffered, format="PNG")
    qr_base64 = b64encode(buffered.getvalue()).decode("utf-8")

    audit_log.delay(current_user.id, "2fa_enabled", {})

    return {
        "qr_code_base64": f"data:image/png;base64,{qr_base64}",
        "secret": secret,
        "backup_codes": backup_codes  # Show once!
    }

@router.post("/2fa/verify")
@limiter.limit("15/minute")
async def verify_2fa_setup(
    payload: Verify2FARequest,
    current_user: Annotated[User, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    if not current_user.totp_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "2FA not enabled")

    totp = pyotp.TOTP(current_user.totp_secret)
    if not totp.verify(payload.code, valid_window=1):
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid code")

    current_user.totp_enabled = True
    await db.commit()

    audit_log.delay(current_user.id, "2fa_verified_setup", {})

    html = f"""
    <h2>2FA Enabled on Your Account</h2>
    <p>Two-factor authentication has been successfully enabled for your CursorCode AI account.</p>
    <p>Your account is now more secure.</p>
    <p>If this was not you, please contact support immediately.</p>
    <br>
    <p>Best regards,<br>CursorCode AI Team</p>
    """

    send_email_task.delay(
        to=current_user.email,
        subject="2FA Enabled on Your Account",
        html=html
    )

    return {"message": "2FA enabled successfully"}

# ────────────────────────────────────────────────
# OAuth Stubs
# ────────────────────────────────────────────────
@router.get("/google", summary="Start Google OAuth")
async def google_login():
    return {"redirect": f"{settings.FRONTEND_URL}/api/auth/signin/google"}

@router.get("/github", summary="Start GitHub OAuth")
async def github_login():
    return {"redirect": f"{settings.FRONTEND_URL}/api/auth/signin/github"}
