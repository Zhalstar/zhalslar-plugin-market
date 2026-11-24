"""FastAPI authentication dependencies."""

from typing import Annotated

from fastapi import Depends, Request
from sqlalchemy.orm import Session

from .database import get_db
from .models import User
from .security import current_user_from_request

Database = Annotated[Session, Depends(get_db)]


def get_current_user(request: Request, db: Database) -> User:
    """Provide the authenticated user for protected routes.

    Args:
        request: Current request.
        db: Open database session.

    Returns:
        Authenticated user.
    """
    return current_user_from_request(request, db)


CurrentUser = Annotated[User, Depends(get_current_user)]
