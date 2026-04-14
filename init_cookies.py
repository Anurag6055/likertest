"""
init_cookies.py — One-time (or periodic) script to login all liker accounts
and store their cookies in the database.

Run this:
  - Once before deploying the liker Lambda, to pre-populate cookies
  - Any time you add a new liker account to the DB
  - As a scheduled task (e.g. weekly) to proactively refresh cookies

Usage:
    python init_cookies.py

Requires DATABASE_URL, ONNX_MODEL_PATH, LABELS_FILE env vars (or .env file).
"""

import logging
import sys
import time
from datetime import datetime, timezone
from pathlib import Path

# Allow running from the erome_liker folder directly
sys.path.insert(0, str(Path(__file__).parent))

from config import (
    CAPTCHA_PATH,
    IMG_HEIGHT,
    IMG_WIDTH,
    LABELS_FILE,
    ONNX_MODEL_PATH,
)
from db_models import LikerAccount, SessionLocal, create_tables
from erome_liker import EromeLiker

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(levelname)s - %(message)s",
)
logger = logging.getLogger(__name__)


def main():
    logger.info("=== Liker Cookie Initialiser ===")

    # Ensure tables exist
    create_tables()

    # Load ONNX pipeline (required for captcha solving during login)
    logger.info("Loading ONNX captcha pipeline...")
    from inference_liker import create_onnx_inference_pipeline
    predict_fn = create_onnx_inference_pipeline(ONNX_MODEL_PATH, IMG_WIDTH, IMG_HEIGHT)
    if not predict_fn:
        logger.critical("Failed to load ONNX pipeline. Aborting.")
        sys.exit(1)
    logger.info("ONNX pipeline ready.")

    db = SessionLocal()
    try:
        accounts = db.query(LikerAccount).filter(LikerAccount.is_active == True).all()

        if not accounts:
            logger.warning("No active liker accounts found in DB.")
            logger.info("Add accounts via SQL or a seed script, then re-run this.")
            return

        logger.info(f"Found {len(accounts)} active account(s). Starting login...")

        success_count = 0
        for acc in accounts:
            logger.info(f"--- Processing account: {acc.email} ---")

            liker = EromeLiker(
                email=acc.email,
                password=acc.password,
                proxy_str=acc.proxy or None,
                predict_fn=predict_fn,
                captcha_path=CAPTCHA_PATH,
            )

            logged_in = liker.login_with_retry(max_attempts=5, base_delay=5)
            if logged_in:
                cookies = liker.dump_cookies()
                acc.cookies = cookies
                acc.cookies_updated_at = datetime.now(timezone.utc)
                db.commit()
                logger.info(f"[OK] Cookies saved for {acc.email} ({len(cookies)} cookies)")
                success_count += 1
            else:
                logger.error(f"[FAIL] Could not login {acc.email}. Cookies NOT updated.")

            # Delay between accounts to avoid rate limiting
            if acc != accounts[-1]:
                logger.info("Sleeping 10s before next account...")
                time.sleep(10)

        logger.info(f"=== Done: {success_count}/{len(accounts)} accounts successfully logged in ===")

    finally:
        db.close()


if __name__ == "__main__":
    main()
