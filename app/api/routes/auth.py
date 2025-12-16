"""
Authentication API routes: register, login, logout, refresh token.
"""
from __future__ import annotations

from datetime import timedelta
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials
from pydantic import BaseModel, EmailStr, Field
from sqlalchemy.orm import Session
from sqlalchemy.exc import IntegrityError
from sqlalchemy import func

from app.api.deps import get_db_session_dependency, security
from app.core.auth import (
    verify_password,
    get_password_hash,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_user_id_from_token
)
from app.core.config import get_settings
from app.services.database_service import DatabaseService
from app.models.db_models import User, Role
from loguru import logger

router = APIRouter(prefix="/api/auth", tags=["authentication"])


# ============================================
# REQUEST/RESPONSE MODELS
# ============================================

class RegisterRequest(BaseModel):
    """User registration request."""
    username: str = Field(..., min_length=3, max_length=100, description="Username (3-100 characters)")
    email: EmailStr = Field(..., description="Email address")
    password: str = Field(..., min_length=8, max_length=100, description="Password (minimum 8 characters)")
    full_name: Optional[str] = Field(None, max_length=255, description="Full name (optional)")


class LoginRequest(BaseModel):
    """User login request."""
    username: str = Field(..., description="Username or email")
    password: str = Field(..., description="Password")


class TokenResponse(BaseModel):
    """JWT token response."""
    access_token: str = Field(..., description="JWT access token")
    refresh_token: str = Field(..., description="JWT refresh token")
    token_type: str = Field(default="bearer", description="Token type")
    expires_in: int = Field(..., description="Access token expiration time in seconds")


class UserResponse(BaseModel):
    """User information response."""
    id: str
    username: str
    email: str
    full_name: Optional[str] = None
    is_active: bool = True
    is_verified: bool = False
    created_at: str = ""

    @classmethod
    def from_user(cls, user: User) -> "UserResponse":
        """Create UserResponse from User model."""
        # Validate user object has required fields
        if not user:
            raise ValueError("User object is None")
        
        if not user.id:
            raise ValueError(f"User object has no id: {user}")
        
        if not user.username:
            raise ValueError(f"User object has no username: {user.id}")
        
        if not user.email:
            raise ValueError(f"User object has no email: {user.id}")
        
        # Handle created_at - ensure it's a datetime or use current time
        from datetime import datetime, timezone
        if user.created_at:
            if hasattr(user.created_at, 'isoformat'):
                created_at_str = user.created_at.isoformat()
            else:
                created_at_str = str(user.created_at)
        else:
            # Fallback to current time if created_at is None
            created_at_str = datetime.now(timezone.utc).isoformat()
        
        try:
            return cls(
                id=str(user.id),
                username=str(user.username),
                email=str(user.email),
                full_name=str(user.full_name) if user.full_name else None,
                is_active=bool(user.is_active) if user.is_active is not None else True,
                is_verified=bool(user.is_verified) if user.is_verified is not None else False,
                created_at=created_at_str
            )
        except Exception as e:
            raise ValueError(f"Failed to create UserResponse from user {user.id}: {e}") from e


class RefreshTokenRequest(BaseModel):
    """Refresh token request."""
    refresh_token: str = Field(..., description="Refresh token")


# ============================================
# AUTHENTICATION ENDPOINTS
# ============================================

