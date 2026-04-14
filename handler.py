"""
Lambda handler — polls DB every 5 minutes for unliked posts and likes them.

EventBridge rule:  rate(5 minutes)
Environment variables required:
  DATABASE_URL
  ONNX_MODEL_PATH   (default: weights/model_0.7200.onnx)
  LABELS_FILE       (default: labels.json)
  DISCORD_WEBHOOK   (optional)
  LIKE_DELAY_SECONDS, LIKE_SLEEP_MIN, LIKE_SLEEP_MAX, COOKIE_MAX_AGE_SECONDS
"""

import json
import logging
import random
import sys
import time
from datetime import datetime, timezone, timedelta
from pathlib import Path

import requests

# Ensure the liker package root is on sys.path when running as Lambda
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    CAPTCHA_PATH,
    COOKIE_MAX_AGE_SECONDS,
    DISCORD_WEBHOOK,
    IMG_HEIGHT,
    IMG_WIDTH,
    LABELS_FILE,
    LIKE_DELAY_SECONDS,
    LIKE_SLEEP_MAX,
    LIKE_SLEEP_MIN,
    ONNX_MODEL_PATH,
)
from db_models import LikerAccount, SessionLocal, UploadedPost, create_tables
from erome_liker import EromeLiker
from sqlalchemy import text

# ---------------------------------------------------------------------------
# Logging
# ---------------------------------------------------------------------------
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Lazy-loaded ONNX pipeline (only instantiated when a fresh login is needed)
# ---------------------------------------------------------------------------
_predict_fn = None


def _get_predict_fn():
    global _predict_fn
    if _predict_fn is None:
        logger.info("[Handler] Loading ONNX captcha pipeline...")
        # Import here so the Lambda can still run without ONNX when cookies are fresh
        from inference_liker import create_onnx_inference_pipeline  # local copy
        _predict_fn = create_onnx_inference_pipeline(ONNX_MODEL_PATH, IMG_WIDTH, IMG_HEIGHT)
        if not _predict_fn:
            raise RuntimeError("Failed to initialise ONNX captcha pipeline.")
        logger.info("[Handler] ONNX pipeline ready.")
    return _predict_fn


# ---------------------------------------------------------------------------
# Discord helper
# ---------------------------------------------------------------------------

def _notify(message: str, color: int = 3447003):
    if not DISCORD_WEBHOOK:
        return
    try:
        requests.post(
            DISCORD_WEBHOOK,
            headers={"Content-Type": "application/json"},
            data=json.dumps({"embeds": [{"description": message, "color": color}]}),
            timeout=10,
        )
    except Exception as e:
        logger.warning(f"[Handler] Discord notification failed: {e}")


# ---------------------------------------------------------------------------
# Cookie helpers
# ---------------------------------------------------------------------------

def _cookies_are_fresh(account: LikerAccount) -> bool:
    """Return True if stored cookies exist and are younger than COOKIE_MAX_AGE_SECONDS."""
    if not account.cookies or not account.cookies_updated_at:
        return False
    updated_at = account.cookies_updated_at
    # SQLite returns naive datetimes — treat them as UTC
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)
    age = (datetime.now(timezone.utc) - updated_at).total_seconds()
    return age < COOKIE_MAX_AGE_SECONDS


def _save_cookies(db_session, account: LikerAccount, cookies_dict: dict):
    account.cookies = cookies_dict
    account.cookies_updated_at = datetime.now(timezone.utc)
    db_session.commit()
    logger.info(f"[Handler] Saved {len(cookies_dict)} cookies for {account.email}")


# ---------------------------------------------------------------------------
# Core: ensure session is valid, re-login if needed
# ---------------------------------------------------------------------------

def _get_valid_liker(db_session, account: LikerAccount) -> EromeLiker | None:
    """
    Returns a logged-in EromeLiker for this account, or None if login fails.
    Uses stored cookies first; falls back to full ONNX login if expired.
    """
    predict_fn = None  # don't load ONNX unless needed

    liker = EromeLiker(
        email=account.email,
        password=account.password,
        proxy_str=account.proxy or None,
        predict_fn=None,  # set below only if needed
        captcha_path=CAPTCHA_PATH,
    )

    # --- Try stored cookies first ---
    if _cookies_are_fresh(account) and account.cookies:
        liker.load_cookies(account.cookies)

        # If cookies are very recent (< 2 hours), trust them without an HTTP check
        updated_at = account.cookies_updated_at
        if updated_at.tzinfo is None:
            updated_at = updated_at.replace(tzinfo=timezone.utc)
        cookie_age = (datetime.now(timezone.utc) - updated_at).total_seconds()

        if cookie_age < 7200:
            logger.info(f"[Handler] Cookies are recent ({cookie_age/60:.0f}min old), trusting without session check for {account.email}")
            return liker

        if liker.is_session_valid():
            logger.info(f"[Handler] Cookie session valid for {account.email}")
            return liker
        logger.info(f"[Handler] Cookie session invalid for {account.email} (age: {cookie_age/3600:.1f}h). Re-logging in...")
    else:
        logger.info(f"[Handler] No fresh cookies for {account.email}. Logging in fresh...")

    # --- Fall back to full login ---
    try:
        predict_fn = _get_predict_fn()
    except RuntimeError as e:
        logger.error(f"[Handler] Cannot load ONNX for re-login: {e}")
        return None

    liker.predict_fn = predict_fn
    if liker.login_with_retry(max_attempts=5):
        _save_cookies(db_session, account, liker.dump_cookies())
        return liker

    logger.error(f"[Handler] Login failed for {account.email} after retries.")
    return None


