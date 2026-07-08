from datetime import datetime, timedelta, timezone
from typing import Optional

import jwt
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from config import get_settings
from database import get_session
from models.user import User


_bearer_scheme = HTTPBearer(auto_error=False)


def create_access_token(
    user_id: int,
    expires_delta: Optional[timedelta] = None,
) -> str:
  settings = get_settings()
  now = datetime.now(timezone.utc)
  if expires_delta is None:
      expires_delta = timedelta(
          minutes=settings.JWT_ACCESS_TOKEN_EXPIRE_MINUTES or 60
      )
  expire = now + expires_delta

  payload = {
      "sub": str(user_id),
      "type": "access",
      "iat": int(now.timestamp()),
      "exp": int(expire.timestamp()),
  }

  return jwt.encode(
      payload,
      settings.JWT_SECRET_KEY,
      algorithm=settings.JWT_ALGORITHM,
  )


def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer_scheme),
    db: Session = Depends(get_session),
) -> User:
  if credentials is None or not credentials.scheme:
      raise HTTPException(
          status_code=status.HTTP_401_UNAUTHORIZED,
          detail="Not authenticated",
      )

  if credentials.scheme.lower() != "bearer":
      raise HTTPException(
          status_code=status.HTTP_401_UNAUTHORIZED,
          detail="Invalid authentication scheme",
      )

  token = credentials.credentials
  settings = get_settings()

  try:
      payload = jwt.decode(
          token,
          settings.JWT_SECRET_KEY,
          algorithms=[settings.JWT_ALGORITHM],
      )
  except jwt.ExpiredSignatureError:
      raise HTTPException(
          status_code=status.HTTP_401_UNAUTHORIZED,
          detail="Token has expired",
      )
  except jwt.PyJWTError:
      raise HTTPException(
          status_code=status.HTTP_401_UNAUTHORIZED,
          detail="Invalid token",
      )

  sub = payload.get("sub")
  if sub is None:
      raise HTTPException(
          status_code=status.HTTP_401_UNAUTHORIZED,
          detail="Invalid token payload",
      )

  try:
      user_id = int(sub)
  except ValueError:
      raise HTTPException(
          status_code=status.HTTP_401_UNAUTHORIZED,
          detail="Invalid token subject",
      )

  user = db.get(User, user_id)
  if not user:
      raise HTTPException(
          status_code=status.HTTP_401_UNAUTHORIZED,
          detail="User not found",
      )

  if not user.is_active:
      raise HTTPException(
          status_code=status.HTTP_403_FORBIDDEN,
          detail="User is deactivated",
      )

  return user

