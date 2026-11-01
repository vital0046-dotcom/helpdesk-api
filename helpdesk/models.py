from datetime import datetime, timezone

from sqlalchemy import CheckConstraint, ForeignKey, String, Text
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .extensions import db

STATUSES = ("new", "in_progress", "closed")
PRIORITIES = ("low", "medium", "high")


def utcnow():
    return datetime.now(timezone.utc)


def iso(value):
    # SQLite drops timezone information. All stored dates are UTC.
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.isoformat()


class User(db.Model):
    __tablename__ = "users"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(100))
    email: Mapped[str] = mapped_column(String(254), unique=True)

    def to_dict(self):
        return {"id": self.id, "name": self.name, "email": self.email}


class Category(db.Model):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80), unique=True)

    def to_dict(self):
        return {"id": self.id, "name": self.name}


class Ticket(db.Model):
    __tablename__ = "tickets"
    __table_args__ = (
        CheckConstraint("status IN ('new', 'in_progress', 'closed')", name="ticket_status"),
        CheckConstraint("priority IN ('low', 'medium', 'high')", name="ticket_priority"),
    )
    id: Mapped[int] = mapped_column(primary_key=True)
    title: Mapped[str] = mapped_column(String(200))
    description: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    priority: Mapped[str] = mapped_column(String(10), default="medium", index=True)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"), index=True)
    created_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), default=utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        db.DateTime(timezone=True), default=utcnow, onupdate=utcnow
    )
    comments: Mapped[list["Comment"]] = relationship(
        cascade="all, delete-orphan", back_populates="ticket"
    )

    def to_dict(self):
        return {
            "id": self.id,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "priority": self.priority,
            "author_id": self.author_id,
            "category_id": self.category_id,
            "created_at": iso(self.created_at),
            "updated_at": iso(self.updated_at),
        }


class Comment(db.Model):
    __tablename__ = "comments"
    id: Mapped[int] = mapped_column(primary_key=True)
    text: Mapped[str] = mapped_column(Text)
    author_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    ticket_id: Mapped[int] = mapped_column(ForeignKey("tickets.id", ondelete="CASCADE"), index=True)
    created_at: Mapped[datetime] = mapped_column(db.DateTime(timezone=True), default=utcnow)
    ticket: Mapped[Ticket] = relationship(back_populates="comments")

    def to_dict(self):
        return {
            "id": self.id,
            "text": self.text,
            "author_id": self.author_id,
            "ticket_id": self.ticket_id,
            "created_at": iso(self.created_at),
        }