# ---------------------------------------------------------------------------
# Core: like a single post with all accounts
# ---------------------------------------------------------------------------

def _like_post(db_session, post: UploadedPost, accounts: list[LikerAccount]):
    """Like ``post`` using every active liker account."""
    logger.info(f"[Handler] Liking album {post.album_guid} ({post.album_title})...")
    
    # Try to fetch model name using a raw SQL approach similar to routes.py
    model_name_str = ""
    if getattr(post, 'model_id', None):
        try:
            result = db_session.execute(
                text("SELECT name FROM model_entry WHERE id = :id LIMIT 1"),
                {"id": post.model_id}
            )
            row = result.fetchone()
            if row:
                model_name_str = f" for `{row[0]}`"
        except Exception as e:
            logger.warning(f"[Handler] Could not fetch model name for model_id {post.model_id}: {e}")

    like_count = 0

    for account in accounts:
        liker = _get_valid_liker(db_session, account)
        if liker is None:
            logger.warning(f"[Handler] Skipping account {account.email} (could not establish session)")
            continue

        success = liker.like_album(post.album_guid)
        if success:
            like_count += 1
            # Persist refreshed cookies (session may have been renewed with new tokens)
            _save_cookies(db_session, account, liker.dump_cookies())
            
            _notify(
                f"❤️ **Liked:** `Model: {model_name_str} | Album title: {post.album_title} | Album guid: {post.album_guid}` with account `{account.email}`",
                color=65280
            )

        # Randomised delay between accounts to avoid burst detection
        sleep_s = random.uniform(LIKE_SLEEP_MIN, LIKE_SLEEP_MAX)
        logger.info(f"[Handler] Sleeping {sleep_s:.1f}s before next account...")
        time.sleep(sleep_s)

    # Mark post as liked regardless of partial success
    post.liked = True
    post.liked_at = datetime.now(timezone.utc)
    post.like_count = like_count
    db_session.commit()

    logger.info(f"[Handler] Album {post.album_guid} liked by {like_count}/{len(accounts)} accounts.")
    _notify(
        f"❤️ **Liked:** `Model: {model_name_str} | Album title: {post.album_title} | Album guid: {post.album_guid}` — "
        f"{like_count}/{len(accounts)} accounts succeeded.",
        color=65280 if like_count == len(accounts) else 16776960,
    )


# ---------------------------------------------------------------------------
# Lambda entry point
# ---------------------------------------------------------------------------

def handler(event, context):
    logger.info("[Handler] Liker Lambda invoked.")

    # Ensure tables exist (idempotent)
    create_tables()

    db = SessionLocal()
    try:
        # --- Fetch active liker accounts ---
        accounts = db.query(LikerAccount).filter(LikerAccount.is_active == True).all()
        if not accounts:
            logger.warning("[Handler] No active liker accounts found in DB. Exiting.")
            return {"status": "no_accounts"}

        logger.info(f"[Handler] {len(accounts)} active liker account(s) loaded.")

        # --- Fetch posts due for liking ---
        cutoff = datetime.now(timezone.utc) - timedelta(seconds=LIKE_DELAY_SECONDS)
        pending_posts = (
            db.query(UploadedPost)
            .filter(
                UploadedPost.liked == False,
                UploadedPost.uploaded_at <= cutoff,
            )
            .order_by(UploadedPost.uploaded_at.asc())
            .all()
        )

        if not pending_posts:
            logger.info("[Handler] No posts pending liking. Exiting.")
            return {"status": "nothing_to_do"}

        logger.info(f"[Handler] {len(pending_posts)} post(s) to like.")

        for post in pending_posts:
            try:
                _like_post(db, post, accounts)
            except Exception as e:
                logger.exception(f"[Handler] Error liking post {post.album_guid}: {e}")
                _notify(f"❌ **Like Error:** `{post.album_guid}`: `{e}`", color=16711680)
                # Don't mark as liked — it will be retried on the next 5-min tick

        return {"status": "ok", "processed": len(pending_posts)}

    except Exception as e:
        logger.exception(f"[Handler] Fatal error in liker Lambda: {e}")
        _notify(f"❌ **Liker Lambda Fatal Error:** `{e}`", color=16711680)
        return {"status": "error", "message": str(e)}
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Local testing
# ---------------------------------------------------------------------------
if __name__ == "__main__":
    result = handler({}, None)
    print(result)
