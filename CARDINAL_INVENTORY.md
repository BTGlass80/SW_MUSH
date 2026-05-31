# Cardinal Consistency Inventory — all six maps

**Date:** May 29 2026 · **Tool:** `tools/check_map_cardinals.py` · **Run:** `python tools/check_map_cardinals.py --all --derive`

**What this checks:** whether the gameplay exit graph's compass words agree with where rooms sit on the *rendered* map (the map YAML `x/y`, which is what the player sees and what we paint against). A "go north" exit should move the marker *up* on the map. Vertical / interior / named exits (`up`/`down`/`in`/`out`/`reception`/etc.) are not planar and are excluded. The map `x/y` is treated as spatial ground truth.

**Classification:** `ok` ≤45° off · `minor` ≤90° (approximate, acceptable) · **`MISMATCH` >90° (wrong way — must fix)** · `degenerate` (rooms co-located).

---

## Result

| Map | planar cardinals | ok | minor | **MISMATCH** | status |
|---|---|---|---|---|---|
| `kamino.tipoca_city` | 4 | 4 | 0 | **0** | ✅ clean |
| `geonosis.stalgasin_hive` | 12 | 10 | 2 | **0** | ✅ clean |
| `kuat.kuat_city` | 7 | 5 | 2 | **0** | ✅ clean |
| `nar_shaddaa.smugglers_moon` | 16 | 7 | 4 | **5** | ⚠ reconcile |
| `coruscant.senate_district` | 16 | 8 | 1 | **7** | ⚠ reconcile |
| `tatooine.mos_eisley` | 48 | 13 | 10 | **25** | ⚠ reconcile |
| **TOTAL** | 103 | 47 | 19 | **37** | — |

Three maps are already navigation-correct. Three carry wrong-way exits — 37 in total — concentrated in Mos Eisley.

---

## The pattern (this is the key to choosing a fix)

Most mismatches are **clean 180° inversions on a spine**, not random noise:

- **Senate:** the `senate_esplanade ↔ monument_plaza ↔ legislative_borough` axis is N/S-inverted — the graph says "north" where the map runs south, and vice-versa (err = 180°). The few non-180° ones are the diagonal `chancellors_avenue`/`grand_reception_hall` ↔ `legislative_borough` links.
- **Mos Eisley:** the main town spine `spaceport_row → market → government → north_end` is entirely N/S-inverted (all 180°) — "North End" sits at the *bottom* of the map — and a run of outskirts/jundland `east` exits is E/W-inverted (also 180°). The remainder are loose diagonals.
- **Nar Shaddaa:** the warrens descent (`collapsed_plaza`/`reactor_core`/`fungal_cavern`/`entry_shaft`) is inverted, plus the `fighting_pits → undercity` link.

Because they cluster as axis inversions, each affected map has **two viable fixes**, and the choice is an authorial call:

**Philosophy B — relabel directions to match the map (recommended default).** Treat the rendered `x/y` as truth and rewrite the offending compass words to the geometry-correct ones (the `--derive` proposals below). *Pros:* preserves every painting and landmark registration you've already done — zero repaint, zero re-register. *Con:* a few room *names* become geographically ironic (e.g. you'd travel "south" to reach "North End"). Cosmetic; rename the room if it bothers you.

**Philosophy A — re-place rooms to match the directions.** Flip/move the offending rooms so "north" points up. *Pro:* names and directions both read naturally. *Con:* it's not a clean global flip (Mos Eisley needs both a N/S and a partial E/W correction), and **moving rooms invalidates the painting and the landmark pins for that map** — repaint + re-register. Heavier, and it throws away work.

