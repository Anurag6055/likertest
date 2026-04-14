import logging
from datetime import datetime, timezone

from sqlalchemy import (
    Boolean, Column, DateTime, Integer, String, JSON,
    create_engine,
)
from sqlalchemy.orm import sessionmaker, declarative_base

from config import DATABASE_URL

logger = logging.getLogger(__name__)

engine = create_engine(DATABASE_URL, echo=False)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()


class LikerAccount(Base):
    """
    Stores the 10 liker accounts with their cookies.
    Cookies are a JSON-serialised dict of { name: value } pairs from requests.Session.
    """
    __tablename__ = "liker_account"

    id = Column(Integer, primary_key=True)
    email = Column(String, unique=True, nullable=False)
    password = Column(String, nullable=False)
    # proxy format: host:port:user:password  (same as EromeUploader)
    proxy = Column(String, nullable=True)
    # Serialised cookies from requests.Session.cookies (RequestsCookieJar → dict)
    cookies = Column(JSON, nullable=True)
    cookies_updated_at = Column(DateTime(timezone=True), nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    def __repr__(self):
        return f"<LikerAccount {self.email}>"


class UploadedPost(Base):
    """
    Tracks every album uploaded by the main bot.
    The uploader writes a row here after a successful upload.
    The liker Lambda reads rows where liked=False to process.
    """
    __tablename__ = "uploaded_post"

    id = Column(Integer, primary_key=True)
    # Erome album GUID, e.g. "5vVvMumU"
    album_guid = Column(String, unique=True, nullable=False)
    # Human-readable title for logging / Discord notifications
    album_title = Column(String, nullable=True)
    uploaded_at = Column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
    )
    liked = Column(Boolean, default=False, nullable=False)
    liked_at = Column(DateTime(timezone=True), nullable=True)
    # Number of liker accounts that successfully liked (for diagnostics)
    like_count = Column(Integer, default=0, nullable=False)
    
    # Optional link back to the ModelEntry (managed by the uploader bot)
    model_id = Column(Integer, nullable=True)

    def __repr__(self):
        return f"<UploadedPost guid={self.album_guid} liked={self.liked}>"


def create_tables():
    """Creates liker tables if they don't already exist."""
    logger.info("Creating liker database tables...")
    Base.metadata.create_all(bind=engine)
    logger.info("Liker database tables ready.")
