# Pre-Flight Checklist v1.1 — Update Notes (Apr 27)

**Update to:** `cw_preflight_checklist_v1.md`
**Reason:** Two new findings from the F.1a session: a real ambient-event bug observed in production, and a category of issue (built-system + GCW-shaped data assumptions) that the existing categories don't cleanly cover.

These are **additions**, not edits — the v1 categories all stand. v1.1 adds one new entry to Category A and one new top-level category (F).

---

## New entry — Category A.4: Ambient/world-event broadcast scope

**Symptom (observed Apr 27):** A `[CANTINA] A fight has broken out in the cantina!` event fires while the player is in a docking bay. The announcement reaches every connected player regardless of their physical zone.

**Root cause:** `engine/world_events.py::_broadcast_activation` (line 451-456) calls `session_mgr.broadcast(text)` unconditionally. It captures `event.zones_affected` (a list like `["cantina"]`) into the event record, but the broadcast itself is global — the zone scope is data-only, never enforced at delivery.

```python
# Current behavior:
zone_name = ", ".join(...) if event.zones_affected else "Mos Eisley"
text = edef.announce_text.replace("{zone_name}", zone_name)
await session_mgr.broadcast(f"\n  {text}")   # <-- broadcasts to ALL players
```

The same broadcast pattern is used for `_broadcast_expiry`, so the same scoping issue applies.

**Suggested fix scope (small):** Replace the unconditional `session_mgr.broadcast` with a filtered iteration that resolves each session's current room → zone, and only delivers if the zone is in `event.zones_affected` (or if `zones_affected` is empty, which is the "global event" case the existing data uses for things like the comet flyby).

The work touches one file (`engine/world_events.py`), maybe ~30 lines, with a unit test that mocks two sessions in different zones and asserts only the cantina-zone session received the text. Worth doing before CW pivot because the same code path will fire in CW (cantina brawls don't cease to be a thing) and the same misfire is era-agnostic.

**Why this belongs in Category A:** It's a built system (`world_events` is wired up and live) where the wire-up is structurally incomplete. The zone scoping was clearly designed (the data field exists and is populated correctly) but the consumer side never used it. Same shape as A.1 (encounter manager built but never registered) and A.3 (registrars defined but never called) — built-but-incompletely-wired.

**Pre-pivot triage:** The bug is annoying but not blocking — players will see the wrong flavor text. Schedule before CW pivot if budget allows; defer to post-launch if not. Not a hard pre-pivot prerequisite.

---

## New category — Category F: GCW-shaped data assumptions in supposedly era-agnostic systems

This category covers a pattern distinct from B (hardcoded faction strings) and A (built-but-unwired): systems that are **conceptually era-agnostic** (ambient events, world events, encounter manager) but whose data shape was **authored against GCW assumptions** in ways that won't transfer cleanly.

The cantina-fight-in-docking-bay incident is partly Category A (broadcast bug), but also partly this — the event data is era-agnostic mechanically, but `data/ambient_events.yaml` and the `EventDef` literals in `engine/world_events.py` are 100% GCW-flavored. Examples:

- `EventType.IMPERIAL_PATROL` — currently a fixed event def keyed on Imperial troopers.
- `EventType.SANDSTORM` (line 137) — fine for Tatooine, but in CW with a Coruscant or Geonosis pivot, sandstorms aren't the right ambient.
- `EventType.CANTINA_BRAWL` — works in CW too, but the announcement text says "tables" and "glass," which is fine until the cantina is a Geonosian hive instead.
- `data/ambient_events.yaml::cantina:` — 12 lines of which one mentions "Corellian whiskey," another "Jawa," another "Devaronian." None Imperial-coded specifically; some era-coded (the Corellian whiskey is fine, the Jawa is Tatooine-coded so wouldn't fit Coruscant).

**The Category B/F distinction:**

- **Category B** — hardcoded strings like `"Imperial"` in faction-typed code paths. Surfaces as: NPC says wrong thing, encounter has wrong faction. Fix: `era_strings.yaml` indirection.
- **Category F** — data files authored with GCW-specific event types and flavor. Surfaces as: ambient flavor is wrong-flavored for the new era's worlds. Fix: per-era `ambient_events.yaml` (or move to `data/worlds/<era>/ambient_events.yaml`, which the F.0 work already started for the director config).

**Recommended approach:**

1. **F.1 — Per-era ambient events.** Move `data/ambient_events.yaml` to `data/worlds/<era>/ambient_events.yaml` (the GCW one already exists at `data/worlds/gcw/ambient_events.yaml` per the era.yaml's `content_refs.ambient_events` entry — but `engine/ambient_events.py` doesn't read it yet, which is part of why ambient events still feel GCW-shaped). Same model as the F.0 world-loader pattern: era.yaml points at the file, loader honors the pointer.

2. **F.2 — Per-era world events.** `engine/world_events.py` has the `EventDef` table inline. Either move to YAML and load per era, or split into era-keyed Python modules (`engine/world_events_gcw.py`, `engine/world_events_cw.py`). YAML is the cleaner answer given F.0's direction.

3. **F.3 — Audit other "built but GCW-shaped" systems.** Likely candidates from a quick grep:

```bash
grep -rln "Imperial\|Empire\|stormtrooper" engine/ | head -20
```

Returns 30+ files. Most overlap with B.1 already, but a few will be Category F: data tables embedded in code that were authored Imperial-flavor and need re-keying.

**Pre-pivot triage:** F.1 (per-era ambient) is high-value because ambient is the most player-visible "feels like the right era" surface. F.2 (per-era world events) similar. F.3 (audit) is cheap to run, expensive to fix — schedule the audit before CW work starts so the actual remediation can happen in parallel with content authoring.

---

## What this v1.1 update does NOT do

- Does not change Categories A.1, A.2, A.3, B.1, B.2, C, D, E from v1 — they all stand.
- Does not change the "how to use this checklist before the pivot" section's seven-step list — those steps remain accurate.
- Does not propose code changes; it just adds findings.
- Does not implement F.1 or F.2 — those are scoped as future drops.

The v1 checklist's overall point still holds: the pre-flight is a **discovery process**, and discoveries like the cantina-brawl-in-docking-bay incident are exactly the value the checklist was created to capture before they bite during pivot.

---

*End of v1.1 update notes.*
