"""
EromeLiker — lightweight session-based liker for Erome albums.

Login flow (mirrors EromeUploader):
  1. Load stored cookies from DB → restore session
  2. Hit /a/{guid} to verify session is still valid
  3. If session expired → full re-login with captcha (ONNX)
  4. POST /album/like with guid
  5. Save updated cookies back to DB
"""

import logging
import random
import time
from datetime import datetime, timezone
from pathlib import Path

import requests
from bs4 import BeautifulSoup

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Shared browser-like headers (same UA as EromeUploader)
# ---------------------------------------------------------------------------
_BASE_HEADERS = {
    "accept-language": "en-US,en;q=0.9",
    "sec-ch-ua": '"Chromium";v="142", "Google Chrome";v="142", "Not_A Brand";v="99"',
    "sec-ch-ua-mobile": "?0",
    "sec-ch-ua-platform": '"Windows"',
    "user-agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/142.0.0.0 Safari/537.36"
    ),
}


class EromeLiker:
    """
    Handles login (cookie-first, ONNX fallback) and album liking for a single account.

    Parameters
    ----------
    email : str
    password : str
    proxy_str : str | None
        Format: ``host:port:user:password``  — same as EromeUploader.
    predict_fn : callable | None
        ONNX captcha prediction function.  Only required when a fresh login
        is needed (i.e. stored cookies are stale or absent).
    captcha_path : Path
        Temp file path for downloading the captcha image.
    """

    def __init__(self, email, password, proxy_str=None, predict_fn=None, captcha_path=None):
        self.email = email
        self.password = password
        self.predict_fn = predict_fn
        self.captcha_path = captcha_path or Path("/tmp/liker_captcha.png")
        self.session = self._build_session(proxy_str)
        self._csrf_token = None  # populated after successful login

    # ------------------------------------------------------------------
    # Session helpers
    # ------------------------------------------------------------------

    def _build_session(self, proxy_str):
        sess = requests.Session()
        if proxy_str:
            try:
                host, port, user, pwd = proxy_str.split(":")
                proxy_url = f"http://{user}:{pwd}@{host}:{port}"
                sess.proxies = {"http": proxy_url, "https": proxy_url}
                r = sess.get("https://api.ipify.org?format=json", timeout=10)
                logger.info(f"[EromeLiker] Proxy IP for {self.email}: {r.json()['ip']}")
            except Exception as e:
                logger.error(f"[EromeLiker] Proxy setup failed for {self.email}: {e}")
                raise
        return sess

    def load_cookies(self, cookies_dict: dict):
        """Restore a previously saved cookie jar into the session."""
        if cookies_dict:
            for name, value in cookies_dict.items():
                self.session.cookies.set(name, value)
            logger.info(f"[EromeLiker] Loaded {len(cookies_dict)} cookies for {self.email}")

    def dump_cookies(self) -> dict:
        """Serialise the current session cookies to a plain dict for DB storage.
        If there are duplicate cookie names, the last value wins (most recently set)."""
        result = {}
        for cookie in self.session.cookies:
            result[cookie.name] = cookie.value
        return result

    # ------------------------------------------------------------------
    # Session validity check
    # ------------------------------------------------------------------

    def is_session_valid(self) -> bool:
        """
        Do a lightweight GET on the Erome homepage and check whether the
        logged-in username appears in the response.  Returns True if the
        session is still active.
        """
        try:
            r = self.session.get(
                "https://www.erome.com/",
                headers={**_BASE_HEADERS, "accept": "text/html,*/*"},
                timeout=15,
                allow_redirects=True,
            )
            # Erome shows the username in the nav when logged in
            soup = BeautifulSoup(r.text, "html.parser")
            # Look for a logout link or a profile link — both indicate an active session
            logged_in = (
                soup.find("a", href="/user/logout") is not None
                or soup.find("a", {"href": lambda h: h and "/user/profile" in h}) is not None
            )
            logger.info(f"[EromeLiker] Session check for {self.email}: {'valid' if logged_in else 'expired'}")
            return logged_in
        except Exception as e:
            logger.warning(f"[EromeLiker] Session validity check failed for {self.email}: {e}")
            return False

    # ------------------------------------------------------------------
    # Full login (with captcha)
    # ------------------------------------------------------------------

    def login(self) -> bool:
        """
        Perform a full username/password + captcha login.
        Requires ``self.predict_fn`` to be set.
        Returns True on success, False on failure.
        """
        if not self.predict_fn:
            logger.error(f"[EromeLiker] No predict_fn provided for {self.email}. Cannot do fresh login.")
            return False

        login_url = "https://www.erome.com/user/login"
        try:
            # 1. GET login page
            r = self.session.get(
                login_url,
                headers={
                    **_BASE_HEADERS,
                    "accept": (
                        "text/html,application/xhtml+xml,application/xml;"
                        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
                    ),
                    "referer": "https://www.erome.com/",
                    "sec-fetch-dest": "document",
                    "sec-fetch-mode": "navigate",
                    "sec-fetch-site": "same-origin",
                    "sec-fetch-user": "?1",
                    "upgrade-insecure-requests": "1",
                },
                timeout=30,
            )
            soup = BeautifulSoup(r.text, "html.parser")

            # 2. Extract CSRF token and captcha URL
            token_input = soup.find("input", {"name": "_token"})
            captcha_img = soup.find("img", {"src": lambda x: x and "captcha/inverse?" in x})

            if not token_input:
                logger.error(f"[EromeLiker] CSRF token not found on login page for {self.email}")
                return False
            if not captcha_img:
                logger.error(f"[EromeLiker] Captcha image not found on login page for {self.email}")
                return False

            token = token_input["value"]
            captcha_url = captcha_img["src"]

            # 3. Download captcha
            cap_r = self.session.get(captcha_url, stream=True, timeout=30)
            with open(self.captcha_path, "wb") as f:
                f.write(cap_r.content)

            # 4. Solve captcha
            captcha_value = self.predict_fn(self.captcha_path)
            logger.info(f"[EromeLiker] Captcha solved for {self.email}: {captcha_value}")

            # 5. POST login
            post_r = self.session.post(
                login_url,
                headers={
                    **_BASE_HEADERS,
                    "accept": (
                        "text/html,application/xhtml+xml,application/xml;"
                        "q=0.9,image/avif,image/webp,image/apng,*/*;q=0.8"
                    ),
                    "content-type": "application/x-www-form-urlencoded",
                    "origin": "https://www.erome.com",
                    "referer": login_url,
                    "sec-fetch-dest": "document",
                    "sec-fetch-mode": "navigate",
                    "sec-fetch-site": "same-origin",
                    "sec-fetch-user": "?1",
                    "upgrade-insecure-requests": "1",
                },
                data={
                    "_token": token,
                    "email": self.email,
                    "password": self.password,
                    "captcha": captcha_value,
                    "remember": "on",
                },
                timeout=30,
            )

            # 6. Check result
            soup = BeautifulSoup(post_r.text, "html.parser")
            errors = [el.text.strip().lower() for el in soup.select("span.help-block") if el.text.strip()]

            if any("captcha is invalid" in e for e in errors):
                logger.error(f"[EromeLiker] Login failed (bad captcha) for {self.email}")
                return False
            if any("credentials do not match" in e for e in errors):
                logger.error(f"[EromeLiker] Login failed (wrong credentials) for {self.email}")
                return False
            if errors:
                logger.error(f"[EromeLiker] Login failed for {self.email}: {' | '.join(errors)}")
                return False

            if any(kw in post_r.url for kw in ("explore", "user/upload", "albums")):
                self._csrf_token = token
                logger.info(f"[EromeLiker] Login successful for {self.email}")
                return True

            logger.error(f"[EromeLiker] Login result unclear for {self.email}. URL: {post_r.url}")
            return False

        except Exception as e:
            logger.exception(f"[EromeLiker] Unexpected error during login for {self.email}: {e}")
            return False
        finally:
            if self.captcha_path.exists():
                self.captcha_path.unlink()

    # ------------------------------------------------------------------
    # Retry login
    # ------------------------------------------------------------------

    def login_with_retry(self, max_attempts=5, base_delay=5) -> bool:
        for attempt in range(1, max_attempts + 1):
            logger.info(f"[EromeLiker] Login attempt {attempt}/{max_attempts} for {self.email}")
            if self.login():
                return True
            if attempt < max_attempts:
                sleep = base_delay * (2 ** (attempt - 1))
                logger.info(f"[EromeLiker] Retrying login in {sleep}s...")
                time.sleep(sleep)
        logger.error(f"[EromeLiker] All login attempts failed for {self.email}")
        return False

    # ------------------------------------------------------------------
    # Like
    # ------------------------------------------------------------------

    def like_album(self, album_guid: str) -> bool:
        """
        POST a like for ``album_guid``.
        Returns True on success (or if already liked), False otherwise.
        """
        # Refresh CSRF token from album page if we don't have one
        if not self._csrf_token:
            self._fetch_csrf_from_album(album_guid)

        like_url = f"https://www.erome.com/album/like/{album_guid}"
        headers = {
            **_BASE_HEADERS,
            "accept": "application/json, text/javascript, */*; q=0.01",
            "origin": "https://www.erome.com",
            "referer": f"https://www.erome.com/a/{album_guid}",
            "x-requested-with": "XMLHttpRequest",
        }
        if self._csrf_token:
            headers["x-csrf-token"] = self._csrf_token

        try:
            r = self.session.post(
                like_url,
                headers=headers,
                timeout=20,
            )
            if r.status_code == 200:
                try:
                    resp = r.json()
                    logger.info(f"[EromeLiker] Like response for {self.email}: {resp}")
                    status = str(resp.get("status", "")).lower()
                    # success / liked = explicit success
                    # error on a 200 = Erome still processed it (usually means already liked)
                    if status in ("success", "liked") or "already" in status or status == "error":
                        logger.info(f"[EromeLiker] {self.email} like accepted for album {album_guid} (status={status}). Likes: {resp.get('likes', '?')}")
                        return True
                    logger.warning(f"[EromeLiker] Unexpected like response for {self.email}: {resp}")
                    return False
                except ValueError:
                    # Non-JSON 200 — treat as success
                    logger.warning(f"[EromeLiker] Non-JSON like response for {self.email}: {r.text[:200]}")
                    return True
            elif r.status_code == 401:
                logger.warning(f"[EromeLiker] 401 on like — session expired for {self.email}")
                return False
            else:
                logger.error(f"[EromeLiker] Like failed for {self.email} — HTTP {r.status_code}: {r.text[:200]}")
                return False
        except Exception as e:
            logger.exception(f"[EromeLiker] Error liking album {album_guid} for {self.email}: {e}")
            return False

    # ------------------------------------------------------------------
    # Internal: grab CSRF from album page
    # ------------------------------------------------------------------

    def _fetch_csrf_from_album(self, album_guid: str):
        try:
            r = self.session.get(
                f"https://www.erome.com/a/{album_guid}",
                headers={
                    **_BASE_HEADERS,
                    "accept": "text/html,*/*",
                    "referer": "https://www.erome.com/",
                },
                timeout=20,
            )
            soup = BeautifulSoup(r.text, "html.parser")
            meta = soup.find("meta", {"name": "csrf-token"})
            if meta:
                self._csrf_token = meta.get("content")
                logger.info(f"[EromeLiker] Got CSRF from album page for {self.email}: {self._csrf_token[:10]}...")
        except Exception as e:
            logger.warning(f"[EromeLiker] Could not fetch CSRF from album page for {self.email}: {e}")
