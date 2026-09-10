"""Small native Keycloak Admin API client for local user and role management."""

from typing import Any
import httpx
import json
import re
import time
from fastapi import HTTPException
from backend.app.core.config import settings

ROLE_DATA = {
    "admin": {"label": "Admin", "description": "Workspace administration", "permissions": ["search", "upload", "review", "pipeline", "manage_users"]},
    "super_admin": {"label": "Super Admin", "description": "Full local workspace administration", "permissions": ["search", "upload", "review", "pipeline", "manage_users", "admin"]},
}

# Roles Keycloak creates for every realm. They carry no application meaning and
# would otherwise show up beside the workspace roles.
KEYCLOAK_BUILT_IN_ROLES = {"offline_access", "uma_authorization"}

# Keycloak accepts almost anything as a role name. This is deliberately narrow:
# the name is what the API checks permissions against and what appears in a
# token, so it stays lowercase and free of characters that need escaping.
ROLE_NAME = re.compile(r"^[a-z][a-z0-9_]{1,62}$")

# Label and permissions have nowhere to live in a Keycloak realm role beyond its
# attributes, so that is where they are kept. It avoids a second store that
# could disagree with Keycloak about which roles exist.
LABEL_ATTRIBUTE = "workspace_label"
PERMISSIONS_ATTRIBUTE = "workspace_permissions"


def _base() -> str:
    return settings.KEYCLOAK_ADMIN_BASE_URL.rstrip("/")


_cached_token = ""
_cached_token_expires_at = 0.0


def _token(force: bool = False) -> str:
    global _cached_token, _cached_token_expires_at
    if not force and _cached_token and time.time() < _cached_token_expires_at:
        return _cached_token
    if not settings.KEYCLOAK_ADMIN_PASSWORD:
        raise HTTPException(503, "Keycloak admin credentials are not configured")
    response = httpx.post(
        f"{_base()}/realms/{settings.KEYCLOAK_ADMIN_TOKEN_REALM}/protocol/openid-connect/token",
        data={"grant_type": "password", "client_id": "admin-cli", "username": settings.KEYCLOAK_ADMIN_USERNAME, "password": settings.KEYCLOAK_ADMIN_PASSWORD},
        timeout=20,
    )
    if response.status_code != 200:
        reason = response.json().get("error_description", "Keycloak admin authentication failed")
        raise HTTPException(503, f"Keycloak admin login failed for user '{settings.KEYCLOAK_ADMIN_USERNAME}' on realm '{settings.KEYCLOAK_ADMIN_TOKEN_REALM}' ({reason}). Check KEYCLOAK_ADMIN_USERNAME / KEYCLOAK_ADMIN_PASSWORD.")
    payload = response.json()
    _cached_token = payload["access_token"]
    _cached_token_expires_at = time.time() + max(30, int(payload.get("expires_in", 60)) - 15)
    return _cached_token


def _request(method: str, path: str, **kwargs: Any) -> httpx.Response:
    headers = kwargs.pop("headers", {})
    headers["Authorization"] = f"Bearer {_token()}"
    response = httpx.request(method, f"{_base()}/admin/realms/{settings.KEYCLOAK_ADMIN_REALM}{path}", headers=headers, timeout=20, **kwargs)
    if response.status_code == 401:
        headers["Authorization"] = f"Bearer {_token(force=True)}"
        response = httpx.request(method, f"{_base()}/admin/realms/{settings.KEYCLOAK_ADMIN_REALM}{path}", headers=headers, timeout=20, **kwargs)
    if response.status_code >= 400 and response.status_code != 404:
        detail = response.text[:300] or "Keycloak admin request failed"
        raise HTTPException(response.status_code, detail)
    return response


def list_users(search: str = "", limit: int = 20) -> dict[str, Any]:
    params = {"max": min(max(limit, 1), 200), "briefRepresentation": "false"}
    if search.strip(): params["search"] = search.strip()
    users = _request("GET", "/users", params=params).json()
    rows = [{"user_id": u["id"], "username": u.get("username", ""), "email": u.get("email", ""), "name": f"{u.get('firstName', '')} {u.get('lastName', '')}".strip(), "first_name": u.get("firstName", ""), "last_name": u.get("lastName", ""), "enabled": u.get("enabled", False), "email_verified": u.get("emailVerified", False), "roles": [], "states": [], "access_type": "dashboard", "access_label": "Dashboard"} for u in users]
    for row in rows:
        roles = _request("GET", f"/users/{row['user_id']}/role-mappings/realm").json()
        row["roles"] = [
            r["name"] for r in roles
            if r.get("name") and r["name"] not in KEYCLOAK_BUILT_IN_ROLES
            and not r["name"].startswith("default-roles-")
        ]
        if "super_admin" in row["roles"]: row["access_type"], row["access_label"] = "super_admin", "Super Admin"
        elif "admin" in row["roles"]: row["access_type"], row["access_label"] = "admin", "Admin"
    return {"total": len(rows), "users": rows, "realm": settings.KEYCLOAK_ADMIN_REALM}


