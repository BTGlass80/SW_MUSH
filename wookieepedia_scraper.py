"""
wookieepedia_scraper.py — Wookieepedia content fetcher for SW_MUSH

Purpose: Pull full article content from Wookieepedia (Fandom CC-BY-SA) into
project-format markdown extracts at wookieepedia_extracts/<topic>.md.

This is Method B from architecture v35 §32 — direct MediaWiki API access. The
underlying API at https://starwars.fandom.com/api.php is open and accessible
to any properly-identified client. (Direct HTML page fetch returns 403, which
is why this script uses the API rather than scraping the rendered page.)

Standing rules per architecture v35 §32.4:
- One file per topic at wookieepedia_extracts/<topic>.md (snake_case filename).
- Always cite source URL(s) and fetch date in frontmatter.
- Content is CC-BY-SA — attribution is required when synthesizing into
  project extracts. This script preserves attribution metadata in the output.

Requires: Python 3.8+, requests
Install:  pip install requests

Usage examples (from project root):

    # Single article
    python wookieepedia_scraper.py "Coruscant Underworld"

    # Multiple articles to one batch directory
    python wookieepedia_scraper.py "Jedi Temple of Coruscant" "Order 66" "Mortis"

    # From a topic list file (one topic per line, # for comments)
    python wookieepedia_scraper.py --from-file topics.txt

    # Override output directory (default: ./wookieepedia_extracts/)
    python wookieepedia_scraper.py --out my_extracts/ "Yoda"

    # Fetch only canon (default: include both canon and Legends)
    python wookieepedia_scraper.py --canon-only "Anakin Skywalker"

    # Fetch the Legends version (suffix /Legends on the article title)
    python wookieepedia_scraper.py "Coruscant Underworld/Legends"

The script DOES NOT synthesize the project-format extract — it produces a
"raw_<topic>.md" file containing the full article body, infobox data, and
section headers. Synthesis into the project-format wookieepedia_extracts/<topic>.md
is a separate Claude-side step. Per architecture v35 §32.4, the raw fetch can
be deleted once the synthesized extract lands.

Author: SW_MUSH project (Brian)
Architecture reference: v35 §32
Generated: April 26, 2026
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

try:
    import requests
except ImportError:
    print("ERROR: requests library not installed.", file=sys.stderr)
    print("       Install with: pip install requests", file=sys.stderr)
    sys.exit(1)


# ----- Constants -------------------------------------------------------------

API_URL = "https://starwars.fandom.com/api.php"
USER_AGENT = (
    "SW-MUSH-Wookieepedia-Scraper/1.0 "
    "(personal-RPG-project; contact: BTGlass80@github)"
)
RATE_LIMIT_SECONDS = 1.0  # Polite delay between API requests
DEFAULT_OUT_DIR = Path("wookieepedia_extracts")
TIMEOUT_SECONDS = 30


# ----- API client ------------------------------------------------------------


class WookieepediaAPI:
    """Thin wrapper over the Fandom MediaWiki API."""

    def __init__(self, rate_limit: float = RATE_LIMIT_SECONDS) -> None:
        self.session = requests.Session()
        self.session.headers.update({"User-Agent": USER_AGENT})
        self.rate_limit = rate_limit
        self._last_request_time = 0.0

    def _throttle(self) -> None:
        elapsed = time.time() - self._last_request_time
        if elapsed < self.rate_limit:
            time.sleep(self.rate_limit - elapsed)
        self._last_request_time = time.time()

    def _get(self, params: dict[str, Any]) -> dict[str, Any]:
        self._throttle()
        params.setdefault("format", "json")
        params.setdefault("formatversion", "2")
        try:
            resp = self.session.get(API_URL, params=params, timeout=TIMEOUT_SECONDS)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            raise RuntimeError(f"API request failed: {e}") from e

    def fetch_article_wikitext(self, title: str) -> dict[str, Any] | None:
        """Fetch the raw wikitext source of an article.

        Returns None if the article does not exist.
        """
        data = self._get({
            "action": "query",
            "titles": title,
            "prop": "revisions",
            "rvprop": "content|timestamp",
            "rvslots": "main",
            "redirects": "1",
        })
        pages = data.get("query", {}).get("pages", [])
        if not pages:
            return None
        page = pages[0]
        if page.get("missing"):
            return None
        revisions = page.get("revisions", [])
        if not revisions:
            return None
        rev = revisions[0]
        wikitext = rev.get("slots", {}).get("main", {}).get("content", "")
        return {
            "title": page.get("title", title),
            "pageid": page.get("pageid"),
            "wikitext": wikitext,
            "last_edited": rev.get("timestamp"),
        }

    def fetch_article_extract(self, title: str) -> dict[str, Any] | None:
        """Fetch the plain-text extract of an article (no markup).

        Useful as a clean fallback when wikitext is too template-heavy.
        Returns None if the article does not exist.
        """
        data = self._get({
            "action": "query",
            "titles": title,
            "prop": "extracts",
            "explaintext": "1",
            "exsectionformat": "plain",
            "redirects": "1",
        })
        pages = data.get("query", {}).get("pages", [])
        if not pages or pages[0].get("missing"):
            return None
        page = pages[0]
        return {
            "title": page.get("title", title),
            "pageid": page.get("pageid"),
            "extract": page.get("extract", ""),
        }

    def fetch_article_categories(self, title: str) -> list[str]:
        """Fetch category list for an article (useful for tagging)."""
        data = self._get({
            "action": "query",
            "titles": title,
            "prop": "categories",
            "cllimit": "max",
            "redirects": "1",
        })
        pages = data.get("query", {}).get("pages", [])
        if not pages:
            return []
        cats = pages[0].get("categories", [])
        return [c.get("title", "").replace("Category:", "") for c in cats]


# ----- Wikitext cleanup ------------------------------------------------------


def wikitext_to_markdown(wikitext: str) -> str:
    """Convert MediaWiki wikitext to reasonably clean markdown.

    This is a pragmatic cleanup, not a full wikitext parser. It handles the
    common patterns seen in Wookieepedia articles. Anything ambiguous is
    left in place for the synthesizer to clean up by hand.
    """
    text = wikitext

    # Strip <ref> tags and their contents (citations).
    text = re.sub(r"<ref[^>]*>.*?</ref>", "", text, flags=re.DOTALL)
    text = re.sub(r"<ref[^/]*/>", "", text)

    # Strip <!-- comments -->
    text = re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)

    # Strip infoboxes and other top-level templates that span many lines.
    # These typically begin with {{ on a line by itself or {{InfoboxName.
    text = _strip_balanced_braces(text)

    # Convert section headers.  ===Foo=== → ### Foo ; ==Foo== → ## Foo
    text = re.sub(r"^======\s*(.+?)\s*======\s*$", r"###### \1", text, flags=re.MULTILINE)
    text = re.sub(r"^=====\s*(.+?)\s*=====\s*$", r"##### \1", text, flags=re.MULTILINE)
    text = re.sub(r"^====\s*(.+?)\s*====\s*$", r"#### \1", text, flags=re.MULTILINE)
    text = re.sub(r"^===\s*(.+?)\s*===\s*$", r"### \1", text, flags=re.MULTILINE)
    text = re.sub(r"^==\s*(.+?)\s*==\s*$", r"## \1", text, flags=re.MULTILINE)

    # Convert internal links.  [[Foo]] → Foo  ;  [[Foo|Bar]] → Bar
    text = re.sub(r"\[\[([^\[\]|]+)\|([^\[\]]+)\]\]", r"\2", text)
    text = re.sub(r"\[\[([^\[\]]+)\]\]", r"\1", text)

    # Bold and italic.  '''foo''' → **foo** ;  ''foo'' → *foo*
    text = re.sub(r"'''(.+?)'''", r"**\1**", text)
    text = re.sub(r"''(.+?)''", r"*\1*", text)

    # Bullet lists.  * Foo → - Foo
    # Note: we deliberately do NOT convert wikitext "# Foo" numbered lists, because:
    #   (a) doing so collides with the markdown headers we just produced above
    #       (the heading regex emits "## Foo" / "### Foo" which would then match), and
    #   (b) Wookieepedia very rarely uses # numbered lists anyway.
    # If a future article has wikitext numbered lists worth preserving, they can be
    # cleaned up by the synthesizer.
    text = re.sub(r"^\*+ ", "- ", text, flags=re.MULTILINE)

    # Strip remaining HTML tags except <br> which becomes newline.
    text = re.sub(r"<br\s*/?>", "\n", text)
    text = re.sub(r"<[^>]+>", "", text)

    # Collapse runs of blank lines.
    text = re.sub(r"\n\s*\n\s*\n+", "\n\n", text)

    return text.strip()


def _strip_balanced_braces(text: str) -> str:
    """Remove {{...}} template invocations, including nested ones.

    Conservatively strips entire balanced {{...}} regions. This drops
    infoboxes, citation templates, navboxes — all of which add noise and
    little value to a markdown extract for SW_MUSH.
    """
    out = []
    depth = 0
    i = 0
    while i < len(text):
        if text[i:i+2] == "{{":
            depth += 1
            i += 2
            continue
        if text[i:i+2] == "}}":
            if depth > 0:
                depth -= 1
            i += 2
            continue
        if depth == 0:
            out.append(text[i])
        i += 1
    return "".join(out)


# ----- Output ----------------------------------------------------------------


def slugify(title: str) -> str:
    """Convert an article title to a snake_case filename stem."""
    s = title.lower()
    s = re.sub(r"[^a-z0-9]+", "_", s)
    s = s.strip("_")
    return s or "untitled"


def write_raw_extract(
    out_dir: Path,
    article: dict[str, Any],
    extract_text: str | None,
    categories: list[str],
) -> Path:
    """Write a raw_<topic>.md file with frontmatter and content.

    Per architecture v35 §32.4, this is the raw fetch. Synthesis into the
    project-format wookieepedia_extracts/<topic>.md is a separate Claude-side
    step.
    """
    title = article["title"]
    slug = slugify(title)
    filename = f"raw_{slug}.md"
    out_path = out_dir / filename

    timestamp = datetime.now(timezone.utc).isoformat(timespec="seconds")
    url = f"https://starwars.fandom.com/wiki/{title.replace(' ', '_')}"

    md = wikitext_to_markdown(article["wikitext"])

    lines = [
        f"# Wookieepedia Raw Extract — {title}",
        "",
        "**Source:** Wookieepedia (Fandom CC-BY-SA)",
        f"**URL:** {url}",
        f"**Page ID:** {article.get('pageid', 'unknown')}",
        f"**Last edited (per API):** {article.get('last_edited', 'unknown')}",
        f"**Fetched:** {timestamp}",
        f"**Fetcher:** wookieepedia_scraper.py (architecture v35 §32 Method B)",
        "",
        "**Categories:**",
    ]
    if categories:
        for cat in sorted(categories):
            lines.append(f"- {cat}")
    else:
        lines.append("- (none returned)")
    lines.extend([
        "",
        "**Disposition note:** This is a RAW fetch. Per architecture v35 §32.4,",
        f"this file should be synthesized into project-format `wookieepedia_extracts/{slug}.md`",
        "and then this raw file may be deleted.",
        "",
        "---",
        "",
        "## Wikitext (cleaned to markdown)",
        "",
        md,
        "",
    ])

    if extract_text:
        lines.extend([
            "",
            "---",
            "",
            "## Plain-text extract (API `extracts` endpoint)",
            "",
            "*Use this version if the wikitext cleanup above is too noisy.*",
            "",
            extract_text,
            "",
        ])

    lines.extend([
        "",
        "---",
        "",
        "*End of raw extract.*",
        "",
    ])

    out_path.write_text("\n".join(lines), encoding="utf-8")
    return out_path


# ----- CLI driver ------------------------------------------------------------


def parse_topics_file(path: Path) -> list[str]:
    """Parse a topics file: one topic per line, # comments allowed."""
    topics = []
    for raw in path.read_text(encoding="utf-8").splitlines():
        line = raw.split("#", 1)[0].strip()
        if line:
            topics.append(line)
    return topics


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Wookieepedia scraper for SW_MUSH project (architecture v35 §32)."
    )
    parser.add_argument(
        "topics",
        nargs="*",
        help="Article title(s) to fetch. Use quotes for multi-word titles.",
    )
    parser.add_argument(
        "--from-file",
        type=Path,
        help="Read topics from a file (one per line, # for comments).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        default=DEFAULT_OUT_DIR,
        help=f"Output directory (default: {DEFAULT_OUT_DIR}).",
    )
    parser.add_argument(
        "--canon-only",
        action="store_true",
        help="(Reserved — Wookieepedia uses /Legends suffix for Legends pages; specify the suffix on the title to fetch Legends.)",
    )
    parser.add_argument(
        "--include-extract",
        action="store_true",
        default=True,
        help="Also fetch the plain-text extract (default: on).",
    )
    parser.add_argument(
        "--rate-limit",
        type=float,
        default=RATE_LIMIT_SECONDS,
        help=f"Seconds between API requests (default: {RATE_LIMIT_SECONDS}).",
    )
    parser.add_argument(
        "--quiet",
        action="store_true",
        help="Suppress progress output.",
    )
    args = parser.parse_args()

    topics: list[str] = list(args.topics)
    if args.from_file:
        if not args.from_file.exists():
            print(f"ERROR: topics file not found: {args.from_file}", file=sys.stderr)
            return 2
        topics.extend(parse_topics_file(args.from_file))

    topics = [t for t in topics if t]
    if not topics:
        parser.print_help()
        return 1

    out_dir: Path = args.out
    out_dir.mkdir(parents=True, exist_ok=True)

    api = WookieepediaAPI(rate_limit=args.rate_limit)

    successes = 0
    failures: list[tuple[str, str]] = []

    for topic in topics:
        if not args.quiet:
            print(f"[fetch] {topic}", flush=True)

        try:
            article = api.fetch_article_wikitext(topic)
        except RuntimeError as e:
            failures.append((topic, str(e)))
            continue

        if article is None:
            failures.append((topic, "article not found"))
            if not args.quiet:
                print(f"  -> NOT FOUND", flush=True)
            continue

        extract_text = None
        if args.include_extract:
            try:
                ex = api.fetch_article_extract(topic)
                if ex:
                    extract_text = ex.get("extract")
            except RuntimeError:
                # Non-fatal: extract is a convenience, wikitext is primary.
                extract_text = None

        try:
            categories = api.fetch_article_categories(topic)
        except RuntimeError:
            categories = []

        out_path = write_raw_extract(out_dir, article, extract_text, categories)
        if not args.quiet:
            size_kb = out_path.stat().st_size // 1024
            print(f"  -> {out_path}  ({size_kb} KB)", flush=True)
        successes += 1

    if not args.quiet:
        print()
        print(f"Done. {successes} succeeded, {len(failures)} failed.")
    if failures:
        for t, msg in failures:
            print(f"  FAILED: {t}  ({msg})", file=sys.stderr)
        return 3 if successes == 0 else 0

    return 0


if __name__ == "__main__":
    sys.exit(main())
