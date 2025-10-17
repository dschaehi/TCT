#!/usr/bin/env python3
"""
generate_feed.py — Unofficial RSS for https://transformer-circuits.pub/

Version 1.5 (final fixes)
-------------------------
- Robust UTF-8 repair: if the response shows mojibake (e.g., “â€””, “â€™”), re-decode as latin1->utf-8.
- HTML entity decoding for clean punctuation.
- External links filtered (keep only transformer-circuits.pub).
- Wider item discovery (.note cards + year-based links under <main>).
- Per-article date via meta/time or Last-Modified (fallback now UTC).

Dependencies
------------
pip install beautifulsoup4 requests feedgen lxml

Usage
-----
python scripts/generate_feed.py
"""

from __future__ import annotations

import os
import sys
import time
import html
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import Optional, Tuple, List
from urllib.parse import urljoin, urlparse

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

ORIGIN = "https://transformer-circuits.pub/"
OUTFILE = "docs/index.xml"
USER_AGENT = "tc-unofficial-rss/1.5 (+github actions; contact: N/A)"

# How many items to include at most (set to None to include all found on homepage)
MAX_ITEMS: Optional[int] = 100

# Delay between fetching individual article pages (be polite)
REQUEST_DELAY_SECONDS = 0.2


def clean_text(s: str) -> str:
    """HTML-unescape and strip."""
    if not s:
        return s
    return html.unescape(s).strip()


def get_html(url: str, session: Optional[requests.Session] = None) -> str:
    """Fetch URL and return best-effort UTF-8 text, repairing mojibake if needed."""
    s = session or requests.Session()
    r = s.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    # Prefer UTF-8 but don't trust headers blindly
    r.encoding = r.encoding or "utf-8"
    r.raise_for_status()
    html_text = r.text

    # Auto-repair common mojibake: UTF-8 bytes decoded as Latin-1
    # Heuristic: presence of these sequences suggests mis-decoding
    if "â€" in html_text or "Ã" in html_text or "â€™" in html_text:
        try:
            html_text = html_text.encode("latin1").decode("utf-8")
        except Exception:
            # If repair fails, fallback to original
            pass

    return html_text


def get_head_last_modified(url: str, session: Optional[requests.Session] = None) -> Optional[datetime]:
    s = session or requests.Session()
    try:
        r = s.head(url, headers={"User-Agent": USER_AGENT}, timeout=20, allow_redirects=True)
        lm = r.headers.get("Last-Modified")
        if lm:
            try:
                dt = parsedate_to_datetime(lm)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                else:
                    dt = dt.astimezone(timezone.utc)
                return dt
            except Exception:
                return None
    except Exception:
        return None
    return None


def extract_meta_datetime(soup: BeautifulSoup) -> Optional[datetime]:
    """Try to extract a publication datetime from common meta/time tags and return tz-aware UTC."""
    candidates = [
        ("meta", {"property": "article:published_time"}),
        ("meta", {"name": "pubdate"}),
        ("meta", {"name": "date"}),
        ("meta", {"property": "og:updated_time"}),
        ("meta", {"property": "article:modified_time"}),
    ]
    for tag, attrs in candidates:
        el = soup.find(tag, attrs=attrs)
        if el and el.get("content"):
            dt = _parse_to_aware_dt(el["content"])
            if dt:
                return dt

    t = soup.find("time", attrs={"datetime": True})
    if t:
        dt = _parse_to_aware_dt(t["datetime"])
        if dt:
            return dt

    return None


def _parse_to_aware_dt(dt_str: str) -> Optional[datetime]:
    """Parse ISO 8601 or RFC-2822 into tz-aware UTC datetime."""
    try:
        dt = parsedate_to_datetime(dt_str)
        if dt:
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            else:
                dt = dt.astimezone(timezone.utc)
            return dt
    except Exception:
        pass

    try:
        iso = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        return None


def _same_host(url: str, origin: str = ORIGIN) -> bool:
    parsed = urlparse(url)
    if not parsed.netloc:
        return True  # relative to origin
    return parsed.netloc == urlparse(origin).netloc


