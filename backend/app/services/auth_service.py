"""
Authentication & Authorization Domain Service.
Handles Keycloak JWT token parsing, role verification, and local email OTP authentication.
"""

import hashlib
import secrets
from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import HTTPException
import httpx
from jose import jwt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from backend.app.core.config import settings
from backend.app.models.auth import AccessRoleModel, EmailOTPModel
from backend.app.schemas.auth import UserProfileResponse

SUPER_ADMIN_PERMISSIONS = ["upload", "review", "pipeline", "search", "admin", "manage_users", "approve_ingestion", "delete_own"]
ADMIN_PERMISSIONS = ["upload", "review", "pipeline", "search", "delete_own"]


class AuthService:
    @staticmethod
    async def user_from_access_token(token: str) -> UserProfileResponse:
        try:
            async with httpx.AsyncClient(timeout=15) as client:
                jwks_response = await client.get(settings.KEYCLOAK_JWKS_URL)
                jwks_response.raise_for_status()
                jwks = jwks_response.json().get("keys", [])
            header = jwt.get_unverified_header(token)
            key = next((item for item in jwks if item.get("kid") == header.get("kid")), None)
            if not key:
                raise HTTPException(401, "Unable to validate access token.")
            claims = jwt.decode(
                token,
                key,
                algorithms=["RS256"],
                issuer=settings.KEYCLOAK_ISSUER,
                options={"verify_aud": bool(settings.KEYCLOAK_AUDIENCE)},
                audience=settings.KEYCLOAK_AUDIENCE or None,
            )
        except HTTPException:
            raise
        except (httpx.HTTPError, ValueError, jwt.JWTError) as exc:
            raise HTTPException(401, "Unable to validate access token.") from exc

        realm_roles = claims.get("realm_access", {}).get("roles", [])
        client_roles = []
        for client in (claims.get("resource_access") or {}).values():
            if isinstance(client, dict):
                client_roles.extend(client.get("roles", []))
        groups = claims.get("groups", [])
        roles = sorted(set(realm_roles + client_roles + (["super_admin"] if "/global/super-admin" in groups else [])))
        if "super-admin" in roles and "super_admin" not in roles:
            roles.append("super_admin")
        permissions = set()
        for role in roles:
            permissions.update(SUPER_ADMIN_PERMISSIONS if role == "super_admin" else ADMIN_PERMISSIONS if role == "admin" else ["search"] if role.startswith("default-roles-") else [])
        return UserProfileResponse(
            user_id=claims.get("sub", ""),
            username=claims.get("preferred_username") or claims.get("email", ""),
            email=claims.get("email"),
            first_name=claims.get("given_name"),
            last_name=claims.get("family_name"),
            roles=roles,
            permissions=sorted(permissions or {"search"}),
            groups=groups,
            is_super_admin="super_admin" in roles or "super-admin" in roles,
        )

    @staticmethod
    def _keycloak_token_url() -> str:
        return settings.KEYCLOAK_TOKEN_URL or (
            f"{settings.KEYCLOAK_ISSUER.rstrip('/')}/protocol/openid-connect/token"
        )

    @staticmethod
    async def _keycloak_token_request(
        form: dict[str, str],
        invalid_grant_message: str = "That sign-in link has already been used or expired. Try again.",
    ) -> dict:
        try:
            async with httpx.AsyncClient(timeout=30) as client:
                response = await client.post(AuthService._keycloak_token_url(), data=form)
                payload = response.json()
        except (httpx.HTTPError, ValueError) as exc:
            raise HTTPException(502, "Unable to contact Keycloak token endpoint.") from exc

        if response.status_code == 200 and payload.get("access_token"):
            return payload
        if payload.get("error") in {"invalid_client", "unauthorized_client"}:
            raise HTTPException(503, "SSO is misconfigured. Check the Keycloak UI client credentials.")
        if payload.get("error") == "invalid_grant":
            raise HTTPException(401, invalid_grant_message)
        raise HTTPException(
            response.status_code if response.status_code < 500 else 502,
            payload.get("error_description", "Could not complete Keycloak authentication."),
        )

    @staticmethod
    async def exchange_sso_code(code: str, redirect_uri: str, code_verifier: Optional[str]) -> dict:
        if not code.strip():
            raise HTTPException(400, "Missing authorization code.")
        if not redirect_uri.strip():
            raise HTTPException(400, "Missing redirect_uri.")
        form = {
            "grant_type": "authorization_code",
            "client_id": settings.KEYCLOAK_OTP_CLIENT_ID,
            "client_secret": settings.KEYCLOAK_CLIENT_SECRET or "",
            "code": code,
            "redirect_uri": redirect_uri,
        }
        if code_verifier:
            form["code_verifier"] = code_verifier
        return await AuthService._keycloak_token_request(form)

    @staticmethod
    async def login_with_password(username: str, password: str) -> dict:
        """Direct access grant. Requires 'Direct access grants' on the Keycloak client."""
        if not username.strip():
            raise HTTPException(400, "Missing username.")
        if not password:
            raise HTTPException(400, "Missing password.")
        return await AuthService._keycloak_token_request(
            {
                "grant_type": "password",
                "client_id": settings.KEYCLOAK_OTP_CLIENT_ID,
                "client_secret": settings.KEYCLOAK_CLIENT_SECRET or "",
                "username": username.strip(),
                "password": password,
                "scope": "openid",
            },
            invalid_grant_message="Incorrect username or password.",
        )

    @staticmethod
    async def refresh_session(refresh_token: str) -> dict:
        if not refresh_token.strip():
            raise HTTPException(400, "Missing refresh token.")
        return await AuthService._keycloak_token_request(
            {
                "grant_type": "refresh_token",
                "client_id": settings.KEYCLOAK_OTP_CLIENT_ID,
                "client_secret": settings.KEYCLOAK_CLIENT_SECRET or "",
                "refresh_token": refresh_token,
            }
        )

    @staticmethod
    def hash_otp_code(code: str) -> str:
        return hashlib.sha256(code.encode("utf-8")).hexdigest()

    @staticmethod
    async def create_email_otp(session: AsyncSession, email: str) -> str:
        code = "".join([str(secrets.randbelow(10)) for _ in range(6)])
        code_hash = AuthService.hash_otp_code(code)
        now = datetime.now(timezone.utc)
        expires_at = now + timedelta(minutes=10)

        stmt = select(EmailOTPModel).where(EmailOTPModel.email == email)
        res = await session.execute(stmt)
        otp = res.scalar_one_or_none()

        if otp:
            otp.code_hash = code_hash
            otp.expires_at = expires_at
            otp.attempts = 0
            otp.last_sent_at = now
        else:
            otp = EmailOTPModel(
                email=email,
                code_hash=code_hash,
                expires_at=expires_at,
                attempts=0,
                created_at=now,
                last_sent_at=now,
            )
            session.add(otp)

        await session.commit()
        return code

    @staticmethod
    async def verify_email_otp(session: AsyncSession, email: str, code: str) -> bool:
        stmt = select(EmailOTPModel).where(EmailOTPModel.email == email)
        res = await session.execute(stmt)
        otp = res.scalar_one_or_none()
        if not otp:
            return False

        now = datetime.now(timezone.utc)
        if otp.expires_at < now or otp.attempts >= 5:
            return False

        if otp.code_hash == AuthService.hash_otp_code(code):
            await session.delete(otp)
            await session.commit()
            return True

        otp.attempts += 1
        await session.commit()
        return False

    @staticmethod
    async def list_roles(session: AsyncSession) -> List[AccessRoleModel]:
        stmt = select(AccessRoleModel).order_by(AccessRoleModel.name.asc())
        res = await session.execute(stmt)
        return list(res.scalars().all())
