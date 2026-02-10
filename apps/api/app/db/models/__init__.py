# app/db/models/__init__.py
"""
Central aggregator / namespace for all SQLAlchemy models in CursorCode AI.

Purpose:
- Single clean import point for models throughout the app
- Prevents circular import issues
- Makes model usage consistent and IDE-friendly

Recommended usage:
    from app.db.models import User, Project, Base, ProjectStatus, Org, Plan, AuditLog

Import order inside this file is important:
1. Base (always first)
2. Independent / core models (Org, Plan, User...)
3. Dependent models (Project → depends on User/Org)
4. Audit / history models (last, as they may reference others)
"""

# ────────────────────────────────────────────────
# Core / foundational (no dependencies)
# ────────────────────────────────────────────────
from .base import Base

# ────────────────────────────────────────────────
# Organization & User models
# ────────────────────────────────────────────────
from .org import Org
from .user import User, UserRole

# ────────────────────────────────────────────────
# Billing / Plan model
# ────────────────────────────────────────────────
from .plan import Plan

# ────────────────────────────────────────────────
# Project model (depends on User & Org)
# ────────────────────────────────────────────────
from .project import Project, ProjectStatus

# ────────────────────────────────────────────────
# Audit / logging model (references User)
# ────────────────────────────────────────────────
from .audit import AuditLog

# ────────────────────────────────────────────────
# Public exports (__all__)
# ────────────────────────────────────────────────
# Controls what is available when doing `from app.db.models import *`
__all__ = [
    # Base class
    "Base",

    # Organization & User
    "Org",
    "User",
    "UserRole",

    # Billing / Plans
    "Plan",

    # Projects
    "Project",
    "ProjectStatus",

    # Audit trail
    "AuditLog",

    # Add future models here (in dependency order)
    # e.g. "Subscription", "CreditTransaction", "Payment", "Invitation"
]

# Prevent accidental execution when imported
if __name__ == "__main__":
    print("This is a model aggregator module — do not run directly.")
