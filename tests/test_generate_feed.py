from __future__ import annotations

import importlib.util
from datetime import datetime, timezone
from email.utils import parsedate_to_datetime
import io
from pathlib import Path
import sys
import tempfile
import unittest
import xml.etree.ElementTree as ET
from unittest.mock import patch


MODULE_PATH = Path(__file__).resolve().parents[1] / "scripts" / "generate_feed.py"


def load_generate_feed():
    spec = importlib.util.spec_from_file_location("generate_feed", MODULE_PATH)
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


class GenerateFeedTests(unittest.TestCase):
    def test_collect_home_items_parses_structured_paper_cards(self) -> None:
        generate_feed = load_generate_feed()
        soup = generate_feed.BeautifulSoup(
            """
            <main>
              <div class="date">October 2025</div>
              <a class="paper" href="/2025/introspection/index.html">
                <h3>Emergent Introspective Awareness in Large Language Models</h3>
                <div class="byline">Lindsey, 2025</div>
                <div class="description">We find evidence that language models can introspect.</div>
              </a>
            </main>
            """,
            "lxml",
        )

        items = generate_feed.collect_home_items(soup)

        self.assertEqual(len(items), 1)
        self.assertEqual(
            items[0],
            (
                "https://transformer-circuits.pub/2025/introspection/index.html",
                "Emergent Introspective Awareness in Large Language Models Lindsey, 2025",
                "We find evidence that language models can introspect.",
                datetime(2025, 10, 1, tzinfo=timezone.utc),
            ),
        )

    def test_main_writes_newest_items_first(self) -> None:
        generate_feed = load_generate_feed()
        article_html = "<html><head></head><body><p>Description from article.</p></body></html>"
        home_html = """
            <main>
              <a class="note" href="/2026/new/index.html">
                <h3>New Article</h3>
                <div class="description">New description.</div>
              </a>
              <a class="note" href="/2025/old/index.html">
                <h3>Old Article</h3>
                <div class="description">Old description.</div>
              </a>
            </main>
        """

        def fake_get_html(url, session=None):
            if url == generate_feed.ORIGIN:
                return home_html
            return article_html

        def fake_last_modified(url, session=None):
            if url.endswith("/2026/new/index.html"):
                return datetime(2026, 4, 8, tzinfo=timezone.utc)
            return datetime(2025, 1, 1, tzinfo=timezone.utc)

        with tempfile.TemporaryDirectory() as tmpdir:
            outfile = Path(tmpdir) / "index.xml"
            with patch.object(generate_feed, "OUTFILE", str(outfile)):
                with patch.object(generate_feed, "get_html", side_effect=fake_get_html):
                    with patch.object(generate_feed, "get_head_last_modified", side_effect=fake_last_modified):
                        with patch.object(generate_feed.time, "sleep"):
                            with patch("sys.stdout", new_callable=io.StringIO):
                                generate_feed.main()

            channel = ET.parse(outfile).getroot().find("channel")
            assert channel is not None
            links = [item.findtext("link") for item in channel.findall("item")]

        self.assertEqual(
            links,
            [
                "https://transformer-circuits.pub/2026/new/index.html",
                "https://transformer-circuits.pub/2025/old/index.html",
            ],
        )

    def test_main_uses_homepage_month_when_article_has_no_date(self) -> None:
        generate_feed = load_generate_feed()
        article_html = "<html><head></head><body><p>Description from article.</p></body></html>"
        home_html = """
            <main>
              <div class="date">December 2025</div>
              <a class="note" href="https://alignment.anthropic.com/2025/activation-oracles/">
                <h3>Circuits Cross-Post — Activation Oracles</h3>
                <div class="description">Activation description.</div>
              </a>
            </main>
        """

        def fake_get_html(url, session=None):
            if url == generate_feed.ORIGIN:
                return home_html
            return article_html

        with tempfile.TemporaryDirectory() as tmpdir:
            outfile = Path(tmpdir) / "index.xml"
            with patch.object(generate_feed, "OUTFILE", str(outfile)):
                with patch.object(generate_feed, "get_html", side_effect=fake_get_html):
                    with patch.object(generate_feed, "get_head_last_modified", return_value=None):
                        with patch.object(generate_feed.time, "sleep"):
                            with patch("sys.stdout", new_callable=io.StringIO):
                                generate_feed.main()

            item = ET.parse(outfile).getroot().find("channel/item")
            assert item is not None
            pub_date = parsedate_to_datetime(item.findtext("pubDate"))

        self.assertEqual(pub_date, datetime(2025, 12, 1, tzinfo=timezone.utc))


if __name__ == "__main__":
    unittest.main()
