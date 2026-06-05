"""Economy audit F1 — ledger chokepoint completeness guard.

R1/F1 mandated that *every* credit mutation route through the single
``Database.adjust_credits`` chokepoint, so the movement lands in
``credit_log`` and is therefore visible to ``@economy velocity``, the
dashboard, and the whale/farming/inflation/velocity alerts. The ledger
migration (Drop 1) was marked complete, but an AST sweep found **14** sites
still writing the balance directly via ``save_character(credits=...)`` — many
in hot economy paths (entertainer, medical, sabacc, combat bounty, repair,
item sale, debt, org stipend, boarding reward, docking fee) — i.e. credit
flow the velocity alerts could never see.

This drop migrated the 13 running-economy transactions to ``adjust_credits``
and allowlisted the 1 chargen initialization. This test is the anti-regression
lock: it AST-scans engine/parser/server and fails if any *new* raw credit
write appears outside the documented allowlist. AST (not grep) so comments and
docstrings that merely mention the old pattern don't trip it.
"""

import ast
import unittest
from pathlib import Path


def _find_root() -> Path:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        if (parent / "db" / "database.py").exists() and (parent / "engine").is_dir():
            return parent
    raise RuntimeError("could not locate repo root from test file")


ROOT = _find_root()

# The ONLY sanctioned raw `save_character(credits=...)` site. Chargen
# initialization (skip-starter-kit) sets a brand-new character's starting
# credits as an absolute value — consistent with the unlogged
# create_character INSERT on the regular path — not a running-economy faucet.
ALLOWLIST = {"server/api.py"}

SCAN_ROOTS = ("engine", "parser", "server")


def _raw_credit_write_sites():
    """Return [(relpath, lineno), ...] for every save_character(credits=...)
    call in the scanned roots."""
    hits = []
    for r in SCAN_ROOTS:
        base = ROOT / r
        if not base.is_dir():
            continue
        for p in base.rglob("*.py"):
            try:
                tree = ast.parse(p.read_text(encoding="utf-8"))
            except Exception:
                # Unparseable files are caught by py_compile elsewhere; the
                # chokepoint guard just skips them rather than erroring out.
                continue
            for node in ast.walk(tree):
                if isinstance(node, ast.Call):
                    fn = getattr(node.func, "attr", None) or getattr(node.func, "id", None)
                    if fn == "save_character" and any(
                            kw.arg == "credits" for kw in node.keywords):
                        rel = str(p.relative_to(ROOT)).replace("\\", "/")
                        hits.append((rel, node.lineno))
    return hits


def _function_source(path: Path, func_name: str) -> str:
    src = path.read_text(encoding="utf-8")
    marker = f"async def {func_name}("
    i = src.index(marker)
    nxt = src.find("\nasync def ", i + 1)
    return src[i:] if nxt == -1 else src[i:nxt]


class TestLedgerChokepointComplete(unittest.TestCase):
    def test_no_unallowlisted_raw_credit_writes(self):
        offenders = sorted(
            f"{rel}:{ln}" for rel, ln in _raw_credit_write_sites()
            if rel not in ALLOWLIST)
        self.assertEqual(
            offenders, [],
            "raw save_character(credits=...) must route through "
            "adjust_credits (economy audit F1). Offenders: " + ", ".join(offenders))

    def test_allowlisted_site_still_exists_and_documented(self):
        # If the allowlisted chargen site is removed/migrated, tighten the
        # allowlist rather than leaving a stale entry.
        sites = {rel for rel, _ in _raw_credit_write_sites()}
        self.assertIn(
            "server/api.py", sites,
            "allowlist names server/api.py but no raw site found there — "
            "remove it from ALLOWLIST")
        api = (ROOT / "server" / "api.py").read_text(encoding="utf-8")
        self.assertIn("Chargen initialization", api,
                      "the allowlisted site must carry its explanatory comment")

    def test_docking_fee_tick_uses_chokepoint(self):
        body = _function_source(
            ROOT / "server" / "tick_handlers_economy.py", "docking_fee_tick")
        self.assertIn("adjust_credits(", body)
        self.assertIn('"docking_fee"', body)
        self.assertNotIn("log_credit(", body,
                         "docking_fee_tick should no longer do a separate "
                         "log_credit — adjust_credits logs atomically")
        # (The raw-write check itself is covered comprehensively by
        # test_no_unallowlisted_raw_credit_writes; not re-substring-matched
        # here since the explanatory comment names the old pattern.)


if __name__ == "__main__":
    unittest.main(verbosity=2)
