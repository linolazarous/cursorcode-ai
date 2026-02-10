# apps/api/app/db/models.py
"""
Central aggregator for all SQLAlchemy model imports in CursorCode AI.

Purpose:
- Single import point for models throughout the app
- Prevents circular import issues
- Makes model usage clean and consistent
- Export commonly used types via __all__

Usage example:
    from app.db.models import User, Project, Base, ProjectStatus

Import order is important:
1. Base (always first)
2. Core/domain models (User, Org, Plan...)
3. Dependent models (Project, AuditLog...)
"""

from .base import Base

# ────────────────────────────────────────────────
# Core / foundational models (no dependencies)
# ────────────────────────────────────────────────
from .user import User, Org, UserRole
from .plan import Plan

# ────────────────────────────────────────────────
# Domain models (may depend on core models)
# ────────────────────────────────────────────────
from .project import Project, ProjectStatus

# ────────────────────────────────────────────────
# Audit / logging / history models
# ────────────────────────────────────────────────
from .audit import AuditLog

# ────────────────────────────────────────────────
# Export all public models & types
# ────────────────────────────────────────────────
# This allows clean imports like:
#     from app.db.models import User, Project, Base, ProjectStatus
__all__ = [
    # Base class
    "Base",

    # User & Organization
    "User",
    "Org",
    "UserRole",

    # Billing / Plans
    "Plan",

    # Projects
    "Project",
    "ProjectStatus",

    # Audit & logging
    "AuditLog",

    # Add new models here when created (in dependency order)
    # e.g. "Subscription", "CreditTransaction", "Payment", "Invitation", "TeamMember"
]
