"""
Authentication & Authorization API Router.
Handles email OTP sending/verification and access role inspection.
"""

from typing import List
from fastapi import APIRouter, Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.database import get_db
from backend.app.schemas.auth import (
    AccessRoleResponse,
    EmailOTPRequest,
    EmailOTPVerifyRequest,
    PasswordLoginRequest,
    SessionRefreshRequest,
    SsoExchangeRequest,
    TokenResponse,
    UserProfileResponse,
)
from backend.app.schemas.common import StandardResponse
from backend.app.services.auth_service import AuthService

router = APIRouter(prefix="/auth", tags=["Auth"])
bearer_scheme = HTTPBearer(auto_error=False)


@router.post("/otp/send", response_model=StandardResponse)
async def send_otp(request: EmailOTPRequest, db: AsyncSession = Depends(get_db)):
    code = await AuthService.create_email_otp(db, request.email)
    # In production, send email via SMTP; in dev, return or log
    return StandardResponse(success=True, message=f"OTP sent to {request.email}")


@router.post("/otp/verify", response_model=TokenResponse)
async def verify_otp(request: EmailOTPVerifyRequest, db: AsyncSession = Depends(get_db)):
    valid = await AuthService.verify_email_otp(db, request.email, request.code)
    if not valid:
        raise HTTPException(status_code=400, detail="Invalid or expired OTP code")
    return TokenResponse(
        access_token="dev-otp-access-token",
        token_type="bearer",
        expires_in=3600,
    )


@router.post("/login", response_model=TokenResponse)
async def login_with_password(request: PasswordLoginRequest):
    return await AuthService.login_with_password(request.username, request.password)


@router.post("/sso/exchange", response_model=TokenResponse)
async def exchange_sso_code(request: SsoExchangeRequest):
    return await AuthService.exchange_sso_code(request.code, request.redirect_uri, request.code_verifier)


@router.post("/session/refresh", response_model=TokenResponse)
async def refresh_session(request: SessionRefreshRequest):
    return await AuthService.refresh_session(request.refresh_token)


@router.get("/me", response_model=UserProfileResponse)
async def current_user(credentials: HTTPAuthorizationCredentials | None = Depends(bearer_scheme)):
    if not credentials:
        raise HTTPException(401, "Authentication required.")
    return await AuthService.user_from_access_token(credentials.credentials)


@router.get("/roles", response_model=List[AccessRoleResponse])
async def list_roles(db: AsyncSession = Depends(get_db)):
    roles = await AuthService.list_roles(db)
    return [AccessRoleResponse.model_validate(r) for r in roles]
