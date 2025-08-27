from fastapi import APIRouter, Depends, HTTPException, status
from fastapi.security import HTTPBearer
from sqlalchemy.orm import Session
from typing import List
from datetime import timedelta

from dependencies import get_db, get_current_active_user, require_admin, require_superadmin
from models.user import User, UserRole, UserStatus
from schemas.user import UserCreate, UserUpdate, UserResponse, UserLogin, Token
from auth import verify_password, get_password_hash, create_access_token, ACCESS_TOKEN_EXPIRE_MINUTES

router = APIRouter()

# Authentication endpoints
@router.post("/auth/login", response_model=Token)
async def login(user_credentials: UserLogin, db: Session = Depends(get_db)):
    """Authenticate user and return JWT token."""
    # Find user by username
    user = db.query(User).filter(User.username == user_credentials.username).first()
    
    if not user or not verify_password(user_credentials.password, str(user.password)):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Incorrect username or password",
            headers={"WWW-Authenticate": "Bearer"},
        )
    
    # Check if user is active - using value comparison to avoid SQLAlchemy issues
    if user.status.value != UserStatus.ACTIVE.value:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"User account is not active. Status: {user.status}"
        )
    
    # Create access token
    access_token_expires = timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
    access_token = create_access_token(
        data={"sub": str(user.username)}, expires_delta=access_token_expires
    )
    
    return {"access_token": access_token, "token_type": "bearer"}

@router.get("/auth/me", response_model=UserResponse)
async def get_current_user_info(current_user: User = Depends(get_current_active_user)):
    """Get current user information using JWT token."""
    return current_user

# User CRUD endpoints
@router.get("/users", response_model=List[UserResponse])
async def get_users(
    skip: int = 0, 
    limit: int = 100, 
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get all users (Admin/Superadmin only)."""
    users = db.query(User).offset(skip).limit(limit).all()
    return users

@router.get("/users/{user_id}", response_model=UserResponse)
async def get_user(
    user_id: int,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Get user by ID (Admin/Superadmin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user

@router.post("/users", response_model=UserResponse)
async def create_user(
    user: UserCreate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Create new user (Admin/Superadmin only)."""
    # Check if username already exists
    existing_user = db.query(User).filter(User.username == user.username).first()
    if existing_user:
        raise HTTPException(status_code=400, detail="Username already registered")
    
    # Only superadmin can create admin/superadmin users
    if user.role in [UserRole.ADMIN, UserRole.SUPERADMIN] and str(current_user.role) != UserRole.SUPERADMIN.value:
        raise HTTPException(status_code=403, detail="Insufficient permissions to create admin users")
    
    # Create user
    db_user = User(
        username=user.username,
        password=get_password_hash(user.password),
        role=user.role,
        status=user.status
    )
    
    db.add(db_user)
    db.commit()
    db.refresh(db_user)
    return db_user

@router.put("/users/{user_id}", response_model=UserResponse)
async def update_user(
    user_id: int,
    user_update: UserUpdate,
    current_user: User = Depends(require_admin),
    db: Session = Depends(get_db)
):
    """Update user (Admin/Superadmin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Only superadmin can modify admin/superadmin users
    if str(user.role) in [UserRole.ADMIN.value, UserRole.SUPERADMIN.value] and str(current_user.role) != UserRole.SUPERADMIN.value:
        raise HTTPException(status_code=403, detail="Insufficient permissions to modify admin users")
    
    # Update fields using proper SQLAlchemy update
    update_data = {}
    
    if user_update.username:
        # Check if new username is already taken
        existing = db.query(User).filter(User.username == user_update.username, User.id != user_id).first()
        if existing:
            raise HTTPException(status_code=400, detail="Username already taken")
        update_data['username'] = user_update.username
    
    if user_update.password:
        update_data['password'] = get_password_hash(user_update.password)
    
    if user_update.role is not None:
        # Only superadmin can change roles to admin/superadmin
        if user_update.role in [UserRole.ADMIN, UserRole.SUPERADMIN] and str(current_user.role) != UserRole.SUPERADMIN.value:
            raise HTTPException(status_code=403, detail="Insufficient permissions to assign admin roles")
        update_data['role'] = user_update.role
    
    if user_update.status is not None:
        update_data['status'] = user_update.status
    
    # Perform the update
    if update_data:
        db.query(User).filter(User.id == user_id).update(update_data)
        db.commit()
        db.refresh(user)
    
    return user

@router.delete("/users/{user_id}")
async def delete_user(
    user_id: int,
    current_user: User = Depends(require_superadmin),
    db: Session = Depends(get_db)
):
    """Delete user (Superadmin only)."""
    user = db.query(User).filter(User.id == user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    # Prevent deleting yourself
    if user_id == current_user.id:
        raise HTTPException(status_code=400, detail="Cannot delete your own account")
    
    db.delete(user)
    db.commit()
    return {"message": "User deleted successfully"}


