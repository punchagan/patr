"""Resolve and download GIFs pasted from Tenor/Giphy links, so they're
stored locally like any other image rather than hotlinked.

No API key needed: a share-page link (e.g. tenor.com/view/...) has a
public og:image meta tag pointing at the actual media file — scraping
that is enough, and avoids tying setup to a Google API key.
"""

import secrets
import urllib.parse
import urllib.request
from pathlib import Path

from bs4 import BeautifulSoup

ALLOWED_HOSTS = ("tenor.com", "giphy.com")
DIRECT_MEDIA_EXTENSIONS = {"gif", "webp", "mp4"}


def _is_allowed_host(url: str) -> bool:
    """Return True if url's host is tenor.com/giphy.com or a subdomain
    (e.g. media.tenor.com) — restricts fetching to these two GIF services,
    not arbitrary URLs."""
    host = urllib.parse.urlsplit(url).netloc.lower()
    return any(host == h or host.endswith(f".{h}") for h in ALLOWED_HOSTS)


def _looks_like_direct_media(url: str) -> bool:
    path = urllib.parse.urlsplit(url).path.lower()
    ext = path.rsplit(".", 1)[-1] if "." in path else ""
    return ext in DIRECT_MEDIA_EXTENSIONS


def resolve_media_url(url: str) -> str | None:
    """Return the direct GIF/webp media URL for a pasted Tenor/Giphy link.

    If `url` already points at a media file, return it unchanged. Otherwise
    treat it as a share-page link and scrape its og:image meta tag — no API
    key needed, since this is public page HTML. Returns None if the host
    isn't allow-listed or nothing could be resolved.
    """
    if not _is_allowed_host(url):
        return None
    if _looks_like_direct_media(url):
        return url
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=5) as r:
            html = r.read()
    except Exception:
        return None
    soup = BeautifulSoup(html, "html.parser")
    tag = soup.find("meta", property="og:image")
    if not tag or not tag.get("content"):
        return None
    media_url = str(tag["content"])
    return media_url if _is_allowed_host(media_url) else None


def download_gif(url: str, dest_dir: Path) -> str | None:
    """Resolve `url` to a direct media URL and download it into dest_dir,
    returning the saved filename, or None on any failure."""
    media_url = resolve_media_url(url)
    if media_url is None:
        return None
    path = urllib.parse.urlsplit(media_url).path
    ext = path.rsplit(".", 1)[-1].lower() if "." in path else "gif"
    if ext not in DIRECT_MEDIA_EXTENSIONS:
        ext = "gif"
    filename = f"{secrets.token_hex(6)}.{ext}"
    try:
        req = urllib.request.Request(media_url, headers={"User-Agent": "Mozilla/5.0"})
        with urllib.request.urlopen(req, timeout=10) as r:
            data = r.read()
    except Exception:
        return None
    dest_dir.mkdir(exist_ok=True)
    (dest_dir / filename).write_bytes(data)
    return filename
