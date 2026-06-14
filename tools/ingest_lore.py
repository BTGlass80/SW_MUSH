#!/usr/bin/env python
"""tools/ingest_lore.py — automated sourcebook -> world-lore ingestion.

Per docs/design/sourcebook_ingestion_pipeline_v1.md. Turns a sourcebook PDF into
era-translated `world_lore` entries (the grounding corpus for the Director +
NPC dialogue + the free-Ollama enrichment), CHEAP and mostly automatic.

PIPELINE (4 stages):
  1. OCR        PDF -> text. PyMuPDF text-layer first; if the page is a scan
                (no text layer), fall back to Tesseract (if installed) or tell
                you to use --vision / install tesseract.
  2. EXTRACT    text -> world_lore entries via Claude Haiku, chunked, era-
                translated to ~20 BBY, canonical figures reduced to archetypes,
                tagged with planet + surface_affinity. (--mock runs offline.)
  3. VALIDATE   drop any entry whose CONTENT contains a banned era token
                (the SAME _BANNED canon the era-cleanness tests enforce).
  4. EMIT       write the validated entries to a REVIEW yaml file. You eyeball
                it, then append the keepers to data/worlds/clone_wars/lore.yaml.
                (The tool never edits the live lorebook directly.)

USAGE:
  # offline smoke (no PDF, no API) — proves the pipeline wiring:
  python tools/ingest_lore.py --mock --out review.yaml

  # real digital PDF (has a text layer — works with no extra install):
  python tools/ingest_lore.py docs/sourcebooks/SOMEBOOK.pdf --out review.yaml

  # scanned PDF (image-only) needs Tesseract OR the vision path:
  python tools/ingest_lore.py SCAN.pdf --ocr tesseract --out review.yaml

Copyright: the PDF stays local/gitignored. The EXTRACTED, era-translated lore
is the committed artifact (transformative).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

for _s in ("stdout", "stderr"):
    try:
        getattr(sys, _s).reconfigure(encoding="utf-8")
    except Exception:
        # Best-effort console encoding; non-fatal for a CLI tool.
        _ENC_FALLBACK = True

PROJECT_ROOT = Path(__file__).resolve().parents[1]

# ── Era canon (kept in sync with tests/test_laneb_era_cleanness.py::_BANNED) ──
# The single source of truth for "this string is off-era for Clone Wars."
# When engine/era_validator.py is built (shared with T3.22 + the enrichment
# pools, per the pipeline doc STEP 0), import from there instead.
_BANNED = (
    "Imperial", "IMPERIAL", "imperial",
    "Stormtrooper", "stormtrooper",
    "Empire", "Rebel", "rebel",
    "TIE fighter", "TIE-", "X-Wing", "x-wing",
    # Post-Clone-Wars / GCW era tokens (added 2026-06-13 after the LLM
    # quality-gate caught these leaking past the original literal list —
    # "Empire"/"Imperial" alone don't catch the New-Republic-era residue):
    "New Republic", "Grand Moff", "Death Star", "Order 66",
    "Order Sixty-Six", "New Order", "Galactic Civil War",
)
# Canonical figures that must never become named NPCs (Q1 policy). Reduced to
# archetypes by the extractor; flagged here as a belt-and-suspenders content check.
_CANONICAL_FIGURES = (
    "Anakin", "Ahsoka", "Obi-Wan", "Obi Wan", "Palpatine", "Sidious",
    "Dooku", "Grievous", "Maul", "Yoda", "Windu", "Padme", "Padmé",
    "Jabba", "Ventress", "Cad Bane", "Bossk", "Aurra Sing", "Boba",
    # Added 2026-06-13 — figures the quality-gate caught in ingested lore
    # (matched case-insensitively as substrings, so "Mothma" catches "Mon
    # Mothma", "Gunray" catches "Nute Gunray", "Tarkin" catches "Tarkin's"):
    "Jango", "Tarkin", "Mon Mothma", "Mothma", "Talzin", "Valorum",
    "Nute Gunray", "Gunray", "Hondo", "Wat Tambor", "Sio Bibble",
    "Lama Su", "Taun We", "Shaak Ti", "Mas Amedda",
)

SURFACE_AFFINITIES = ("dialogue", "encounter", "bounty", "news", "ambient", "general")
PLANETS = ("tatooine", "coruscant", "kamino", "kuat", "geonosis", "nar_shaddaa", "all")
CATEGORIES = ("faction", "location", "technology", "concept", "person", "organization")


@dataclass
class LoreEntry:
    title: str
    keywords: str            # comma-separated trigger terms (lowercased)
    content: str             # 1-3 paragraphs
    category: str = "concept"
    zone_scope: Optional[str] = None
    priority: int = 5
    planet: str = "all"      # filter tag (free at generation time)
    surface_affinity: str = "general"   # filter tag (free)
    _rejects: list = field(default_factory=list)   # validation flags

    def as_yaml_block(self) -> str:
        def q(s):
            return '"' + str(s).replace('"', '\\"') + '"'
        lines = [
            f"  - title: {q(self.title)}",
            f"    keywords: {q(self.keywords)}",
            f"    category: {q(self.category)}",
            f"    priority: {self.priority}",
            f"    planet: {q(self.planet)}",
            f"    surface_affinity: {q(self.surface_affinity)}",
        ]
        if self.zone_scope:
            lines.append(f"    zone_scope: {q(self.zone_scope)}")
        # content as a YAML block scalar
        lines.append("    content: |")
        for para in self.content.strip().splitlines():
            lines.append(f"      {para}")
        return "\n".join(lines)


# ── STAGE 1: OCR / text extraction ────────────────────────────────────────

def extract_text(pdf_path: Path, ocr: str = "auto", concurrency: int = 1) -> tuple[str, str]:
    """Return (text, method). Reads the text layer per page; OCRs scan-like pages
    via Tesseract. Pixmaps are rendered SEQUENTIALLY (PyMuPDF isn't thread-safe on a
    single Document) but the slow Tesseract pass runs CONCURRENTLY across
    `concurrency` workers over the rendered PNG bytes (no fitz access in threads)."""
    try:
        import fitz  # PyMuPDF
    except Exception:
        raise SystemExit("PyMuPDF (fitz) not installed — `pip install pymupdf`.")

    doc = fitz.open(str(pdf_path))
    n = doc.page_count
    parts: list = [None] * n
    ocr_jobs: list = []          # (page_index, png_bytes) for the scanned pages
    scanned_pages = 0
    tess_ok = ocr in ("tesseract", "auto") and _ensure_tesseract_cmd()
    for i in range(n):
        page = doc[i]
        text = page.get_text()
        if len(text.strip()) < 40:           # ~no text layer => scanned page
            scanned_pages += 1
            if tess_ok:
                ocr_jobs.append((i, page.get_pixmap(dpi=300).tobytes("png")))
            else:
                parts[i] = f"[PAGE {i + 1}: no text layer — OCR needed]"
        else:
            parts[i] = text
    doc.close()

    if ocr_jobs:
        if concurrency > 1 and len(ocr_jobs) > 1:
            from concurrent.futures import ThreadPoolExecutor
            with ThreadPoolExecutor(max_workers=concurrency) as ex:
                done = list(ex.map(lambda j: (j[0], _ocr_png(j[1])), ocr_jobs))
        else:
            done = [(idx, _ocr_png(b)) for idx, b in ocr_jobs]
        for idx, txt in done:
            parts[idx] = txt or f"[PAGE {idx + 1}: no text layer — OCR needed]"

    parts = [p if p is not None else "" for p in parts]
    method = "text-layer"
    if scanned_pages:
        method = f"text-layer + {scanned_pages} scanned page(s)"
    return "\n".join(parts), method


# Common Windows install path for the Tesseract binary (not always on PATH).
_TESSERACT_PATHS = (
    r"C:\Program Files\Tesseract-OCR\tesseract.exe",
    r"C:\Program Files (x86)\Tesseract-OCR\tesseract.exe",
)


def _ensure_tesseract_cmd() -> bool:
    """Point pytesseract at the binary if it isn't on PATH. Returns availability."""
    try:
        import pytesseract
        import shutil
        if shutil.which("tesseract"):
            return True
        for p in _TESSERACT_PATHS:
            if os.path.exists(p):
                pytesseract.pytesseract.tesseract_cmd = p
                return True
        return False
    except Exception:
        return False


