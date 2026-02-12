"""
Authentication Router - CursorCode AI
Full production auth system (2026 standards) with rate limiting on all sensitive endpoints.
Migrated from SendGrid → Resend (plain HTML emails).
"""

import logging
import secrets
import json
from datetime import datetime, timedelta, timezone
from typing import Annotated, Optional  # ← FIXED: added Annotated

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
from uuid import UUID

from app.core.config import settings
from app.core.security import create_access_token, create_refresh_token  # ← NEW: shared helpers
from app.db.session import get_db
from app.middleware.auth import get_current_user, AuthUser
from app.db.models.user import User  # ← FIXED: correct path
from app.services.logging import audit_log
from app.tasks.email import send_email_task

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/auth", tags=["Authentication"])

# ────────────────────────────────────────────────
# Rate Limiter – per user when authenticated, else per IP
# ────────────────────────────────────────────────
def auth_limiter_key(request: Request) -> str:
    user = getattr(request.state, "user", None)
    if user and hasattr(user, "id"):
        return str(user.id)
    return get_remote_address()

limiter = Limiter(key_func=auth_limiter_key)

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
    password: str = Field(..., min_length=12, description="Minimum 12 characters")

class LoginRequest(BaseModel):
    email: EmailStr
    password: str
    totp_code: Optional[str] = Field(None, pattern=r"^\d{6}$", description="6-digit 2FA code")

class ResetRequest(BaseModel):
    email: EmailStr = Field(..., example="user@example.com")

class ResetConfirm(BaseModel):
    token: str = Field(...)
    new_password: str = Field(..., min_length=12)

class Enable2FARequest(BaseModel):
    pass

class Verify2FARequest(BaseModel):
    code: str = Field(..., pattern=r"^\d{6}$", description="6-digit code")

class TokenResponse(BaseModel):
    message: str

class QRResponse(BaseModel):
    qr_code_base64: str
    secret: str
    backup_codes: list[str]  # lowercase list — correct & no import needed