def collect_home_items(home_soup: BeautifulSoup) -> List[Tuple[str, str, str]]:
    """
    Return a list of (url, title, description) found on the homepage.

    Strategy:
      1) Card-style notes (.note):
         - Item: a.note[href]
         - Title: h3
         - Description: div[class*='description']
      2) Year-based internal links in the main content:
         - main a[href^='/20']
    External links are filtered out (keep only transformer-circuits.pub).
    """
    items: List[Tuple[str, str, str]] = []

    # 1) .note cards
    for a in home_soup.select("a.note[href]"):
        href = a.get("href", "").strip()
        if not href:
            continue
        url = urljoin(ORIGIN, href)
        if not _same_host(url):
            continue

        title_el = a.select_one("h3")
        raw_title = title_el.get_text(strip=True) if title_el else url
        title = clean_text(raw_title)

        desc_el = a.select_one("div[class*='description']")
        raw_desc = desc_el.get_text(" ", strip=True) if desc_el else ""
        description = clean_text(raw_desc)

        items.append((url, title, description))

    # 2) Year-based internal links under main
    for a in home_soup.select("main a[href^='/20']"):
        href = a.get("href", "").strip()
        if not href:
            continue
        url = urljoin(ORIGIN, href)
        if not _same_host(url):
            continue

        # Skip if already captured by .note
        if any(url == it[0] for it in items):
            continue

        raw_title = a.get_text(" ", strip=True) or url
        title = clean_text(raw_title)
        description = ""  # We'll try to fetch per-page later
        items.append((url, title, description))

    # Deduplicate while preserving order
    seen = set()
    deduped: List[Tuple[str, str, str]] = []
    for u, t, d in items:
        if u in seen:
            continue
        seen.add(u)
        deduped.append((u, t, d))

    if MAX_ITEMS:
        deduped = deduped[:MAX_ITEMS]

    return deduped


def main() -> None:
    os.makedirs(os.path.dirname(OUTFILE), exist_ok=True)

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    # Fetch homepage and parse items
    home_html = get_html(ORIGIN, session=session)
    home_soup = BeautifulSoup(home_html, "lxml")
    items = collect_home_items(home_soup)

    fg = FeedGenerator()
    fg.id(ORIGIN)
    fg.title("Transformer Circuits (Unofficial)")
    fg.link(href=ORIGIN, rel="alternate")
    # If you know your final feed URL on GitHub Pages, you can set rel='self' here.
    # fg.link(href="https://<your-username>.github.io/<your-repo>/index.xml", rel="self")
    fg.description("Unofficial RSS feed generated from the homepage of transformer-circuits.pub")
    fg.language("en")
    fg.lastBuildDate(datetime.now(timezone.utc))  # tz-aware

    count = 0
    # Optional: collect entries to sort newest-first
    entries: List[Tuple[str, str, str, datetime]] = []

    for (url, title, description) in items:
        if not _same_host(url):
            continue

        pub_dt = None

        # Try to read per-article metadata and maybe a better description
        try:
            article_html = get_html(url, session=session)
            article_soup = BeautifulSoup(article_html, "lxml")

            # Prefer meta/time dates
            pub_dt = extract_meta_datetime(article_soup)

            # If description was empty, try first real paragraph from article
            if not description:
                p = article_soup.find("p")
                if p:
                    description = clean_text(p.get_text(" ", strip=True)[:1000])
        except Exception:
            pub_dt = None

        # Try Last-Modified header
        if pub_dt is None:
            pub_dt = get_head_last_modified(url, session=session)

        # Fallback to now (UTC)
        if pub_dt is None:
            pub_dt = datetime.now(timezone.utc)

        entries.append((url, clean_text(title), clean_text(description), pub_dt))
        count += 1
        time.sleep(REQUEST_DELAY_SECONDS)

    # Sort newest first (optional, but nice for readers)
    entries.sort(key=lambda x: x[3], reverse=True)

    for url, title, description, pub_dt in entries:
        fe = fg.add_entry()
        fe.id(url)
        fe.link(href=url)
        fe.title(title)
        if description:
            fe.description(description)
        fe.pubDate(pub_dt)

    fg.rss_file(OUTFILE, pretty=True)
    print(f"Wrote {OUTFILE} with {count} items.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        sys.stderr.write(f"ERROR: {e}\n")
        sys.exit(1)