def _describe_role(name: str, role: dict[str, Any] | None) -> dict[str, Any]:
    """One role as the console shows it, whether or not it is in Keycloak yet."""
    built_in = ROLE_DATA.get(name)
    attributes = (role or {}).get("attributes") or {}

    def attribute(key: str) -> str:
        values = attributes.get(key) or []
        return values[0] if values else ""

    permissions: list[str] = []
    raw = attribute(PERMISSIONS_ATTRIBUTE)
    if raw:
        try:
            decoded = json.loads(raw)
            if isinstance(decoded, list):
                permissions = [str(item) for item in decoded]
        except json.JSONDecodeError:
            permissions = []
    if not permissions and built_in:
        permissions = list(built_in["permissions"])

    return {
        "name": name,
        "label": attribute(LABEL_ATTRIBUTE) or (built_in or {}).get("label") or name.replace("_", " ").title(),
        "description": (role or {}).get("description") or (built_in or {}).get("description") or "",
        "permissions": permissions,
        "scope": "Global" if name == "super_admin" else "Workspace",
        "custom": built_in is None,
        "exists": role is not None,
    }


def list_roles() -> dict[str, Any]:
    """The two built-in roles plus every custom realm role.

    `briefRepresentation=false` is what makes Keycloak return attributes, which
    is where a custom role's label and permissions are stored.
    """
    response = _request("GET", "/roles", params={"briefRepresentation": "false"})
    existing = {
        role["name"]: role
        for role in (response.json() if response.status_code == 200 else [])
        if role.get("name") and role["name"] not in KEYCLOAK_BUILT_IN_ROLES
        and not role["name"].startswith("default-roles-")
    }

    roles = [_describe_role(name, existing.get(name)) for name in ROLE_DATA]
    roles += [
        _describe_role(name, role)
        for name, role in sorted(existing.items())
        if name not in ROLE_DATA
    ]
    return {"realm": settings.KEYCLOAK_ADMIN_REALM, "roles": roles}


def ensure_role(name: str, label: str, description: str, permissions: list[str]) -> dict[str, Any]:
    """Create the role if it is missing, then update its label and permissions.

    Any name is accepted, not only the two built-in ones: the console needs to
    be able to add a role. A built-in role keeps its defaults when the caller
    sends nothing for a field, so re-saving one cannot empty it.
    """
    name = (name or "").strip().lower()
    if not ROLE_NAME.match(name):
        raise HTTPException(400, "Role name must be lowercase letters, digits and underscores, starting with a letter")

    built_in = ROLE_DATA.get(name)
    label = (label or "").strip() or (built_in or {}).get("label") or name.replace("_", " ").title()
    description = (description or "").strip() or (built_in or {}).get("description") or ""
    permissions = permissions or list((built_in or {}).get("permissions") or [])

    body = {
        "name": name,
        "description": description,
        "attributes": {
            LABEL_ATTRIBUTE: [label],
            PERMISSIONS_ATTRIBUTE: [json.dumps(permissions)],
        },
    }

    existing = _request("GET", f"/roles/{name}")
    if existing.status_code == 404:
        _request("POST", "/roles", json=body)
    else:
        _request("PUT", f"/roles/{name}", json=body)

    return {**_describe_role(name, body), "exists": True}


def create_user(payload: dict[str, Any]) -> dict[str, Any]:
    email = str(payload.get("email", "")).strip().lower()
    if not email or "@" not in email: raise HTTPException(400, "Valid email is required")
    body = {"username": payload.get("username") or email.split("@", 1)[0], "email": email, "firstName": payload.get("first_name", ""), "lastName": payload.get("last_name", ""), "enabled": True, "emailVerified": True}
    _request("POST", "/users", json=body)
    user = _request("GET", "/users", params={"email": email, "exact": "true"}).json()[0]
    return {"created": True, "user_id": user["id"], "username": user.get("username", ""), "email": email, "roles": []}


def assign_role(user_id: str, role_name: str) -> dict[str, Any]:
    response = _request("GET", f"/roles/{role_name}")
    if response.status_code == 404:
        raise HTTPException(400, f"Role {role_name} does not exist in this realm")
    role = response.json()
    _request("POST", f"/users/{user_id}/role-mappings/realm", json=[{"id": role["id"], "name": role_name}])
    return {"user_id": user_id, "role": role_name, "roles": [role_name], "requires_relogin": True}