@router.post("/register", response_model=UserResponse, status_code=status.HTTP_201_CREATED)
def register(
    request: RegisterRequest,
    db: Session = Depends(get_db_session_dependency)
) -> UserResponse:
    """Register a new user account.
    
    Creates a new user account with the provided credentials.
    The password is hashed before storage.
    """
    db_service = DatabaseService(db)
    
    # Check if username already exists
    if db_service.get_user_by_username(request.username):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Username already registered"
        )
    
    # Check if email already exists
    if db_service.get_user_by_email(request.email):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Email already registered"
        )
    
    # Hash password
    password_hash = get_password_hash(request.password)
    
    # Create user
    try:
        user = db_service.create_user(
            username=request.username,
            email=request.email,
            password_hash=password_hash,
            full_name=request.full_name
        )
        
        # Assign default "user" role (if it exists)
        # TODO: Create default roles in migration or seed script
        try:
            user_role = db.query(Role).filter(Role.name == "user").first()
            if user_role:
                user.roles.append(user_role)
                db.commit()
                db.refresh(user)
        except Exception as role_error:
            logger.warning(f"Could not assign default role: {role_error}")
            # Continue without role assignment - user can be assigned roles later
        
        # Ensure user is refreshed to get all database defaults
        db.refresh(user)
        
        logger.info(f"User registered: {user.username} ({user.id})")
        logger.debug(f"User data: id={user.id}, created_at={user.created_at}, is_active={user.is_active}")
        
        # Validate user data before creating response
        try:
            return UserResponse.from_user(user)
        except Exception as response_error:
            logger.error(f"Failed to create UserResponse: {response_error}", exc_info=True)
            logger.error(f"User object: id={user.id}, username={user.username}, created_at={user.created_at}")
            raise ValueError(f"Failed to create user response: {response_error}") from response_error
        
    except IntegrityError as e:
        db.rollback()
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        logger.error(f"Failed to register user: {error_msg}")
        
        # Provide more specific error messages
        if 'username' in error_msg.lower() or 'users_username' in error_msg.lower():
            if 'unique' in error_msg.lower() or 'duplicate' in error_msg.lower():
                detail = "Username already registered"
            elif 'check' in error_msg.lower() or 'constraint' in error_msg.lower():
                detail = "Username format invalid. Only lowercase letters, numbers, underscores, and hyphens allowed."
            else:
                detail = f"Username error: {error_msg}"
        elif 'email' in error_msg.lower() or 'users_email' in error_msg.lower():
            if 'unique' in error_msg.lower() or 'duplicate' in error_msg.lower():
                detail = "Email already registered"
            else:
                detail = f"Email error: {error_msg}"
        else:
            detail = f"Registration failed: {error_msg}"
        
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=detail
        )
    except Exception as e:
        db.rollback()
        error_msg = str(e)
        error_type = type(e).__name__
        logger.exception(f"Unexpected error during registration ({error_type}): {error_msg}")
        
        # Provide more helpful error message
        if isinstance(e, ValueError):
            detail = f"Registration failed: {error_msg}. Please check your input data."
        else:
            detail = f"Registration failed: {error_msg}. Please check server logs for details."
        
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail
        )


@router.post("/login", response_model=TokenResponse)
def login(
    request: LoginRequest,
    db: Session = Depends(get_db_session_dependency)
) -> TokenResponse:
    """Login and get JWT tokens.
    
    Authenticates the user and returns access and refresh tokens.
    """
    db_service = DatabaseService(db)
    settings = get_settings()
    
    # Try to find user by username or email
    user = db_service.get_user_by_username(request.username)
    if not user:
        user = db_service.get_user_by_email(request.username)
    
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    # Verify password
    if not verify_password(request.password, user.password_hash):
        # Increment failed login attempts
        user.failed_login_attempts += 1
        db.commit()
        
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid username or password"
        )
    
    # Check if account is active
    if not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Account is inactive"
        )
    
    # Reset failed login attempts on successful login
    user.failed_login_attempts = 0
    from datetime import datetime, timezone
    user.last_login = datetime.now(timezone.utc)
    db.commit()
    
    # Create tokens
    token_data = {
        "sub": str(user.id),  # Subject (user ID)
        "username": user.username,
        "email": user.email
    }
    
    access_token_expires = timedelta(hours=settings.jwt_access_token_expire_hours)
    refresh_token_expires = timedelta(days=settings.jwt_refresh_token_expire_days)
    
    access_token = create_access_token(token_data, expires_delta=access_token_expires)
    refresh_token = create_refresh_token(token_data, expires_delta=refresh_token_expires)
    
    logger.info(f"User logged in: {user.username} ({user.id})")
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=int(access_token_expires.total_seconds())
    )


