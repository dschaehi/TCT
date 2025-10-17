#!/usr/bin/env python3
"""
generate_feed.py — Build an unofficial RSS feed for https://transformer-circuits.pub/

How it works
------------
- Scrapes the homepage and finds items via CSS selector: a.note (with h3 title and a description div).
- Builds <item> entries with title, link, and description.
- Attempts to find a publication date by fetching the article page (looking for common meta/time tags),
  else falls back to the HTTP Last-Modified header, else current UTC time.
- Writes RSS XML to docs/index.xml (create the docs/ folder in your repo).

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
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
from typing import List, Optional, Tuple
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

ORIGIN = "https://transformer-circuits.pub/"
OUTFILE = "docs/index.xml"
USER_AGENT = "tc-unofficial-rss/1.1 (+github actions; contact: N/A)"

# How many items to include at most (set to None to include all found on homepage)
MAX_ITEMS: Optional[int] = 50

# Delay between fetching individual article pages (be polite)
REQUEST_DELAY_SECONDS = 0.2


def get_html(url: str, session: Optional[requests.Session] = None) -> str:
    s = session or requests.Session()
    r = s.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    return r.text


def get_head_last_modified(
    url: str, session: Optional[requests.Session] = None
) -> Optional[datetime]:
    s = session or requests.Session()
    try:
        r = s.head(
            url, headers={"User-Agent": USER_AGENT}, timeout=20, allow_redirects=True
        )
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
    """
    Try to extract a publication datetime from common meta/time tags, return tz-aware UTC.
    """
    # <meta property="article:published_time" content="2025-09-10T12:34:56Z">
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

    # <time datetime="...">
    t = soup.find("time", attrs={"datetime": True})
    if t:
        dt = _parse_to_aware_dt(t["datetime"])
        if dt:
            return dt

    return None


def _parse_to_aware_dt(dt_str: str) -> Optional[datetime]:
    """
    Parse ISO 8601 or RFC-2822-ish into tz-aware UTC datetime.
    """
    # Try RFC 2822 via email.utils first
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

    # Then try ISO 8601
    try:
        # Normalize trailing Z
        iso = dt_str.replace("Z", "+00:00")
        dt = datetime.fromisoformat(iso)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt
    except Exception:
        return None


def collect_home_items(home_soup: BeautifulSoup) -> List[Tuple[str, str, str]]:
    """
    Return a list of (url, title, description) found on the homepage.
    Uses FiveFilters-learned selectors:
      - Item: a.note
      - Title: h3
      - Description: div[class*='description']
    """
    items: List[Tuple[str, str, str]] = []
    for a in home_soup.select("a.note[href]"):
        href = a.get("href", "").strip()
        if not href:
            continue
        url = urljoin(ORIGIN, href)

        title_el = a.select_one("h3")
        title = title_el.get_text(strip=True) if title_el else url

        desc_el = a.select_one("div[class*='description']")
        description = desc_el.get_text(" ", strip=True) if desc_el else ""

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
    fg.description(
        "Unofficial RSS feed generated from the homepage of transformer-circuits.pub"
    )
    fg.language("en")
    fg.lastBuildDate(datetime.now(timezone.utc))  # tz-aware

    count = 0
    for url, title, description in items:
        pub_dt = None

        # Try to read per-article metadata
        try:
            article_html = get_html(url, session=session)
            article_soup = BeautifulSoup(article_html, "lxml")
            pub_dt = extract_meta_datetime(article_soup)
        except Exception:
            pub_dt = None

        # Try Last-Modified header
        if pub_dt is None:
            pub_dt = get_head_last_modified(url, session=session)

        # Fallback to now (UTC)
        if pub_dt is None:
            pub_dt = datetime.now(timezone.utc)

        fe = fg.add_entry()
        fe.id(url)
        fe.link(href=url)
        fe.title(title)
        if description:
            fe.description(description)
        fe.pubDate(pub_dt)

        count += 1
        # Be polite
        time.sleep(REQUEST_DELAY_SECONDS)

    fg.rss_file(OUTFILE, pretty=True)
    print(f"Wrote {OUTFILE} with {count} items.")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        sys.stderr.write(f"ERROR: {e}\n")
        sys.exit(1)