def _ocr_png(png_bytes: bytes) -> str:
    """OCR rendered PNG bytes via Tesseract, or '' on failure. Takes raw bytes (no
    PyMuPDF access) so it is safe to call from worker threads. Assumes
    _ensure_tesseract_cmd() already ran once on the main thread."""
    try:
        import pytesseract       # noqa
        from PIL import Image    # noqa
        import io
        img = Image.open(io.BytesIO(png_bytes))
        return pytesseract.image_to_string(img)
    except Exception:
        return ""


# ── STAGE 2: extraction (Haiku) + offline Mock ────────────────────────────

_EXTRACT_SYSTEM = """\
You extract WORLD-LORE entries from a Star Wars D6 sourcebook for a Clone Wars
(~20 BBY) MUD. Output ONLY a JSON array of entries. Each entry:
  {"title","keywords","content","category","zone_scope","priority","planet","surface_affinity"}
HARD RULES:
- ERA-TRANSLATE to the Clone Wars (~20 BBY): Republic/CIS/Separatist/clones —
  NEVER the Empire, Imperials, stormtroopers, TIEs, Rebels, X-Wings.
- NO canonical named figures as subjects (no Anakin/Ahsoka/Dooku/Jabba/etc.) —
  reduce them to archetypes ("a Hutt crime lord", "a fallen Jedi").
- content = 1-3 tight paragraphs of TEXTURE a generator can ground on (sights,
  vocabulary, customs, danger) — not rules/stats.
- keywords = comma-separated lowercase trigger terms.
- category one of: faction|location|technology|concept|person|organization.
- planet one of: tatooine|coruscant|kamino|kuat|geonosis|nar_shaddaa|all.
- surface_affinity one of: dialogue|encounter|bounty|news|ambient|general
  (which generation surface this lore best grounds).
- zone_scope: comma-separated zone keys or null (global).
- priority 1-10 (higher = more prominent).
OCR NOISE: the source is OCR'd and MAY contain errors (garbled/split/merged words,
stray characters, page header/footer noise, multi-column bleed). Silently correct
OBVIOUS OCR artifacts when the intended word is clear from context. If a passage —
or a proper noun like a species/place/tech name — is too garbled to read
CONFIDENTLY, OMIT it; do NOT guess or invent a name or fact to fill an OCR gap.
Dropping an uncertain entry is better than storing a wrong one."""