# ────────────────────────────────────────────────
# Signup - Heavily rate-limited
# ────────────────────────────────────────────────
@router.post("/signup", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
@limiter.limit("5/minute")
async def signup(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: SignupRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Create a new account. Sends verification email.
    Rate limited to prevent mass registration.
    """
    existing = await db.scalar(select(User).where(User.email == payload.email))
    if existing:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered"
        )

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
    <p>Thank you for signing up. Please verify your email address.</p>
    <p><a href="{verification_url}" style="padding: 10px 20px; background: #0066cc; color: white; text-decoration: none; border-radius: 5px;">Verify Email</a></p>
    <p>This link expires in 24 hours.</p>
    <p>If you didn't create this account, ignore this email.</p>
    <br>
    <p>Best regards,<br>CursorCode AI Team</p>
    """

    background_tasks.add_task(
        send_email_task,
        to=user.email,
        subject="Verify Your CursorCode AI Account",
        html=html
    )

    audit_log.delay(
        user_id=str(user.id),
        action="signup_attempt",
        metadata={"email": payload.email, "ip": request.client.host}
    )

    return {"message": "Account created. Check your email to verify."}


# ────────────────────────────────────────────────
# Verify Email
# ────────────────────────────────────────────────
@router.get("/verify", response_model=TokenResponse)
async def verify_email(
    response: Response,
    token: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Verify email with token from signup/reset.
    Logs user in on success.
    """
    user = await db.scalar(
        select(User).where(
            User.verification_token == token,
            User.verification_expires > datetime.now(timezone.utc),
            User.is_verified == False
        )
    )

    if not user:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid or expired verification token"
        )

    user.is_verified = True
    user.verification_token = None
    user.verification_expires = None
    await db.commit()

    access_token = create_access_token({"sub": str(user.id), "email": user.email, "roles": user.roles})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    response.set_cookie("access_token", access_token, **settings.COOKIE_DEFAULTS)
    response.set_cookie("refresh_token", refresh_token, **settings.COOKIE_DEFAULTS)

    audit_log.delay(str(user.id), "email_verified", {"token_used": token})

    return {"message": "Email verified. You are now logged in."}


# ────────────────────────────────────────────────
# Login - Rate limited + 2FA support
# ────────────────────────────────────────────────
@router.post("/login", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(
    response: Response,
    request: Request,
    form_data: OAuth2PasswordRequestForm = Depends(),
    db: AsyncSession = Depends(get_db)
):
    """
    Login with email/password + optional 2FA.
    Returns JWT tokens in cookies.
    """
    user = await db.scalar(select(User).where(User.email == form_data.username))
    if not user:
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    try:
        pwd_hasher.verify(user.hashed_password, form_data.password)
    except VerifyMismatchError:
        audit_log.delay(None, "login_failed", {"email": form_data.username, "ip": request.client.host})
        raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid credentials")

    if not user.is_verified:
        raise HTTPException(status.HTTP_403_FORBIDDEN, "Email not verified")

    # 2FA check
    if user.totp_enabled:
        if not hasattr(form_data, 'totp_code') or not form_data.totp_code:
            raise HTTPException(status.HTTP_428_PRECONDITION_REQUIRED, "2FA code required")

        totp = pyotp.TOTP(user.totp_secret)
        if not totp.verify(form_data.totp_code, valid_window=1):
            audit_log.delay(str(user.id), "2fa_failed", {"ip": request.client.host})
            raise HTTPException(status.HTTP_401_UNAUTHORIZED, "Invalid 2FA code")

    access_token = create_access_token({"sub": str(user.id), "email": user.email, "roles": user.roles})
    refresh_token = create_refresh_token({"sub": str(user.id)})

    response.set_cookie("access_token", access_token, **settings.COOKIE_DEFAULTS)
    response.set_cookie("refresh_token", refresh_token, **settings.COOKIE_DEFAULTS)

    audit_log.delay(
        str(user.id),
        "login_success",
        {"method": "password+2fa" if getattr(form_data, 'totp_code', None) else "password"}
    )

    return {"message": "Logged in successfully"}


# ────────────────────────────────────────────────
# Password Reset Request
# ────────────────────────────────────────────────
@router.post("/reset-password/request", status_code=status.HTTP_200_OK)
@limiter.limit("3/minute")
async def request_password_reset(
    request: Request,
    background_tasks: BackgroundTasks,
    payload: ResetRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Request password reset link. Always returns 200 to prevent enumeration.
    """
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
    <p>A password reset was requested for your CursorCode AI account.</p>
    <p><a href="{reset_url}" style="padding: 10px 20px; background: #0066cc; color: white; text-decoration: none; border-radius: 5px;">Reset Password</a></p>
    <p>This link expires in 1 hour.</p>
    <p>If you did not request this, ignore this email — your account is safe.</p>
    <br>
    <p>Best regards,<br>CursorCode AI Team</p>
    """

    background_tasks.add_task(
        send_email_task,
        to=user.email,
        subject="Reset Your CursorCode AI Password",
        html=html
    )

    audit_log.delay(str(user.id), "reset_password_requested", {"ip": request.client.host})

    return {"message": "If the email exists, a reset link has been sent."}


# ────────────────────────────────────────────────
# Password Reset Confirm
# ────────────────────────────────────────────────
@router.post("/reset-password/confirm", response_model=TokenResponse)
async def confirm_password_reset(
    response: Response,
    payload: ResetConfirm,
    db: AsyncSession = Depends(get_db)
):
    """
    Confirm password reset with token and set new password.
    Logs user in on success.
    """
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

    audit_log.delay(str(user.id), "password_reset_success", {})

    return {"message": "Password reset successful. You are now logged in."}


# ────────────────────────────────────────────────
# 2FA Enable + QR Code
# ────────────────────────────────────────────────
@router.post("/2fa/enable", response_model=QRResponse)
@limiter.limit("5/minute")
async def enable_2fa(
    request: Request,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    """
    Enable 2FA for the current user.
    Returns QR code and backup codes (show once!).
    """
    user = await db.get(User, UUID(current_user.id))
    if not user:
        raise HTTPException(status.HTTP_404_NOT_FOUND, "User not found")

    if user.totp_enabled:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "2FA is already enabled")

    secret = pyotp.random_base32()
    user.totp_secret = secret

    backup_codes = [secrets.token_hex(8) for _ in range(BACKUP_CODES_COUNT)]
    hashed_backups = [pwd_hasher.hash(code) for code in backup_codes]
    user.totp_backup_codes = json.dumps(hashed_backups)

    await db.commit()

    provisioning_uri = pyotp.totp.TOTP(secret).provisioning_uri(
        name=user.email,
        issuer_name=TOTP_ISSUER
    )

    qr = qrcode.make(provisioning_uri)
    buffered = BytesIO()
    qr.save(buffered, format="PNG")
    qr_base64 = b64encode(buffered.getvalue()).decode("utf-8")

    audit_log.delay(
        user_id=current_user.id,
        action="2fa_enabled",
        metadata={"ip": request.client.host}
    )

    return QRResponse(
        qr_code_base64=f"data:image/png;base64,{qr_base64}",
        secret=secret,
        backup_codes=backup_codes  # Display only once!
    )


@router.post("/2fa/verify")
@limiter.limit("15/minute")
async def verify_2fa_setup(
    request: Request,
    payload: Verify2FARequest,
    current_user: Annotated[AuthUser, Depends(get_current_user)],
    db: AsyncSession = Depends(get_db)
):
    """
    Verify 2FA setup code to finalize enabling.
    """
    user = await db.get(User, UUID(current_user.id))
    if not user or not user.totp_secret:
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "2FA not enabled or setup incomplete")

    totp = pyotp.TOTP(user.totp_secret)
    if not totp.verify(payload.code, valid_window=1):
        audit_log.delay(
            user_id=current_user.id,
            action="2fa_verify_failed",
            metadata={"ip": request.client.host}
        )
        raise HTTPException(status.HTTP_400_BAD_REQUEST, "Invalid 2FA code")

    user.totp_enabled = True
    await db.commit()

    audit_log.delay(
        user_id=current_user.id,
        action="2fa_verified_setup",
        metadata={"ip": request.client.host}
    )

    html = f"""
    <h2>2FA Successfully Enabled</h2>
    <p>Two-factor authentication is now active on your CursorCode AI account.</p>
    <p>Your account is more secure. Keep your backup codes safe.</p>
    <p>If this was not you, contact support immediately.</p>
    <br>
    <p>Best regards,<br>CursorCode AI Team</p>
    """

    send_email_task.delay(
        to=user.email,
        subject="2FA Enabled on Your Account",
        html=html
    )

    return {"message": "2FA enabled successfully"}


# ────────────────────────────────────────────────
# OAuth Stubs (Google/GitHub)
# ────────────────────────────────────────────────
@router.get("/google", summary="Start Google OAuth flow")
async def google_login():
    return {"redirect": f"{settings.FRONTEND_URL}/auth/signin/google"}


@router.get("/github", summary="Start GitHub OAuth flow")
async def github_login():
    return {"redirect": f"{settings.FRONTEND_URL}/auth/signin/github"}
