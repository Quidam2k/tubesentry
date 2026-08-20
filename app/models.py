from datetime import datetime

from sqlalchemy import Column, Integer, String, Text, DateTime, Float, ForeignKey, Boolean, Enum as SAEnum
from sqlalchemy.orm import relationship
import enum

from app.database import Base


class SummaryScope(enum.Enum):
    VIDEO = "video"
    CHANNEL = "channel"
    ACCOUNT = "account"


class AlertType(enum.Enum):
    KEYWORD = "keyword"
    AI_CLASSIFICATION = "ai_classification"


class VideoSource(enum.Enum):
    SUBSCRIPTION = "subscription"  # From a subscribed channel
    UPLOAD = "upload"              # Posted by the monitored account


class Account(Base):
    """A monitored YouTube account (one per kid/user)."""
    __tablename__ = "accounts"

    id = Column(Integer, primary_key=True)
    name = Column(String(255), nullable=False)  # Display name (e.g., "Jake")
    youtube_handle = Column(String(255), nullable=True)  # @handle if known
    notes = Column(Text, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    channels = relationship("Channel", back_populates="account", cascade="all, delete-orphan")
    alerts = relationship("Alert", back_populates="account", cascade="all, delete-orphan")
    summaries = relationship(
        "Summary",
        back_populates="account",
        foreign_keys="Summary.account_id",
        cascade="all, delete-orphan",
    )


class Channel(Base):
    """A YouTube channel being monitored."""
    __tablename__ = "channels"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    youtube_channel_id = Column(String(255), nullable=True)  # UC... ID
    channel_url = Column(String(512), nullable=False)
    channel_name = Column(String(255), nullable=True)
    is_account_uploads = Column(Boolean, default=False)  # True if this is the account's own channel
    last_scanned_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account", back_populates="channels")
    videos = relationship("Video", back_populates="channel", cascade="all, delete-orphan")
    summaries = relationship(
        "Summary",
        back_populates="channel",
        foreign_keys="Summary.channel_id",
        cascade="all, delete-orphan",
    )


class Video(Base):
    """An individual YouTube video."""
    __tablename__ = "videos"

    id = Column(Integer, primary_key=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=False)
    youtube_video_id = Column(String(20), nullable=False, unique=True)
    title = Column(String(512), nullable=True)
    description = Column(Text, nullable=True)
    duration_seconds = Column(Integer, nullable=True)
    upload_date = Column(DateTime, nullable=True)
    source = Column(SAEnum(VideoSource), default=VideoSource.SUBSCRIPTION)
    processed = Column(Boolean, default=False)  # True after transcription + summarization
    created_at = Column(DateTime, default=datetime.utcnow)

    channel = relationship("Channel", back_populates="videos")
    transcript = relationship("Transcript", back_populates="video", uselist=False, cascade="all, delete-orphan")
    summary = relationship(
        "Summary",
        back_populates="video",
        foreign_keys="Summary.video_id",
        uselist=False,
        cascade="all, delete-orphan",
    )
    notifications = relationship("Notification", back_populates="video", cascade="all, delete-orphan")


class Transcript(Base):
    """Full text transcript. Sourced from a YouTube caption track (manual or
    auto-generated) when available, else from local Whisper transcription."""
    __tablename__ = "transcripts"

    id = Column(Integer, primary_key=True)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False, unique=True)
    text = Column(Text, nullable=False)
    language = Column(String(10), nullable=True)
    # How this transcript was obtained: 'caption_manual', 'caption_auto', or
    # 'whisper'. Nullable for back-compat with rows created before provenance
    # tracking existed. `is_auto` flags lower-confidence sources (auto captions)
    # so they can be re-done with Whisper later if quality demands it.
    source = Column(String(20), nullable=True)
    is_auto = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    video = relationship("Video", back_populates="transcript")


class Summary(Base):
    """AI-generated summary. Can be per-video, per-channel, or per-account."""
    __tablename__ = "summaries"

    id = Column(Integer, primary_key=True)
    scope = Column(SAEnum(SummaryScope), nullable=False)

    # Exactly one of these should be set, depending on scope
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=True, unique=True)
    channel_id = Column(Integer, ForeignKey("channels.id"), nullable=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=True)

    text = Column(Text, nullable=False)
    model_used = Column(String(255), nullable=True)  # Which LLM generated this
    created_at = Column(DateTime, default=datetime.utcnow)

    video = relationship("Video", back_populates="summary", foreign_keys=[video_id])
    channel = relationship("Channel", back_populates="summaries", foreign_keys=[channel_id])
    account = relationship("Account", back_populates="summaries", foreign_keys=[account_id])


class Alert(Base):
    """A user-defined alert rule."""
    __tablename__ = "alerts"

    id = Column(Integer, primary_key=True)
    account_id = Column(Integer, ForeignKey("accounts.id"), nullable=False)
    alert_type = Column(SAEnum(AlertType), nullable=False)
    # For KEYWORD: the keyword/phrase to match
    # For AI_CLASSIFICATION: natural language description of what to flag
    criteria = Column(Text, nullable=False)
    enabled = Column(Boolean, default=True)
    created_at = Column(DateTime, default=datetime.utcnow)

    account = relationship("Account", back_populates="alerts")
    notifications = relationship("Notification", back_populates="alert", cascade="all, delete-orphan")


class Notification(Base):
    """A triggered alert — shown in the web UI."""
    __tablename__ = "notifications"

    id = Column(Integer, primary_key=True)
    alert_id = Column(Integer, ForeignKey("alerts.id"), nullable=False)
    video_id = Column(Integer, ForeignKey("videos.id"), nullable=False)
    snippet = Column(Text, nullable=True)  # The matching text/context
    read = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.utcnow)

    alert = relationship("Alert", back_populates="notifications")
    video = relationship("Video", back_populates="notifications")
