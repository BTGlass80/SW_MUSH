"""tools/mapgen/batch.py — batch orchestration + selection, with the
"toe the line" generation loop.

Pipeline for one area:
  seed + brief  ->  apply term substitutions (at the current rungs)
                ->  generate N candidates via the nano client
                      (each candidate runs the TOE-THE-LINE loop: start bold,
                       step a term down on refusal / off-theme, record the
                       boldest rung that worked)
                ->  screen each  ->  coord-score each  ->  rank
                ->  persist a batch manifest  ->  human selects  ->  writeback

All three external collaborators (nano client, screener, coord scorer) are
constructor-injected and DEFAULT to Mock/NoOp, so the whole harness runs
offline end-to-end with no API keys and no frozen coordinates.
"""
from __future__ import annotations

import json
import shutil
from dataclasses import dataclass, field, asdict
from pathlib import Path
from typing import Optional

from . import paths, term_substitutions as tsub
from .nano_client import MockNanoClient
from .screen import MockScreener, screen_image, ScreeningVerdict
from .scorer import NoOpCoordinateScorer, CompositeRanker, screen_to_score


# How far to step down a term's ladder before giving up on that candidate.
_MAX_BACKOFF_STEPS = 6


@dataclass
class CandidateArtifact:
    id: str
    image_path: str
    ai_screen_score: float
    coord_fit_score: float
    composite_rank: float
    rungs_used: dict          # term -> ladder rung that produced this image
    verdict: dict             # the ScreeningVerdict
    notes: str = ""


@dataclass
class BatchResult:
    area_key: str
    timestamp: str
    seed_path: str
    brief_path: str
    candidates: list = field(default_factory=list)   # list[CandidateArtifact]
    top_k: list = field(default_factory=list)         # candidate ids, best first
    escalated: list = field(default_factory=list)     # ids the screener flagged ESCALATE
    selected: Optional[str] = None
    manifest_path: str = ""


