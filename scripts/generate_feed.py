#!/usr/bin/env python3
import re, sys, time
from datetime import datetime, timezone
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup
from feedgen.feed import FeedGenerator

ORIGIN = "https://transformer-circuits.pub/"
OUTFILE = "docs/index.xml"
USER_AGENT = "tc-unofficial-rss/1.0 (+github actions)"

# Regex: top-level article pages like /2025/some-post/index.html (exclude /vis/)
ARTICLE_HREF_RE = re.compile(r"^/20\d{2}/[^/]+/index\.html$")
EXCLUDE_RE = re.compile(r"/vis/")


def get_html(url: str) -> str:
    r = requests.get(url, headers={"User-Agent": USER_AGENT}, timeout=30)
    r.raise_for_status()
    return r.text


def head_last_modified(url: str) -> str | None:
    try:
        r = requests.head(
            url, headers={"User-Agent": USER_AGENT}, timeout=20, allow_redirects=True
        )
        lm = r.headers.get("Last-Modified")
        if lm:
            # Normalize to RFC-2822 string
            dt = datetime.strptime(lm, "%a, %d %b %Y %H:%M:%S %Z")
            return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")
    except Exception:
        pass
    return None


def extract_pubdate_from_doc(soup: BeautifulSoup) -> str | None:
    """
    Try common patterns; fall back to None.
    Returned format should be RFC-2822 (pubDate) in GMT.
    """
    # 1) <meta property="article:published_time" content="2025-09-10T12:34:56Z">
    meta = (
        soup.find("meta", attrs={"property": "article:published_time"})
        or soup.find("meta", attrs={"name": "pubdate"})
        or soup.find("meta", attrs={"name": "date"})
    )
    if meta and meta.get("content"):
        try:
            dt = datetime.fromisoformat(
                meta["content"].replace("Z", "+00:00")
            ).astimezone(timezone.utc)
            return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")
        except Exception:
            pass

    # 2) <time datetime="2025-09-10"> or with time
    t = soup.find("time", attrs={"datetime": True})
    if t:
        try:
            dt = datetime.fromisoformat(
                t["datetime"].replace("Z", "+00:00")
            ).astimezone(timezone.utc)
            return dt.strftime("%a, %d %b %Y %H:%M:%S GMT")
        except Exception:
            pass

    return None


def extract_title(soup: BeautifulSoup) -> str | None:
    if soup.title and soup.title.text:
        return soup.title.text.strip()
    h1 = soup.find("h1")
    if h1 and h1.get_text(strip=True):
        return h1.get_text(strip=True)
    return None


def main():
    home_html = get_html(ORIGIN)
    home = BeautifulSoup(home_html, "lxml")

    # Collect candidate links from homepage
    found = []
    for a in home.find_all("a", href=True):
        href = a["href"].strip()
        if EXCLUDE_RE.search(href):
            continue
        if ARTICLE_HREF_RE.match(href):
            found.append(urljoin(ORIGIN, href))

    # Deduplicate, keep insertion order
    seen = set()
    links = []
    for u in found:
        if u not in seen:
            seen.add(u)
            links.append(u)

    # Optionally cap number of items (e.g., latest 50)
    links = links[:50]

    fg = FeedGenerator()
    fg.id(ORIGIN)
    fg.title("Transformer Circuits (Unofficial)")
    fg.link(href=ORIGIN, rel="alternate")
    fg.link(
        href="https://github.com/", rel="self"
    )  # replaced by final Pages URL automatically by readers
    fg.description(
        "Unofficial RSS feed generated from the homepage of transformer-circuits.pub"
    )
    fg.language("en")
    fg.lastBuildDate(datetime.utcnow())

    session = requests.Session()
    session.headers.update({"User-Agent": USER_AGENT})

    for u in links:
        try:
            r = session.get(u, timeout=30)
            r.raise_for_status()
            soup = BeautifulSoup(r.text, "lxml")

            title = extract_title(soup) or u
            pub = extract_pubdate_from_doc(soup) or head_last_modified(u)
            if not pub:
                pub = datetime.utcnow().strftime("%a, %d %b %Y %H:%M:%S GMT")

            fe = fg.add_entry()
            fe.id(u)
            fe.title(title)
            fe.link(href=u)
            fe.pubDate(pub)

            # Optional: short description (first paragraph)
            p = soup.find("p")
            if p:
                desc = p.get_text(" ", strip=True)
                if desc:
                    fe.description(desc[:1000])

            # Be polite: brief pause to avoid hammering host
            time.sleep(0.3)

        except Exception as e:
            # Skip bad pages, but continue
            sys.stderr.write(f"[warn] {u}: {e}\n")

    # Ensure output dir exists
    import os

    os.makedirs("docs", exist_ok=True)
    fg.rss_file(OUTFILE, pretty=True)
    print(f"Wrote {OUTFILE} with {len(fg.entry())} items.")


if __name__ == "__main__":
    main()