class MockExtractor:
    """Offline extractor — returns a deterministic sample so the pipeline runs
    with no API/PDF. Proves wiring; never used for real ingestion."""

    def extract(self, chunk: str, source: str) -> list[dict]:
        return [{
            "title": f"Sample Lore from {source}",
            "keywords": "sample,mock,cantina,spaceport",
            "content": ("A weathered spaceport baking under a pale sun, its "
                        "landing pits slick with hydraulic fluid and the smell "
                        "of scorched ozone. Spacers haggle in a dozen tongues."),
            "category": "location",
            "zone_scope": None,
            "priority": 5,
            "planet": "all",
            "surface_affinity": "ambient",
        }]


class FatalExtractionError(RuntimeError):
    """Raised when the API rejects a call in a way that would fail IDENTICALLY for
    every chunk (bad/again-unauthorized key, no credit balance, SSL/proxy break) —
    so the run aborts loudly instead of silently writing a 0-entry review file."""


def _inject_os_trust_store() -> None:
    """Make stdlib SSL use the OS (Windows) cert store, so a corporate
    TLS-inspection proxy whose root CA the OS trusts (but certifi does not) does
    not break the HTTPS call. No-op if `truststore` isn't installed."""
    try:
        import truststore
        truststore.inject_into_ssl()
    except Exception:
        pass  # truststore optional — stdlib SSL/certifi stands if it's absent


