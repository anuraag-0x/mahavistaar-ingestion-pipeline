"""
Pydantic Schemas for Auth, Users, Roles, and Email OTPs.
"""

from typing import List, Optional
from backend.app.schemas.common import BaseSchema


class UserProfileResponse(BaseSchema):
    user_id: str
    username: str
    email: Optional[str] = None
    first_name: Optional[str] = None
    last_name: Optional[str] = None
    roles: List[str] = []
    permissions: List[str] = []
    groups: List[str] = []
    is_super_admin: bool = False


class AccessRoleResponse(BaseSchema):
    name: str
    label: str
    description: str
    permissions: List[str]


class AccessRoleCreateRequest(BaseSchema):
    name: str
    label: str
    description: str = ""
    permissions: List[str] = []


class EmailOTPRequest(BaseSchema):
    email: str


class EmailOTPVerifyRequest(BaseSchema):
    email: str
    code: str


class PasswordLoginRequest(BaseSchema):
    username: str
    password: str


class SsoExchangeRequest(BaseSchema):
    code: str
    redirect_uri: str
    code_verifier: Optional[str] = None


class SessionRefreshRequest(BaseSchema):
    refresh_token: str


class TokenResponse(BaseSchema):
    access_token: str
    token_type: str = "bearer"
    expires_in: int = 3600
    refresh_token: Optional[str] = None
    refresh_expires_in: Optional[int] = None
    id_token: Optional[str] = None
    user: Optional[UserProfileResponse] = None