**Recommendation:** Philosophy B everywhere, *except* consider Philosophy A for the handful of rooms whose names would become absurd (Mos Eisley's "North End", "South End"). It's a per-map, per-room judgment — yours to make. Nothing here blocks painting (the painting only depends on `x/y`); reconcile before each map goes live, enforced by the pre-flight gate (`--gate`).

---

## Proposed corrections (Philosophy B — `--derive` output)

These are the geometry-correct direction words. **Review before applying — this is the live movement graph.** I have not auto-applied them. Tatooine/Nar Shaddaa store exits as a top-level `{from,to,forward,reverse}` list; Coruscant/Geonosis/Kamino/Kuat store them inline per room as `{direction: target_slug}` (so for the inline planets, only `forward` exists — the reverse is the opposite).

### coruscant.senate_district (7)
```
senate_esplanade     --south--> monument_plaza        forward "south" -> "north"
chancellors_avenue   --east-->  legislative_borough   forward "east"  -> "northwest"
grand_reception_hall --east-->  legislative_borough   forward "east"  -> "northwest"
legislative_borough  --north--> grand_reception_hall  forward "north" -> "southeast"
legislative_borough  --west-->  chancellors_avenue    forward "west"  -> "southeast"
legislative_borough  --south--> monument_plaza        forward "south" -> "north"
monument_plaza       --north--> senate_esplanade      forward "north" -> "south"
```

### nar_shaddaa.smugglers_moon (5)
```
enforcer_alley          --north--> westport_arrivals      forward "north" -> "southwest"
fighting_pits           --east-->  undercity_depths       forward "east"  -> "west"
warrens_fungal_cavern   --east-->  warrens_entry_shaft    forward "east"  -> "west"
warrens_reactor_core    --south--> warrens_entry_shaft    forward "south" -> "northeast"
warrens_collapsed_plaza --south--> warrens_reactor_core   forward "south" -> "north"
```

### tatooine.mos_eisley (25)
```
docking_bay_94_entrance  --north--> spaceport_row        forward "north"     -> "southeast"
spaceport_customs_office --east-->  spaceport_row        forward "east"      -> "west"
spaceport_customs_office --south--> docking_bay_94_entr  forward "south"     -> "northwest"
docking_bay_86           --west-->  spaceport_row        forward "west"      -> "east"
docking_bay_87           --east-->  spaceport_row        forward "east"      -> "southwest"
spaceport_row            --north--> market_district      forward "north"     -> "south"
market_district          --north--> government_quarter   forward "north"     -> "south"
government_quarter       --north--> north_end            forward "north"     -> "south"
market_district          --southeast--> south_end        forward "southeast" -> "north"
mos_eisley_inn           --south--> spaceport_row        forward "south"     -> "northeast"
jabbas_townhouse_entr    --southeast--> market_district  forward "southeast" -> "northwest"
police_station_main      --west-->  government_quarter   forward "west"      -> "east"
tatooine_militia_hq      --south--> government_quarter   forward "south"     -> "northeast"
control_tower            --north--> spaceport_row        forward "north"     -> "southwest"
kaysons_weapon_shop      --east-->  market_district      forward "east"      -> "northwest"
heffs_souvenirs          --northeast--> market_district  forward "northeast" -> "west"
jawa_traders             --west-->  market_district      forward "west"      -> "east"
transport_depot          --east-->  south_end            forward "east"      -> "northwest"
cutting_edge_clinic      --east-->  government_quarter   forward "east"      -> "northwest"
outskirts_speeder_track  --east-->  scavenger_market     forward "east"      -> "northwest"
outskirts_checkpoint     --east-->  eastern_gate         forward "east"      -> "west"
outskirts_trail_junction --east-->  checkpoint           forward "east"      -> "west"
jundland_canyon_mouth    --east-->  trail_junction       forward "east"      -> "west"
jundland_tusken_overlook --east-->  canyon_mouth         forward "east"      -> "west"
jundland_krayt_graveyard --east-->  tusken_overlook      forward "east"      -> "west"
```
*(reverse words mirror to the opposite of each new forward)*

> Mos Eisley's spine inversion (`spaceport→market→government→north_end` all flipping `north`→`south`, ending at a "North End" that sits at the map's south) is the clearest case where you may instead prefer **Philosophy A** — flip those spine rooms' placement so the names stay sensible. Your call; the rest of Mos Eisley's mismatches are loose diagonals best handled by relabel (B).

---

## Wiring the gate

Before any map's substrate goes live, run:
```
python tools/check_map_cardinals.py <area_key> --gate
```
Exit code 1 = unresolved wrong-way exits → fix before go-live. Add it to the substrate pre-flight so this can't regress. Kamino, Geonosis, and Kuat pass today.