class HaikuExtractor:
    """Real extractor via the Anthropic API (claude-haiku). Cheap (~1c/book)."""

    def __init__(self, api_key: str, model: str = "claude-haiku-4-5-20251001"):
        self.api_key = api_key
        self.model = model
        _inject_os_trust_store()

    def extract(self, chunk: str, source: str) -> list[dict]:
        import urllib.request
        import urllib.error
        import time
        body = json.dumps({
            "model": self.model,
            "max_tokens": 2000,
            "system": _EXTRACT_SYSTEM,
            "messages": [{"role": "user", "content":
                f"Source: {source}\n\nExtract lore entries from this text:\n\n{chunk[:12000]}"}],
        }).encode()
        req = urllib.request.Request(
            "https://api.anthropic.com/v1/messages", data=body,
            headers={"x-api-key": self.api_key,
                     "anthropic-version": "2023-06-01",
                     "content-type": "application/json"})
        data = None
        backoff = 1.0
        for attempt in range(5):
            try:
                with urllib.request.urlopen(req, timeout=90) as resp:
                    data = json.loads(resp.read())
                break
            except urllib.error.HTTPError as e:
                detail = ""
                try:
                    detail = e.read().decode("utf-8", "replace")
                except Exception:
                    pass  # detail is best-effort for the error message
                low = detail.lower()
                # auth / billing errors recur identically for every chunk -> abort
                if e.code in (401, 403) or "credit balance" in low or \
                   "authentication" in low or "invalid x-api-key" in low:
                    raise FatalExtractionError(f"HTTP {e.code}: {detail[:300] or e.reason}")
                # 429 rate-limit / 5xx overload -> back off and RETRY (don't drop the
                # chunk — that silently loses lore under concurrency)
                if (e.code == 429 or 500 <= e.code < 600) and attempt < 4:
                    ra = e.headers.get("retry-after") if e.headers else None
                    wait = float(ra) if (ra and str(ra).isdigit()) else backoff
                    sys.stderr.write(f"[ingest] HTTP {e.code}; retry {attempt + 1}/5 in {wait:.0f}s\n")
                    time.sleep(wait)
                    backoff *= 2
                    continue
                # other 4xx, or transient after retries exhausted -> skip this chunk
                sys.stderr.write(f"[ingest] chunk skipped (HTTP {e.code}): {detail[:160]}\n")
                return []
            except urllib.error.URLError as e:
                reason = str(e.reason)
                # SSL/cert problems are environmental and won't fix on retry -> abort
                if "SSL" in reason.upper() or "CERTIFICATE" in reason.upper():
                    raise FatalExtractionError(f"connection/SSL error: {e.reason}")
                # timeout / connection refused / transient DNS -> back off and retry
                if attempt < 4:
                    sys.stderr.write(f"[ingest] network error ({reason}); retry {attempt + 1}/5 in {backoff:.0f}s\n")
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                sys.stderr.write(f"[ingest] chunk skipped (network: {reason})\n")
                return []
            except (TimeoutError, ConnectionError) as e:
                # bare socket read-timeout / connection reset -> transient, retry
                if attempt < 4:
                    sys.stderr.write(f"[ingest] {type(e).__name__}; retry {attempt + 1}/5 in {backoff:.0f}s\n")
                    time.sleep(backoff)
                    backoff *= 2
                    continue
                sys.stderr.write(f"[ingest] chunk skipped ({type(e).__name__})\n")
                return []
        if data is None:
            return []
        try:
            text = "".join(b.get("text", "") for b in data.get("content", []))
            m = re.search(r"\[.*\]", text, re.DOTALL)
            return json.loads(m.group(0)) if m else []
        except Exception as e:
            sys.stderr.write(f"[ingest] chunk parse failed: {e}\n")
            return []


def chunk_text(text: str, max_chars: int = 10000) -> list[str]:
    """Split into ~max_chars chunks on paragraph boundaries."""
    paras = text.split("\n\n")
    chunks, cur = [], ""
    for p in paras:
        if len(cur) + len(p) > max_chars and cur:
            chunks.append(cur)
            cur = ""
        cur += p + "\n\n"
    if cur.strip():
        chunks.append(cur)
    return chunks or [""]


# ── STAGE 3: era validation ───────────────────────────────────────────────

def validate(entry: LoreEntry) -> LoreEntry:
    """Flag banned era tokens / canonical figures in the CONTENT (+ title).
    Keywords may legitimately reference canonical names as triggers; content
    must not put words in their mouths."""
    haystack = (entry.title + " " + entry.content)
    for bad in _BANNED:
        if re.search(r"\b" + re.escape(bad) + r"\b", haystack):
            entry._rejects.append(f"era:{bad}")
    low = haystack.lower()
    for fig in _CANONICAL_FIGURES:
        if fig.lower() in low:
            entry._rejects.append(f"canon:{fig}")
    # field sanity
    if entry.category not in CATEGORIES:
        entry.category = "concept"
    if entry.planet not in PLANETS:
        entry.planet = "all"
    if entry.surface_affinity not in SURFACE_AFFINITIES:
        entry.surface_affinity = "general"
    return entry


# ── STAGE 4: emit ─────────────────────────────────────────────────────────

def emit(entries: list[LoreEntry], out_path: Path) -> tuple[int, int]:
    keepers = [e for e in entries if not e._rejects]
    flagged = [e for e in entries if e._rejects]
    with open(out_path, "w", encoding="utf-8") as fh:
        fh.write("# Ingested lore — REVIEW before appending to "
                 "data/worlds/clone_wars/lore.yaml\n")
        fh.write(f"# {len(keepers)} clean entr(ies); {len(flagged)} flagged "
                 "(shown commented-out at the bottom for manual era-translation).\n\n")
        for e in keepers:
            fh.write(e.as_yaml_block() + "\n\n")
        if flagged:
            fh.write("\n# ─── FLAGGED (fix the era/canon issue, then move up) ───\n")
            for e in flagged:
                fh.write(f"# REJECTED [{', '.join(e._rejects)}]:\n")
                fh.write("\n".join("# " + ln for ln in e.as_yaml_block().splitlines()))
                fh.write("\n\n")
    return len(keepers), len(flagged)


