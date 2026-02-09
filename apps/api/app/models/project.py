# apps/api/app/models/project.py
"""
SQLAlchemy Project Model - CursorCode AI
Represents an autonomously generated software project.
Multi-tenant scoped, tracks full lifecycle (prompt → build → deploy → maintain).
"""

from datetime import datetime
from typing import List, Optional
from uuid import uuid4

from sqlalchemy import (
    ForeignKey,
    Index,
    Integer,
    JSON,
    String,
    Text,
    func,
)
from sqlalchemy.dialects.postgresql import UUID, ENUM  # ← Added ENUM here!
from sqlalchemy.orm import Mapped, mapped_column, relationship
from enum import Enum as PyEnum

from app.db.base import Base


class ProjectStatus(str, PyEnum):
    """
    Project lifecycle states.
    Stored as native PostgreSQL ENUM type.
    """
    PENDING = "pending"
    BUILDING = "building"
    COMPLETED = "completed"
    FAILED = "failed"
    DEPLOYED = "deployed"
    MAINTAINING = "maintaining"


class Project(Base):
    """
    Project Entity
    - Created from user prompt via AI agents
    - Scoped to Organization (multi-tenant)
    - Tracks generated code, deployment, status, logs
    - Supports version history, RAG memory, rollback
    """

    __tablename__ = "projects"

    __table_args__ = (
        Index("ix_projects_user_id_status", "user_id", "status"),
        Index("ix_projects_org_id", "org_id"),
        Index("ix_projects_deploy_url", "deploy_url"),
        {'extend_existing': True},
    )

    id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        primary_key=True,
        default=uuid4,
        server_default=func.gen_random_uuid(),
        index=True,
    )

    # Core
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    title: Mapped[Optional[str]] = mapped_column(String(255), nullable=True)
    description: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Status & Lifecycle
    status: Mapped[ProjectStatus] = mapped_column(
        ENUM(ProjectStatus, name="project_status_enum", native_enum=True),
        default=ProjectStatus.PENDING,
        nullable=False,
        index=True,
    )
    error_message: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    logs: Mapped[Optional[List[str]]] = mapped_column(JSON, nullable=True)

    # Generated Artifacts
    code_repo_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    deploy_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    preview_url: Mapped[Optional[str]] = mapped_column(String(512), nullable=True)
    openapi_spec: Mapped[Optional[str]] = mapped_column(Text, nullable=True)

    # Versioning & Rollback
    current_version: Mapped[int] = mapped_column(Integer, default=1, nullable=False)
    versions: Mapped[Optional[List[dict]]] = mapped_column(JSON, nullable=True)

    # AI Features
    rag_embeddings: Mapped[Optional[bytes]] = mapped_column(String(1536 * 4), nullable=True)  # pgvector vector(1536)
    memory_context: Mapped[Optional[dict]] = mapped_column(JSON, nullable=True)

    # Ownership & Tenant
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )
    org_id: Mapped[str] = mapped_column(
        UUID(as_uuid=True),
        ForeignKey("orgs.id", ondelete="CASCADE"),
        nullable=False,
        index=True,
    )

    # Relationships
    user: Mapped["User"] = relationship("User", back_populates="projects")
    org: Mapped["Org"] = relationship("Org", back_populates="projects")

    # Timestamps & Soft Delete
    created_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )
    deleted_at: Mapped[Optional[datetime]] = mapped_column(nullable=True, index=True)

    def __repr__(self) -> str:
        return f"<Project(id={self.id}, title={self.title}, status={self.status}, org_id={self.org_id})>"

    @property
    def is_active(self) -> bool:
        return self.deleted_at is None and self.status not in [ProjectStatus.FAILED]

    def update_status(self, new_status: ProjectStatus, message: Optional[str] = None) -> None:
        self.status = new_status
        if message:
            self.error_message = message
        self.updated_at = datetime.utcnow()

    def add_version(self, commit_hash: str, changes: dict) -> None:
        version_data = {
            "version": self.current_version + 1,
            "commit": commit_hash,
            "timestamp": datetime.utcnow().isoformat(),
            "changes": changes
        }
        if not self.versions:
            self.versions = []
        self.versions.append(version_data)
        self.current_version += 1
