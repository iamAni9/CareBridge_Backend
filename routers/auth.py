import os
from datetime import datetime, timedelta, timezone
from fastapi import APIRouter, HTTPException, Depends
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from jose import jwt, JWTError
from passlib.context import CryptContext

from models.schemas import LoginRequest, RegisterRequest
from services.supabase_client import supabase

router = APIRouter(prefix="/api/v1/auth", tags=["Auth"])
security = HTTPBearer()
pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

JWT_SECRET = os.getenv("JWT_SECRET", "carebridge-dev-secret-key")
JWT_ALGORITHM = os.getenv("JWT_ALGORITHM", "HS256")
ACCESS_TOKEN_EXPIRE_MINUTES = int(os.getenv("ACCESS_TOKEN_EXPIRE_MINUTES", "1440"))


def create_access_token(data: dict) -> str:
    to_encode = data.copy()
    expire = datetime.now(timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    to_encode.update({"exp": expire})
    return jwt.encode(to_encode, JWT_SECRET, algorithm=JWT_ALGORITHM)


def get_current_user(credentials: HTTPAuthorizationCredentials = Depends(security)) -> dict:
    """Decode JWT and return payload with sub, role, name."""
    try:
        payload = jwt.decode(credentials.credentials, JWT_SECRET, algorithms=[JWT_ALGORITHM])
        user_id = payload.get("sub")
        if user_id is None:
            raise HTTPException(status_code=401, detail="Invalid token")
        return payload
    except JWTError:
        raise HTTPException(status_code=401, detail="Invalid or expired token")


@router.post("/login")
def login(body: LoginRequest):
    """Authenticate user with email + password, return JWT."""
    result = supabase.table("users").select("*").eq("email", body.email).execute()

    if not result.data or len(result.data) == 0:
        # Fallback for mock family accounts if not seeded in Supabase yet
        if body.email in ["takeshi@example.com", "yuko@example.com"] and body.password == "password123":
            role = "family"
            name = "Takeshi Tanaka" if body.email == "takeshi@example.com" else "Yuko Tanaka"
            user_id = "00000000-0000-0000-0000-000000000004" if body.email == "takeshi@example.com" else "00000000-0000-0000-0000-000000000005"
            token = create_access_token({
                "sub": user_id,
                "role": role,
                "name": name,
                "email": body.email,
            })
            return {
                "access_token": token,
                "token_type": "bearer",
                "role": role,
                "user_id": user_id,
                "name": name,
            }
        raise HTTPException(status_code=401, detail="Invalid email or password")

    user = result.data[0]

    if not pwd_context.verify(body.password, user["password_hash"]):
        raise HTTPException(status_code=401, detail="Invalid email or password")

    token = create_access_token({
        "sub": user["id"],
        "role": user["role"],
        "name": user["name"],
        "email": user["email"],
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user["role"],
        "user_id": user["id"],
        "name": user["name"],
    }


@router.post("/register")
def register(body: RegisterRequest):
    """Register new user + create profile, return JWT."""
    # Check if email already exists
    existing = supabase.table("users").select("id").eq("email", body.email).execute()
    if existing.data and len(existing.data) > 0:
        raise HTTPException(status_code=400, detail="Email already registered")

    # Hash password
    password_hash = pwd_context.hash(body.password)

    # Insert user
    user_result = supabase.table("users").insert({
        "email": body.email,
        "password_hash": password_hash,
        "role": body.role,
        "name": body.name,
        "phone": body.phone,
    }).execute()

    if not user_result.data:
        raise HTTPException(status_code=500, detail="Failed to create user")

    user = user_result.data[0]

    # Create role-specific profile
    if body.role == "elder":
        supabase.table("elder_profiles").insert({
            "user_id": user["id"],
            "age": body.age or 70,
            "lat": body.lat,
            "lng": body.lng,
        }).execute()
    else:
        supabase.table("volunteer_profiles").insert({
            "user_id": user["id"],
            "is_available": True,
            "lat": body.lat,
            "lng": body.lng,
        }).execute()

    token = create_access_token({
        "sub": user["id"],
        "role": user["role"],
        "name": user["name"],
        "email": user["email"],
    })

    return {
        "access_token": token,
        "token_type": "bearer",
        "role": user["role"],
        "user_id": user["id"],
        "name": user["name"],
    }


@router.get("/me")
def get_me(current_user: dict = Depends(get_current_user)):
    """Return current user info from JWT + profile."""
    user_id = current_user["sub"]
    role = current_user["role"]

    user_result = supabase.table("users").select("id, email, name, phone, role").eq("id", user_id).execute()
    if not user_result.data:
        # Fallback mock user response if family user is not in Supabase yet
        if user_id in ["00000000-0000-0000-0000-000000000004", "00000000-0000-0000-0000-000000000005"]:
            return {
                "id": user_id,
                "email": "takeshi@example.com" if user_id == "00000000-0000-0000-0000-000000000004" else "yuko@example.com",
                "name": "Takeshi Tanaka" if user_id == "00000000-0000-0000-0000-000000000004" else "Yuko Tanaka",
                "phone": "+81-90-8765-4321" if user_id == "00000000-0000-0000-0000-000000000004" else "+81-90-5555-1234",
                "role": "family"
            }
        raise HTTPException(status_code=404, detail="User not found")

    user = user_result.data[0]

    # Get profile based on role
    if role == "elder":
        profile = supabase.table("elder_profiles").select("*").eq("user_id", user_id).execute()
        if profile.data:
            user.update(profile.data[0])
    else:
        profile = supabase.table("volunteer_profiles").select("*").eq("user_id", user_id).execute()
        if profile.data:
            user.update(profile.data[0])

    return user