# ── Driver ────────────────────────────────────────────────────────────────

def main(argv=None) -> int:
    try:    # Windows cp1252 consoles crash on unicode in OCR'd entry text
        sys.stdout.reconfigure(encoding="utf-8")
        sys.stderr.reconfigure(encoding="utf-8")
    except Exception:
        pass  # reconfigure is best-effort; older/non-Windows streams keep default
    ap = argparse.ArgumentParser(description="Sourcebook -> world-lore ingestion.")
    ap.add_argument("pdf", nargs="?", help="path to the sourcebook PDF")
    ap.add_argument("--out", default="ingested_lore_review.yaml",
                    help="review file to write (default: ingested_lore_review.yaml)")
    ap.add_argument("--ocr", choices=["auto", "tesseract", "off"], default="auto")
    ap.add_argument("--mock", action="store_true",
                    help="offline: no PDF/API, emits a sample (pipeline smoke)")
    ap.add_argument("--source", default="", help="source label for entries")
    ap.add_argument("--concurrency", type=int, default=1,
                    help="parallel OCR pages + API chunks (default 1 = sequential)")
    args = ap.parse_args(argv)

    source = args.source or (Path(args.pdf).stem if args.pdf else "mock")

    # Stage 1
    if args.mock:
        chunks = ["(mock chunk)"]
        print("[ingest] MOCK mode — no PDF/API; smoking the pipeline.")
    else:
        if not args.pdf:
            print("[ingest] need a PDF path (or --mock). See --help.", file=sys.stderr)
            return 2
        text, method = extract_text(Path(args.pdf), ocr=args.ocr, concurrency=args.concurrency)
        print(f"[ingest] stage 1 OCR: {method}; {len(text):,} chars")
        if "[PAGE" in text and args.ocr != "tesseract":
            print("[ingest] NOTE: some pages had no text layer (scanned). "
                  "Install Tesseract + `pip install pytesseract pillow`, then "
                  "re-run with --ocr tesseract, OR use a digital PDF.")
        chunks = chunk_text(text)
        print(f"[ingest] stage 1: {len(chunks)} chunk(s)")

    # Stage 2
    if args.mock:
        extractor = MockExtractor()
    else:
        key = os.environ.get("ANTHROPIC_API_KEY", "").strip()
        if not key:
            print("[ingest] no ANTHROPIC_API_KEY — falling back to MOCK extractor "
                  "(set the key for real extraction).")
            extractor = MockExtractor()
        else:
            extractor = HaikuExtractor(key)
    raw = []
    try:
        if args.mock or args.concurrency <= 1:
            for i, ch in enumerate(chunks, 1):
                got = extractor.extract(ch, source)
                raw.extend(got)
                print(f"[ingest] stage 2: chunk {i}/{len(chunks)} -> {len(got)} entr(ies)")
        else:
            from concurrent.futures import ThreadPoolExecutor, as_completed
            with ThreadPoolExecutor(max_workers=args.concurrency) as ex:
                futs = [ex.submit(extractor.extract, ch, source) for ch in chunks]
                done = 0
                for fut in as_completed(futs):
                    got = fut.result()          # re-raises FatalExtractionError
                    raw.extend(got)
                    done += 1
                    print(f"[ingest] stage 2: {done}/{len(chunks)} chunks "
                          f"-> +{len(got)} (conc={args.concurrency})")
    except FatalExtractionError as e:
        print(f"\n[ingest] ABORTED — the API rejected the request and would fail "
              f"identically for every chunk:\n    {e}\n"
              f"[ingest] No review file written. Common fix: add credits at "
              f"console.anthropic.com -> Plans & Billing (or check the API key/account).",
              file=sys.stderr)
        return 3

    # de-dup by title
    seen, entries = set(), []
    for d in raw:
        title = str(d.get("title", "")).strip()
        if not title or title.lower() in seen:
            continue
        seen.add(title.lower())
        entries.append(validate(LoreEntry(
            title=title,
            keywords=str(d.get("keywords", "")).lower(),
            content=str(d.get("content", "")),
            category=str(d.get("category", "concept")),
            zone_scope=(d.get("zone_scope") or None),
            priority=int(d.get("priority", 5) or 5),
            planet=str(d.get("planet", "all")),
            surface_affinity=str(d.get("surface_affinity", "general")),
        )))

    # Stages 3+4
    kept, flagged = emit(entries, Path(args.out))
    print(f"[ingest] stage 3-4: {kept} clean, {flagged} flagged -> {args.out}")
    print(f"[ingest] DONE. Review {args.out}, then append the keepers to "
          "data/worlds/clone_wars/lore.yaml.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
