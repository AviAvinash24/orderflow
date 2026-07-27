from fastapi import APIRouter, HTTPException, status
from asyncpg.exceptions import UniqueViolationError

from app.core.db import get_pool
from app.core.security import create_access_token, hash_password, verify_password
from app.schemas.auth import AuthResponse, LoginRequest, SignupRequest

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/signup", response_model=AuthResponse, status_code=status.HTTP_201_CREATED)
async def signup(body: SignupRequest):
    pool = get_pool()
    password_hash = hash_password(body.password)

    try:
        row = await pool.fetchrow(
            """
            INSERT INTO users (email, password_hash)
            VALUES ($1, $2)
            RETURNING id, email
            """,
            body.email.lower(),
            password_hash,
        )
    except UniqueViolationError:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Email already registered",
        )

    token = create_access_token(str(row["id"]), row["email"])
    return AuthResponse(
        access_token=token,
        user_id=str(row["id"]),
        email=row["email"],
    )


@router.post("/login", response_model=AuthResponse)
async def login(body: LoginRequest):
    pool = get_pool()
    row = await pool.fetchrow(
        "SELECT id, email, password_hash FROM users WHERE email = $1",
        body.email.lower(),
    )

    if row is None or not verify_password(body.password, row["password_hash"]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid email or password",
        )

    token = create_access_token(str(row["id"]), row["email"])
    return AuthResponse(
        access_token=token,
        user_id=str(row["id"]),
        email=row["email"],
    )