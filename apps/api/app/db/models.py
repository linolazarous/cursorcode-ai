# apps/api/app/db/models.py
"""
Central location for all SQLAlchemy model imports.
Use this file to import models throughout the app.

This avoids circular import issues and keeps imports clean.

All models should inherit from Base (defined in app/db/base.py).
Order of imports matters when there are relationships between models.
"""

from .base import Base  # Declarative base class — all models inherit from this

# Import all models here (order matters for relationships)
from .user import User, Org, UserRole
from .project import Project, ProjectStatus
from .audit import AuditLog
from .plan import Plan               # Billing plans with Stripe price IDs

# ────────────────────────────────────────────────
# Export commonly used types/enums/models
# This makes it easy to do: from app.db.models import User, Plan, Base, ...
# ────────────────────────────────────────────────
__all__ = [
    # Base class
    "Base",
    
    # User & Organization related
    "User",
    "Org",
    "UserRole",
    
    # Project related
    "Project",
    "ProjectStatus",
    
    # Audit & logging
    "AuditLog",
    
    # Billing / Plans
    "Plan",
    
    # Add future models here (e.g. "Subscription", "CreditTransaction", etc.)
]
