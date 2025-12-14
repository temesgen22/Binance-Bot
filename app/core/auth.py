"""
Authentication utilities: password hashing and JWT token management.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Optional
from uuid import UUID

from jose import JWTError, jwt
import bcrypt
from loguru import logger

from app.core.config import get_settings

# JWT settings
ALGORITHM = "HS256"


def get_jwt_secret_key() -> str:
    """Get JWT secret key from settings."""
    settings = get_settings()
    return settings.jwt_secret_key


def verify_password(plain_password: str, hashed_password: str) -> bool:
    """Verify a password against a hash.
    
    Note: bcrypt has a 72-byte limit. Passwords longer than 72 bytes
    will be truncated to match the hashing behavior.
    """
    try:
        # Ensure password is bytes
        if isinstance(plain_password, str):
            plain_password = plain_password.encode('utf-8')
        if isinstance(hashed_password, str):
            hashed_password = hashed_password.encode('utf-8')
        
        # Bcrypt has a 72-byte limit - truncate if necessary
        if len(plain_password) > 72:
            plain_password = plain_password[:72]
        
        return bcrypt.checkpw(plain_password, hashed_password)
    except Exception as e:
        logger.error(f"Password verification error: {e}")
        return False


def get_password_hash(password: str) -> str:
    """Hash a password using bcrypt.
    
    Note: bcrypt has a 72-byte limit. Passwords longer than 72 bytes
    will be truncated automatically by bcrypt, but we handle it explicitly
    to avoid issues.
    """
    # Convert to bytes if string
    if isinstance(password, str):
        password_bytes = password.encode('utf-8')
    else:
        password_bytes = password
    
    # Bcrypt has a 72-byte limit - truncate if necessary
    if len(password_bytes) > 72:
        password_bytes = password_bytes[:72]
        logger.warning("Password truncated to 72 bytes for bcrypt compatibility")
    
    # Generate salt and hash
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(password_bytes, salt)
    
    # Return as string
    return hashed.decode('utf-8')


def create_access_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """Create a JWT access token.
    
    Args:
        data: Data to encode in the token (typically user_id, username, etc.)
        expires_delta: Optional expiration time. Defaults to 24 hours.
    
    Returns:
        Encoded JWT token string
    """
    settings = get_settings()
    secret_key = settings.jwt_secret_key
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        # Default: 24 hours
        expire = datetime.now(timezone.utc) + timedelta(hours=24)
    
    to_encode = data.copy()
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "access"
    })
    
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)
    return encoded_jwt


def create_refresh_token(
    data: dict,
    expires_delta: Optional[timedelta] = None
) -> str:
    """Create a JWT refresh token.
    
    Args:
        data: Data to encode in the token (typically user_id)
        expires_delta: Optional expiration time. Defaults to 7 days.
    
    Returns:
        Encoded JWT refresh token string
    """
    settings = get_settings()
    secret_key = settings.jwt_secret_key
    
    if expires_delta:
        expire = datetime.now(timezone.utc) + expires_delta
    else:
        # Default: 7 days
        expire = datetime.now(timezone.utc) + timedelta(days=7)
    
    to_encode = data.copy()
    to_encode.update({
        "exp": expire,
        "iat": datetime.now(timezone.utc),
        "type": "refresh"
    })
    
    encoded_jwt = jwt.encode(to_encode, secret_key, algorithm=ALGORITHM)
    return encoded_jwt


def decode_token(token: str) -> Optional[dict]:
    """Decode and verify a JWT token.
    
    Args:
        token: JWT token string
    
    Returns:
        Decoded token payload if valid, None otherwise
    """
    try:
        settings = get_settings()
        secret_key = settings.jwt_secret_key
        payload = jwt.decode(token, secret_key, algorithms=[ALGORITHM])
        return payload
    except JWTError as e:
        logger.debug(f"JWT decode error: {e}")
        return None


def get_user_id_from_token(token: str) -> Optional[UUID]:
    """Extract user_id from a JWT token.
    
    Args:
        token: JWT token string
    
    Returns:
        User ID (UUID) if token is valid, None otherwise
    """
    payload = decode_token(token)
    if payload and "sub" in payload:
        try:
            return UUID(payload["sub"])
        except (ValueError, TypeError):
            return None
    return None

