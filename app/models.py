import enum
from datetime import datetime
from sqlalchemy import (
    Column,
    BigInteger,
    String,
    Boolean,
    Numeric,
    Integer,
    DateTime,
    Text,
    Enum,
    ForeignKey,
    Index
)
from sqlalchemy.orm import relationship
from app.database import Base


class ContactStatus(str, enum.Enum):
    BELUM_DIHUBUNGI = "belum_dihubungi"
    SUDAH_DIHUBUNGI = "sudah_dihubungi"
    FOLLOW_UP = "follow_up"
    TIDAK_TERTARIK = "tidak_tertarik"
    DEAL = "deal"
    TIDAK_RELEVAN = "tidak_relevan"


class LeadPriority(str, enum.Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"


class CrawlRun(Base):
    __tablename__ = "crawl_runs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    location_query = Column(String(255), nullable=False)
    category_query = Column(String(255), nullable=False)
    province = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)
    search_method = Column(String(50), default="text_search")
    started_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    finished_at = Column(DateTime, nullable=True)
    status = Column(String(50), default="pending", nullable=False)  # success/failed/partial/pending
    total_businesses = Column(Integer, default=0, nullable=False)
    api_requests_used = Column(Integer, default=0, nullable=False)

    # Relationships
    businesses = relationship("Business", back_populates="crawl_run", cascade="all, delete-orphan")
    user = relationship("User", backref="crawl_runs")


class Business(Base):
    __tablename__ = "businesses"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=True, index=True)
    crawl_run_id = Column(BigInteger, ForeignKey("crawl_runs.id", ondelete="CASCADE"), nullable=False)
    google_place_id = Column(String(255), nullable=False, index=True)
    location_query = Column(String(255), nullable=False)
    category = Column(String(255), nullable=True)
    business_name = Column(String(500), nullable=False)
    address = Column(String(1000), nullable=True)
    province = Column(String(100), nullable=True)
    city = Column(String(100), nullable=True)
    phone = Column(String(50), nullable=True)
    whatsapp_link = Column(String(255), nullable=True)
    website = Column(String(500), nullable=True)
    has_website = Column(Boolean, default=False, nullable=False, index=True)
    rating_avg = Column(Numeric(3, 2), nullable=True)
    total_review = Column(Integer, default=0, nullable=False)
    opening_hours = Column(String(500), nullable=True)
    business_status = Column(String(50), nullable=True)
    gmaps_url = Column(String(1000), nullable=True)
    latitude = Column(Numeric(10, 7), nullable=True)
    longitude = Column(Numeric(10, 7), nullable=True)
    scraped_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    crawl_run = relationship("CrawlRun", back_populates="businesses")
    lead_status = relationship("LeadStatus", back_populates="business", uselist=False)
    user = relationship("User", backref="businesses")

    __table_args__ = (
        Index("idx_biz_user_place", "user_id", "google_place_id"),
        Index("idx_biz_location_category", "location_query", "category"),
    )



class LeadStatus(Base):
    __tablename__ = "lead_status"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    business_id = Column(BigInteger, ForeignKey("businesses.id", ondelete="SET NULL"), unique=True, nullable=True, index=True)
    contact_status = Column(
        Enum(ContactStatus, values_callable=lambda obj: [e.value for e in obj]),
        default=ContactStatus.BELUM_DIHUBUNGI,
        nullable=False,
        index=True
    )
    priority = Column(
        Enum(LeadPriority, values_callable=lambda obj: [e.value for e in obj]),
        default=LeadPriority.LOW,
        nullable=False
    )
    notes = Column(Text, nullable=True)
    last_contacted_at = Column(DateTime, nullable=True)
    assigned_to = Column(String(255), nullable=True)
    next_followup_at = Column(DateTime, nullable=True)
    followup_note = Column(String(255), nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)

    # Relationships
    business = relationship("Business", back_populates="lead_status")


class BusinessProfile(Base):
    __tablename__ = "business_profile"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    company_name = Column(String(255), nullable=False)
    contact_person = Column(String(255), nullable=True)
    phone = Column(String(50), nullable=True)
    website_url = Column(String(255), nullable=True, default="https://juangdev.my.id")
    default_wa_template = Column(Text, nullable=True)
    updated_at = Column(DateTime, default=datetime.utcnow, onupdate=datetime.utcnow, nullable=False)


class PortfolioItem(Base):
    __tablename__ = "portfolio_items"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    title = Column(String(255), nullable=False)
    category_keywords = Column(String(500), nullable=True)
    demo_url = Column(String(500), nullable=False)
    image_url = Column(String(500), nullable=True)
    pitch_snippet = Column(Text, nullable=True)
    is_default = Column(Boolean, default=False, nullable=False)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class User(Base):
    __tablename__ = "users"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    username = Column(String(100), unique=True, nullable=False, index=True)
    password_hash = Column(String(255), nullable=False)
    full_name = Column(String(255), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)
    is_admin = Column(Boolean, default=True, nullable=False)
    role = Column(String(20), default="admin", nullable=False)  # "admin" or "admin_demo"
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)
    last_login_at = Column(DateTime, nullable=True)


class ApiKeyConfig(Base):
    __tablename__ = "api_key_configs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    provider = Column(String(50), default="serpapi", nullable=False)  # serpapi / google_places
    label = Column(String(255), nullable=False)
    api_key = Column(String(255), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    priority = Column(Integer, default=1, nullable=False, index=True)  # 1 = primary, 2 = fallback 1, etc.
    status = Column(String(50), default="active", nullable=False)  # active, exhausted, invalid, error
    requests_used = Column(Integer, default=0, nullable=False)
    quota_limit = Column(Integer, default=250, nullable=False)
    last_used_at = Column(DateTime, nullable=True)
    last_error_message = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)


class ActivityLog(Base):
    """Timeline of all interactions and status changes per lead."""
    __tablename__ = "activity_logs"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    business_id = Column(BigInteger, ForeignKey("businesses.id", ondelete="CASCADE"), nullable=False, index=True)
    action = Column(String(100), nullable=False)  # e.g. "status_changed", "wa_sent", "note_added"
    detail = Column(Text, nullable=True)
    created_by = Column(String(100), nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow, nullable=False)

    # Relationships
    business = relationship("Business", backref="activity_logs")


class DemoToken(Base):
    """Tracks crawl token usage for Admin Demo users (max 3 per 24h window)."""
    __tablename__ = "demo_tokens"

    id = Column(BigInteger, primary_key=True, autoincrement=True)
    user_id = Column(BigInteger, ForeignKey("users.id", ondelete="CASCADE"), nullable=False, index=True)
    tokens_used = Column(Integer, default=0, nullable=False)
    window_start = Column(DateTime, nullable=False)
    max_tokens = Column(Integer, default=3, nullable=False)


