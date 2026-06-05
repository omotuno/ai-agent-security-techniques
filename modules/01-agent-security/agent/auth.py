from dataclasses import dataclass

from fastapi import Depends, HTTPException
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from firebase_admin import auth

from agent.config import COMPANY_ID, ensure_firebase_initialized

ensure_firebase_initialized()

security = HTTPBearer()


@dataclass
class UserContext:
    """Verified user identity extracted from Firebase ID token.

    This is the ONLY source of user identity in the system.
    Tools must NEVER accept user identity from the conversation.
    The LLM cannot modify or override these fields.
    """

    uid: str
    email: str
    department: str
    employee_id: str
    role: str  # "employee" | "manager" | "admin"
    company_id: str = COMPANY_ID


async def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(security),
) -> UserContext:
    """Verify Firebase ID token and build UserContext."""
    token = credentials.credentials
    try:
        decoded = auth.verify_id_token(token)
    except auth.InvalidIdTokenError:
        raise HTTPException(status_code=401, detail="Invalid authentication token")
    except auth.ExpiredIdTokenError:
        raise HTTPException(status_code=401, detail="Token expired")
    except Exception:
        raise HTTPException(status_code=401, detail="Authentication failed")

    return UserContext(
        uid=decoded["uid"],
        email=decoded.get("email", ""),
        department=decoded.get("department", "unknown"),
        employee_id=decoded.get("employee_id", ""),
        role=decoded.get("role", "employee"),
    )