class BatchOrchestrator:
    def __init__(self, area_key: str, *, era: str = "clone_wars",
                 nano_client=None, screener_provider=None, coord_scorer=None,
                 ranker: Optional[CompositeRanker] = None,
                 boundaries_path: Optional[Path] = None):
        self.area_key = area_key
        self.era = era
        # Inject-or-Mock: this is what makes the harness run offline.
        self.nano = nano_client or MockNanoClient()
        self.screener_provider = screener_provider   # None -> MockScreener path
        self.coord_scorer = coord_scorer or NoOpCoordinateScorer()
        self.ranker = ranker or CompositeRanker()
        self.boundaries_path = boundaries_path

    async def run_batch(self, n_candidates: int = 6, *, timestamp: str,
                        style_reference_image: Optional[Path] = None,
                        verified_stamp: str = "") -> BatchResult:
        """Generate, screen, score, rank N candidates. `timestamp` is supplied
        by the caller (no Date.now() here, for determinism/resume)."""
        seed = paths.seed_for(self.area_key)
        brief_path = paths.brief_for(self.area_key)
        brief_text = brief_path.read_text(encoding="utf-8") if brief_path.exists() \
            else f"(no brief on disk for {self.area_key})"
        geography = brief_text

        out_dir = paths.ensure_dir(paths.batch_dir(self.area_key, timestamp))
        cand_dir = paths.ensure_dir(out_dir / "candidates")

        result = BatchResult(
            area_key=self.area_key, timestamp=timestamp,
            seed_path=str(seed), brief_path=str(brief_path),
            manifest_path=str(out_dir / "manifest.json"),
        )

        manifest = self._load_manifest_json()

        for i in range(n_candidates):
            cid = f"cand_{i:02d}"
            img_path = cand_dir / f"{cid}.png"
            # Idempotent resume: if this candidate already exists, reuse it.
            if img_path.exists():
                continue
            artifact = await self._make_one_candidate(
                cid, seed, brief_text, geography, style_reference_image,
                img_path, manifest, verified_stamp)
            if artifact:
                result.candidates.append(artifact)

        # Rank survivors (best composite first).
        result.candidates.sort(key=lambda c: c.composite_rank, reverse=True)
        result.top_k = [c.id for c in result.candidates]
        # ESCALATE routing: a borderline screen verdict flags 'ESCALATE'; surface
        # those for a human/Opus second look instead of trusting the auto-rank.
        result.escalated = [c.id for c in result.candidates
                            if "ESCALATE" in c.verdict.get("flags", [])]
        self._write_manifest(result, out_dir)
        return result

    async def _make_one_candidate(self, cid, seed, brief_text, geography,
                                  style_ref, img_path, manifest, verified):
        """Run the TOE-THE-LINE loop for one candidate: start each present term
        at its boundary/bold rung, generate; on a content-filter REFUSAL or an
        OFF-THEME screen, step the offending term(s) down a rung and retry;
        record the boldest rung that ultimately worked."""
        rungs = tsub.starting_rungs(brief_text, self.boundaries_path)
        present = tsub.terms_present(brief_text)
        notes = []

        for _step in range(_MAX_BACKOFF_STEPS + 1):
            prompt = tsub.apply_term_substitutions(brief_text, rungs)
            gen = await self.nano.generate_image(seed, style_ref, prompt)

            if gen.refused:
                # Content filter crossed the line — step the boldest present
                # term down one rung and retry.
                if not self._step_down(rungs, present):
                    notes.append("refused at safe floor; gave up")
                    return None
                notes.append("refused -> stepped a term down")
                continue
            if not gen.ok:
                notes.append(f"gen error: {gen.error}")
                return None

            verdict: ScreeningVerdict = await screen_image(
                gen.image, brief_text, geography, provider=self.screener_provider)

            if not verdict["on_theme"]:
                # Off-theme (e.g. ocean ship in a desert) — also a line signal.
                if not self._step_down(rungs, present):
                    notes.append("off-theme at safe floor; kept anyway")
                else:
                    notes.append("off-theme -> stepped a term down")
                    continue

            # Success (or off-theme-at-floor): keep this image.
            img_path.write_bytes(gen.image)
            self._record_boundaries(rungs, present, verdict, verified)

            screen_score = screen_to_score(verdict)
            coord_score = self.coord_scorer.score_coordinate_fit(gen.image, manifest)
            composite = self.ranker.composite(screen_score, coord_score)
            return CandidateArtifact(
                id=cid, image_path=str(img_path),
                ai_screen_score=screen_score, coord_fit_score=coord_score,
                composite_rank=composite, rungs_used=dict(rungs),
                verdict=dict(verdict), notes="; ".join(notes))
        notes.append("exhausted backoff steps")
        return None

    @staticmethod
    def _step_down(rungs: dict, present: list) -> bool:
        """Move the boldest present term (lowest rung index) one rung safer.
        Returns False if every present term is already at its safe floor."""
        # Pick the term currently at the boldest rung that still has room.
        candidates = [(rungs.get(t, 0), t) for t in present
                      if rungs.get(t, 0) < tsub.boldest_rung_count(t) - 1]
        if not candidates:
            return False
        candidates.sort()  # lowest rung (boldest) first
        _, term = candidates[0]
        rungs[term] = rungs.get(term, 0) + 1
        return True

    def _record_boundaries(self, rungs, present, verdict, verified):
        """On an on-theme keeper, record each present term's working rung as the
        known-good boundary (only tightens toward bolder)."""
        if not verdict.get("on_theme", True):
            return
        score = float(verdict.get("score", 0.0))
        for term in present:
            tsub.record_boundary(term, rungs.get(term, 0), score,
                                 verified=verified, path=self.boundaries_path)

    def _load_manifest_json(self) -> dict:
        mpath = paths.manifest_for(self.area_key)
        if mpath.exists():
            try:
                return json.loads(mpath.read_text(encoding="utf-8"))
            except (json.JSONDecodeError, OSError):
                return {}
        return {}

    def _write_manifest(self, result: BatchResult, out_dir: Path) -> None:
        payload = {
            "area_key": result.area_key,
            "timestamp": result.timestamp,
            "seed_path": result.seed_path,
            "brief_path": result.brief_path,
            "selected": result.selected,
            "top_k": result.top_k,
            "escalated": result.escalated,
            "candidates": [asdict(c) for c in result.candidates],
        }
        (out_dir / "manifest.json").write_text(
            json.dumps(payload, indent=2) + "\n", encoding="utf-8")


def select_painting(result: BatchResult, candidate_id: str, *,
                    slug: Optional[str] = None) -> Optional[str]:
    """Copy the chosen candidate to static/maps/<slug>_substrate.png and record
    the selection in the batch manifest. Returns the `substrate_image:` line to
    paste into the area map YAML (the area_loader seam) — the YAML edit stays
    MANUAL to honor the additive/map-safety invariant."""
    chosen = next((c for c in result.candidates if c.id == candidate_id), None)
    if chosen is None:
        return None
    slug = slug or result.area_key.replace(".", "_")
    dest = paths.substrate_dest(slug)
    paths.ensure_dir(dest.parent)
    shutil.copyfile(chosen.image_path, dest)
    result.selected = candidate_id
    out_dir = Path(result.manifest_path).parent
    # rewrite manifest with the selection recorded
    orch_payload = json.loads(Path(result.manifest_path).read_text(encoding="utf-8"))
    orch_payload["selected"] = candidate_id
    Path(result.manifest_path).write_text(
        json.dumps(orch_payload, indent=2) + "\n", encoding="utf-8")
    try:
        rel = dest.relative_to(paths.PROJECT_ROOT).as_posix()
    except ValueError:
        # dest is outside the project root (e.g. a redirected test dir) —
        # fall back to the conventional repo-relative path for the slug.
        rel = f"static/maps/{slug}_substrate.png"
    return f'substrate_image: "{rel}"   # paste into the area map YAML (manual)'
