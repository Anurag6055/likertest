"""
record_upload.py — Utility for manually inserting a row into uploaded_post
(e.g. for backfilling or testing). The uploader (main.py) writes directly
to the DB using its own models — this file is only used within the liker repo.
"""

import logging
from datetime import datetime, timezone

logger = logging.getLogger(__name__)


def record_uploaded_post(album_guid: str, album_title: str | None = None):
    """
    Insert a new row into uploaded_post so the liker Lambda can pick it up.
    Safe to call after every successful upload — uses INSERT OR IGNORE semantics
    so duplicate guids are silently skipped.
    """
    # Import lazily to avoid circular imports and keep the liker self-contained
    from erome_liker.db_models import SessionLocal, UploadedPost

    db = SessionLocal()
    try:
        # Check if guid already recorded (e.g. upload retried and succeeded on 2nd attempt)
        existing = db.query(UploadedPost).filter(UploadedPost.album_guid == album_guid).first()
        if existing:
            logger.info(f"[record_upload] Album {album_guid} already in uploaded_post. Skipping.")
            return

        post = UploadedPost(
            album_guid=album_guid,
            album_title=album_title,
            uploaded_at=datetime.now(timezone.utc),
            liked=False,
        )
        db.add(post)
        db.commit()
        logger.info(f"[record_upload] Recorded uploaded_post for guid={album_guid}")
    except Exception as e:
        logger.error(f"[record_upload] Failed to record upload for {album_guid}: {e}")
        db.rollback()
    finally:
        db.close()