@router.post("/refresh", response_model=TokenResponse)
def refresh_token(
    request: RefreshTokenRequest,
    db: Session = Depends(get_db_session_dependency)
) -> TokenResponse:
    """Refresh access token using refresh token.
    
    Validates the refresh token and returns a new access token.
    """
    settings = get_settings()
    
    # Decode refresh token
    payload = decode_token(request.refresh_token)
    if not payload:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid refresh token"
        )
    
    # Check token type
    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type"
        )
    
    # Get user_id from token
    user_id = get_user_id_from_token(request.refresh_token)
    if not user_id:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token payload"
        )
    
    # Verify user exists and is active
    db_service = DatabaseService(db)
    user = db_service.get_user_by_id(user_id)
    if not user or not user.is_active:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive"
        )
    
    # Create new access token
    token_data = {
        "sub": str(user.id),
        "username": user.username,
        "email": user.email
    }
    
    access_token_expires = timedelta(hours=settings.jwt_access_token_expire_hours)
    access_token = create_access_token(token_data, expires_delta=access_token_expires)
    
    # Optionally create a new refresh token (rotate refresh tokens)
    refresh_token_expires = timedelta(days=settings.jwt_refresh_token_expire_days)
    refresh_token = create_refresh_token(token_data, expires_delta=refresh_token_expires)
    
    return TokenResponse(
        access_token=access_token,
        refresh_token=refresh_token,
        token_type="bearer",
        expires_in=int(access_token_expires.total_seconds())
    )


@router.get("/me", response_model=UserResponse)
def get_current_user_info(
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db_session_dependency)
) -> UserResponse:
    """Get current authenticated user information."""
    from app.api.deps import get_current_user
    
    user = get_current_user(credentials, db)
    return UserResponse.from_user(user)


@router.post("/logout")
def logout() -> dict:
    """Logout (client-side token removal).
    
    Note: With JWT tokens, logout is typically handled client-side by removing tokens.
    For server-side session invalidation, you would need to maintain a token blacklist.
    """
    return {
        "message": "Logged out successfully. Please remove tokens from client storage."
    }


class ChangePasswordRequest(BaseModel):
    """Change password request."""
    current_password: str = Field(..., description="Current password")
    new_password: str = Field(..., min_length=8, max_length=100, description="New password (minimum 8 characters)")


class UpdateProfileRequest(BaseModel):
    """Update profile request."""
    email: Optional[EmailStr] = Field(None, description="Email address")
    full_name: Optional[str] = Field(None, max_length=255, description="Full name")


@router.post("/change-password", response_model=dict)
def change_password(
    request: ChangePasswordRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db_session_dependency)
) -> dict:
    """Change user password.
    
    Requires the current password to be provided for verification.
    """
    from app.api.deps import get_current_user
    
    user = get_current_user(credentials, db)
    db_service = DatabaseService(db)
    
    # Verify current password
    if not verify_password(request.current_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Current password is incorrect"
        )
    
    # Check if new password is the same as current password
    if verify_password(request.new_password, user.password_hash):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="New password must be different from current password"
        )
    
    # Hash new password
    new_password_hash = get_password_hash(request.new_password)
    
    # Update password
    try:
        db_service.update_user(user.id, password_hash=new_password_hash)
        logger.info(f"Password changed for user: {user.username} ({user.id})")
        return {"message": "Password changed successfully"}
    except Exception as e:
        logger.error(f"Failed to change password for user {user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to change password"
        )


@router.put("/profile", response_model=UserResponse)
def update_profile(
    request: UpdateProfileRequest,
    credentials: HTTPAuthorizationCredentials = Depends(security),
    db: Session = Depends(get_db_session_dependency)
) -> UserResponse:
    """Update user profile information.
    
    Allows updating email and full_name. Email must be unique if changed.
    """
    from app.api.deps import get_current_user
    
    user = get_current_user(credentials, db)
    db_service = DatabaseService(db)
    
    updates = {}
    
    # Update email if provided and different
    if request.email is not None and request.email != user.email:
        # Check if email is already taken by another user
        existing_user = db_service.get_user_by_email(request.email)
        if existing_user and existing_user.id != user.id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        updates["email"] = request.email
    
    # Update full_name if provided
    if request.full_name is not None:
        updates["full_name"] = request.full_name
    
    # If no updates, return current user
    if not updates:
        return UserResponse.from_user(user)
    
    # Update user
    try:
        updated_user = db_service.update_user(user.id, **updates)
        if not updated_user:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="User not found"
            )
        logger.info(f"Profile updated for user: {user.username} ({user.id})")
        return UserResponse.from_user(updated_user)
    except IntegrityError as e:
        db.rollback()
        error_msg = str(e.orig) if hasattr(e, 'orig') else str(e)
        logger.error(f"Failed to update profile: {error_msg}")
        
        if 'email' in error_msg.lower():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Email already registered"
            )
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to update profile: {error_msg}"
        )
    except Exception as e:
        db.rollback()
        logger.error(f"Failed to update profile for user {user.id}: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Failed to update profile"
        )

