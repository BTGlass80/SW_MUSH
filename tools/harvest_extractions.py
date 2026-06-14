#!/usr/bin/env python
"""tools/harvest_extractions.py — the FREE lorebook quick-win.

The 16 sourcebook extraction docs under docs/design/ already contain
"Deliverable A: World Lore Entries" — era-translated world_lore entries in
Python-dict form, written for the lorebook but never loaded into it. This
harvests them into lore.yaml format with ZERO new ingestion, $0, no PDFs, no
API.

It reuses tools/ingest_lore.py's LoreEntry + era-validator + emit, so harvested
entries pass the SAME era-cleanness gate as freshly-ingested ones, and gain the
planet + surface_affinity filter tags.

USAGE:
  python tools/harvest_extractions.py --out harvested_lore_review.yaml
  # then review the file and append the keepers to
  # data/worlds/clone_wars/lore.yaml

Per docs/design/sourcebook_ingestion_pipeline_v1.md (the QUICK WIN).
"""
from __future__ import annotations

import argparse
import ast
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from ingest_lore import LoreEntry, validate, emit, PLANETS  # noqa: E402

PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTRACT_DIR = PROJECT_ROOT / "docs" / "design"

# Per-source-book default PLANET tag. Era-neutral texture (crime, creatures,
# gear, ships, smuggling) grounds EVERY planet -> "all". Planet-specific books
# tag their world. The reviewer can refine per entry.
_SOURCE_PLANET = {
    "gg7_mos_eisley": "tatooine",
    "secrets_of_tatooine": "tatooine",
    "geonosis_outer_rim": "geonosis",
    "wretched_hive": "all",
    "gg11_criminal_organizations": "all",
    "gg10_bounty_hunters": "all",
    "creatures_of_the_galaxy": "all",
    "hideouts_and_strongholds": "all",
    "platt_smugglers_guide": "all",
    "gg6_tramp_freighters": "all",
    "crackens_rebel_field_guide": "all",
    "jas": "all",
    "totj": "all",
}

# Infer which generation surface an entry best grounds, from its category.
_CATEGORY_AFFINITY = {
    "faction": "dialogue",
    "organization": "bounty",
    "location": "ambient",
    "person": "encounter",
    "technology": "general",
    "concept": "general",
}


def _source_key(path: Path) -> str:
    name = path.stem.replace("_extraction_v1_1_appendix", "").replace("_extraction_v1", "")
    return name


def _planet_for(source_key: str) -> str:
    for k, planet in _SOURCE_PLANET.items():
        if source_key.startswith(k):
            return planet
    return "all"


def find_dict_blocks(text: str) -> list[str]:
    """Return every balanced {...} block that contains a "title": key."""
    blocks, i, n = [], 0, len(text)
    while i < n:
        if text[i] == "{":
            depth, j = 0, i
            while j < n:
                if text[j] == "{":
                    depth += 1
                elif text[j] == "}":
                    depth -= 1
                    if depth == 0:
                        block = text[i:j + 1]
                        if '"title":' in block:
                            blocks.append(block)
                        i = j
                        break
                j += 1
        i += 1
    return blocks


def harvest_file(path: Path) -> list[LoreEntry]:
    text = path.read_text(encoding="utf-8")
    src = _source_key(path)
    planet = _planet_for(src)
    out = []
    for block in find_dict_blocks(text):
        try:
            d = ast.literal_eval(block)
        except (ValueError, SyntaxError):
            continue          # not a clean dict literal (prose with braces) — skip
        if not isinstance(d, dict) or "title" not in d or "content" not in d:
            continue
        category = str(d.get("category", "concept"))
        entry = LoreEntry(
            title=str(d["title"]).strip(),
            keywords=str(d.get("keywords", "")).lower(),
            content=str(d.get("content", "")),
            category=category,
            zone_scope=(d.get("zone_scope") or None),
            priority=int(d.get("priority", 5) or 5),
            planet=planet,
            surface_affinity=_CATEGORY_AFFINITY.get(category, "general"),
        )
        out.append(validate(entry))
    return out


def main(argv=None) -> int:
    ap = argparse.ArgumentParser(description="Harvest existing extraction lore into lore.yaml format.")
    ap.add_argument("--out", default="harvested_lore_review.yaml")
    args = ap.parse_args(argv)

    docs = sorted(EXTRACT_DIR.glob("*extraction*.md"))
    print(f"[harvest] scanning {len(docs)} extraction doc(s)...")
    all_entries, seen = [], set()
    for doc in docs:
        entries = harvest_file(doc)
        # de-dup by title across docs (some extend existing entries)
        fresh = []
        for e in entries:
            if e.title.lower() in seen:
                continue
            seen.add(e.title.lower())
            fresh.append(e)
        if fresh:
            print(f"[harvest] {doc.stem}: {len(fresh)} entr(ies) "
                  f"(planet={_planet_for(_source_key(doc))})")
        all_entries.extend(fresh)

    kept, flagged = emit(all_entries, Path(args.out))
    print(f"[harvest] TOTAL: {kept} clean, {flagged} flagged -> {args.out}")
    print(f"[harvest] DONE. Review {args.out}, then append the keepers to "
          "data/worlds/clone_wars/lore.yaml. $0, no PDFs, no API.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
