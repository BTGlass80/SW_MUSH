# -*- coding: utf-8 -*-
"""
engine/world_lore.py — World Lore System (Lorebook Pattern) for SW_MUSH.

Keyword-triggered context injection for Director AI and NPC dialogue.
Instead of carrying the entire world state in every prompt, relevant
lore entries are dynamically loaded based on current game context.

Design source: competitive_analysis_feature_designs_v1.md §C
Expanded: sourcebook_mining_crafting_exp_design_v1.md §2

Schema: world_lore table with keyword matching + zone scope filtering.
Cache: In-memory, refreshed every 5 minutes from DB.
"""

from __future__ import annotations
import logging
import time
from typing import Optional

log = logging.getLogger(__name__)

# ── Schema ────────────────────────────────────────────────────────────────────

WORLD_LORE_SCHEMA = """
CREATE TABLE IF NOT EXISTS world_lore (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    title       TEXT NOT NULL,
    keywords    TEXT NOT NULL,
    content     TEXT NOT NULL,
    category    TEXT NOT NULL DEFAULT 'general',
    zone_scope  TEXT,
    priority    INTEGER DEFAULT 5,
    active      INTEGER DEFAULT 1,
    created_at  REAL NOT NULL,
    updated_at  REAL
);

CREATE INDEX IF NOT EXISTS idx_world_lore_active ON world_lore(active);
"""


async def ensure_lore_schema(db) -> None:
    """Create world_lore table if it doesn't exist. Idempotent."""
    try:
        for stmt in WORLD_LORE_SCHEMA.strip().split(";"):
            stmt = stmt.strip()
            if stmt:
                await db.execute(stmt)
        await db.commit()
        log.info("[world_lore] Schema ensured.")
    except Exception as e:
        log.warning("[world_lore] Schema creation failed: %s", e)


# ── Cache ─────────────────────────────────────────────────────────────────────

_lore_cache: list[dict] = []
_cache_ts: float = 0.0
_CACHE_TTL = 300.0  # 5 minutes


async def _refresh_cache(db) -> list[dict]:
    """Load all active lore entries from DB into memory cache."""
    global _lore_cache, _cache_ts
    try:
        rows = await db.fetchall(
            "SELECT * FROM world_lore WHERE active = 1 ORDER BY priority DESC"
        )
        _lore_cache = [dict(r) for r in rows]
        _cache_ts = time.time()
        log.debug("[world_lore] Cache refreshed: %d entries", len(_lore_cache))
    except Exception as e:
        log.warning("[world_lore] Cache refresh failed: %s", e)
        if not _lore_cache:
            _lore_cache = []
    return _lore_cache


async def _get_entries(db) -> list[dict]:
    """Get cached lore entries, refreshing if stale."""
    if time.time() - _cache_ts > _CACHE_TTL or not _lore_cache:
        return await _refresh_cache(db)
    return _lore_cache


def clear_cache() -> None:
    """Force cache refresh on next access."""
    global _cache_ts
    _cache_ts = 0.0


# ── Keyword Matching ──────────────────────────────────────────────────────────

async def get_relevant_lore(
    db,
    context_text: str,
    zone_id: str = "",
    max_entries: int = 5,
    max_chars: int = 1200,
) -> list[dict]:
    """Find lore entries whose keywords match the context text.

    Args:
        db: Database instance.
        context_text: Text to scan for keyword matches (player dialogue,
                      zone names, faction names, recent events).
        zone_id: Current zone for scope filtering. Entries with zone_scope
                 only match if zone_id is in their scope list.
        max_entries: Maximum number of entries to return.
        max_chars: Maximum total content characters (rough token proxy).

    Returns:
        List of matched lore entry dicts, sorted by priority (highest first).
    """
    entries = await _get_entries(db)
    if not entries or not context_text:
        return []

    context_lower = context_text.lower()
    matches = []

    for entry in entries:
        # Zone scope check
        scope = entry.get("zone_scope", "")
        if scope:
            scope_zones = [z.strip().lower() for z in scope.split(",")]
            if zone_id and zone_id.lower() not in scope_zones:
                continue
            elif not zone_id:
                # If no zone_id provided, skip zone-scoped entries
                continue

        # Keyword match — any keyword present in context
        raw_kw = entry.get("keywords", "")
        keywords = [k.strip().lower() for k in raw_kw.split(",") if k.strip()]
        match_count = sum(1 for kw in keywords if kw in context_lower)
        if match_count > 0:
            matches.append((match_count, entry))

    # Sort by priority (desc), then match count (desc)
    matches.sort(key=lambda x: (x[1].get("priority", 5), x[0]), reverse=True)

    # Fit within character budget
    result = []
    total_chars = 0
    for _mc, entry in matches:
        content_len = len(entry.get("content", ""))
        if total_chars + content_len > max_chars:
            if result:
                break  # Already have some entries, stop
            # First entry — include even if over budget (truncated)
        result.append(entry)
        total_chars += content_len
        if len(result) >= max_entries:
            break

    return result


def format_lore_block(entries: list[dict], label: str = "WORLD CONTEXT") -> str:
    """Format matched lore entries into a prompt injection block.

    Returns an empty string if no entries.
    """
    if not entries:
        return ""
    lines = [f"\n{label}:"]
    for e in entries:
        cat = e.get("category", "general").upper()
        title = e.get("title", "")
        content = e.get("content", "")
        lines.append(f"  [{cat}] {title}: {content}")
    return "\n".join(lines)


# ── CRUD ──────────────────────────────────────────────────────────────────────

async def add_lore(
    db,
    title: str,
    keywords: str,
    content: str,
    category: str = "general",
    zone_scope: str = "",
    priority: int = 5,
) -> dict:
    """Add a new lore entry. Returns {ok, msg, id}."""
    if not title or not keywords or not content:
        return {"ok": False, "msg": "Title, keywords, and content are required."}
    if len(content) > 1000:
        return {"ok": False, "msg": "Content must be under 1000 characters."}
    if len(title) > 100:
        return {"ok": False, "msg": "Title must be under 100 characters."}

    now = time.time()
    try:
        cursor = await db.execute(
            "INSERT INTO world_lore (title, keywords, content, category, "
            "zone_scope, priority, active, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, 1, ?, ?)",
            (title, keywords.lower(), content, category.lower(),
             zone_scope or None, priority, now, now),
        )
        await db.commit()
        clear_cache()
        return {"ok": True, "msg": f"Lore '{title}' added.", "id": cursor.lastrowid}
    except Exception as e:
        log.warning("[world_lore] add_lore failed: %s", e)
        return {"ok": False, "msg": f"Database error: {e}"}


async def edit_lore(
    db,
    lore_id: int,
    **kwargs,
) -> dict:
    """Update fields on an existing lore entry."""
    allowed = {"title", "keywords", "content", "category", "zone_scope",
               "priority", "active"}
    updates = {k: v for k, v in kwargs.items() if k in allowed and v is not None}
    if not updates:
        return {"ok": False, "msg": "No valid fields to update."}

    updates["updated_at"] = time.time()
    if "keywords" in updates:
        updates["keywords"] = updates["keywords"].lower()

    set_clause = ", ".join(f"{k} = ?" for k in updates)
    values = list(updates.values()) + [lore_id]

    try:
        await db.execute(
            f"UPDATE world_lore SET {set_clause} WHERE id = ?", values
        )
        await db.commit()
        clear_cache()
        return {"ok": True, "msg": f"Lore #{lore_id} updated."}
    except Exception as e:
        log.warning("[world_lore] edit_lore failed: %s", e)
        return {"ok": False, "msg": f"Database error: {e}"}


async def disable_lore(db, lore_id: int) -> dict:
    """Deactivate a lore entry (soft delete)."""
    return await edit_lore(db, lore_id, active=0)


async def search_lore(db, query: str, include_inactive: bool = False) -> list[dict]:
    """Search lore by title or keywords."""
    where = "" if include_inactive else "AND active = 1"
    try:
        rows = await db.fetchall(
            f"SELECT * FROM world_lore WHERE "
            f"(LOWER(title) LIKE ? OR LOWER(keywords) LIKE ?) {where} "
            f"ORDER BY priority DESC LIMIT 20",
            (f"%{query.lower()}%", f"%{query.lower()}%"),
        )
        return [dict(r) for r in rows]
    except Exception as e:
        log.warning("[world_lore] search failed: %s", e)
        return []


async def get_all_lore(db, include_inactive: bool = False) -> list[dict]:
    """Get all lore entries."""
    where = "WHERE active = 1" if not include_inactive else ""
    try:
        rows = await db.fetchall(
            f"SELECT * FROM world_lore {where} ORDER BY priority DESC, id ASC"
        )
        return [dict(r) for r in rows]
    except Exception as e:
        log.warning("[world_lore] get_all failed: %s", e)
        return []


# ── Seed Data ─────────────────────────────────────────────────────────────────
# 40 entries: 12 original + 28 sourcebook-mined.
# Sources: WEG40092 (Imperial Sourcebook), WEG40069 (GG7 Mos Eisley),
#          WEG40124 (GG1 A New Hope), WEG40027 (GG6 Tramp Freighters),
#          WEG40048 (GM Screen), WEG40093 (SW Sourcebook 2nd Ed)

SEED_ENTRIES = [
    # ── ORIGINAL 12 ───────────────────────────────────────────────
    {
        "title": "The Galactic Empire",
        "keywords": "empire,imperial,emperor,palpatine,stormtrooper,vader,star destroyer",
        "content": "The Galactic Empire rules through military might. Emperor Palpatine dissolved the Senate. The Imperial military includes stormtroopers, Star Destroyers, and TIE fighters. The Death Star was recently destroyed at Yavin. Dissent is crushed ruthlessly.",
        "category": "faction",
        "priority": 8,
    },
    {
        "title": "The Rebel Alliance",
        "keywords": "rebel,rebellion,alliance,mon mothma,princess leia,yavin",
        "content": "The Rebel Alliance fights to restore the Republic. Operating from hidden bases, they rely on guerrilla tactics. The destruction of the Death Star at Yavin was their greatest victory. They recruit secretly in every system.",
        "category": "faction",
        "priority": 8,
    },
    {
        "title": "The Hutt Cartel",
        "keywords": "hutt,jabba,cartel,crime lord,criminal",
        "content": "The Hutt Cartel controls criminal enterprise across the Outer Rim. Jabba the Hutt rules from his palace on Tatooine. They deal in spice, slaves, and contraband. Crossing a Hutt means a bounty on your head.",
        "category": "faction",
        "priority": 7,
    },
    {
        "title": "Mos Eisley",
        "keywords": "mos eisley,cantina,docking bay,tatooine spaceport",
        "content": "Mos Eisley is a lawless spaceport on Tatooine in the Outer Rim. The Hutt Cartel holds real power here. The cantina is the social hub for smugglers, bounty hunters, and criminals. Imperial patrols are present but stretched thin. Water and shade are precious.",
        "category": "location",
        "zone_scope": "tatooine_mos_eisley,tatooine_outskirts,tatooine_docking",
        "priority": 7,
    },
    {
        "title": "Nar Shaddaa",
        "keywords": "nar shaddaa,smuggler's moon,vertical city,hutt moon",
        "content": "Nar Shaddaa is the Smuggler's Moon — a vertical city of neon and squalor orbiting Nal Hutta. Every vice is for sale. The Hutts control everything from the upper casino towers to the toxic undercity. Imperial customs is overwhelmed and corrupt.",
        "category": "location",
        "zone_scope": "nar_shaddaa_upper,nar_shaddaa_lower,nar_shaddaa_undercity",
        "priority": 7,
    },
    {
        "title": "Kessel",
        "keywords": "kessel,spice mines,kessel run,maw",
        "content": "Kessel is a prison world famous for its spice mines. Imperial guards run the operation with brutal efficiency. The Kessel Run — a dangerous smuggling route near the Maw black hole cluster — is legendary among pilots.",
        "category": "location",
        "zone_scope": "kessel_mines",
        "priority": 7,
    },
    {
        "title": "Corellia",
        "keywords": "corellia,coronet,corsec,corellian,shipyard",
        "content": "Corellia is an industrial Core world famous for its shipyards and independent-minded people. Coronet City is the capital. CorSec maintains law and order with professional efficiency. The Empire maintains a careful presence — push too hard and Corellians push back.",
        "category": "location",
        "zone_scope": "corellia_coronet,corellia_outskirts",
        "priority": 7,
    },
    {
        "title": "Bounty Hunters' Guild",
        "keywords": "bounty hunter,guild,contract,target,wanted",
        "content": "The Bounty Hunters' Guild operates across the galaxy with Imperial sanction. Members take contracts to capture or eliminate targets. The Guild maintains strict rules about poaching and territory. Guild hunters can operate in Imperial space without harassment.",
        "category": "faction",
        "priority": 6,
    },
    {
        "title": "The Force",
        "keywords": "force,jedi,sith,lightsaber,dark side,light side",
        "content": "The Force is an energy field connecting all living things. The Jedi Order was destroyed by the Empire. Force-sensitives are hunted. Using the Force openly is extremely dangerous — Imperial Inquisitors seek out any sign of Force ability.",
        "category": "history",
        "priority": 9,
    },
    {
        "title": "Galactic Credits",
        "keywords": "credits,money,currency,payment,economy",
        "content": "Imperial credits are the standard currency. The Outer Rim also accepts barter and Hutt currency. A meal costs 5-10 credits, a blaster pistol 500, a used freighter 25,000-75,000. Most people in the Outer Rim live on a few hundred credits a week.",
        "category": "item",
        "priority": 4,
    },
    {
        "title": "Smuggling",
        "keywords": "smuggling,contraband,cargo,spice,customs,inspection",
        "content": "Smuggling is a major industry in the Outer Rim. Common contraband includes spice, weapons, and Rebel supplies. Imperial customs inspections are a constant threat. Skilled smugglers modify their ships with hidden cargo compartments.",
        "category": "history",
        "priority": 5,
    },
    {
        "title": "Wuher the Bartender",
        "keywords": "wuher,bartender,cantina bar,no droids",
        "content": "Wuher is the ill-tempered Human bartender at Chalmun's Cantina in Mos Eisley. He famously doesn't serve droids. He hears everything and shares nothing — unless properly motivated with credits.",
        "category": "npc",
        "zone_scope": "tatooine_mos_eisley",
        "priority": 5,
    },

    # ── IMPERIAL ORGANIZATION (WEG40092) ──────────────────────────
    {
        "title": "Imperial Military Structure",
        "keywords": "imperial,military,navy,army,sector group,fleet",
        "content": "The Imperial military has two branches: the Imperial Navy (space) and Imperial Army (ground). A Sector Group typically includes 24 Star Destroyers, 1,600 smaller warships, and support vessels. Stormtroopers are separate from both branches and answer directly to the Emperor.",
        "category": "faction",
        "priority": 6,
    },
    {
        "title": "Moffs and Grand Moffs",
        "keywords": "moff,grand moff,tarkin,sector,governor,regional",
        "content": "Moffs govern entire sectors of the Empire. Grand Moffs command multiple sectors with even greater military resources. Grand Moff Tarkin devised the Doctrine of Fear — rule through terror rather than bureaucracy. After Tarkin's death at Yavin, the number of Grand Moffs is increasing as the Emperor tightens control.",
        "category": "faction",
        "priority": 6,
    },
    {
        "title": "COMPNOR",
        "keywords": "compnor,coalition,progress,propaganda,SAGroup,imperial youth",
        "content": "COMPNOR — the Commission for the Preservation of the New Order — is the Empire's propaganda and civilian control apparatus. It includes the Sub-Adult Group (youth indoctrination), the Imperial Security Bureau (ISB), and thousands of volunteer informants who report 'treasonous' activity among citizens.",
        "category": "faction",
        "priority": 5,
    },
    {
        "title": "Imperial Intelligence",
        "keywords": "imperial intelligence,ISB,ubiqtorate,analysis,bureau,spy",
        "content": "Imperial Intelligence operates parallel to the ISB but with different methods. The Ubiqtorate coordinates all intelligence operations from a hidden location. Analysis Bureau processes data, Intelligence Bureau runs field operations, and Internal Organization Bureau handles counterintelligence. They rival the ISB for influence.",
        "category": "faction",
        "priority": 5,
    },
    {
        "title": "Stormtrooper Variants",
        "keywords": "stormtrooper,snowtrooper,seatrooper,spacetrooper,scout trooper,sandtrooper",
        "content": "Beyond standard stormtroopers, the Empire fields specialized variants: snowtroopers for polar environments, seatroopers for aquatic operations, spacetroopers in powered armor for zero-G boarding actions, scout troopers on speeder bikes for reconnaissance, and sandtroopers for desert worlds like Tatooine.",
        "category": "faction",
        "zone_scope": "tatooine_mos_eisley,tatooine_outskirts",
        "priority": 5,
    },
    {
        "title": "Imperial Star Destroyers",
        "keywords": "star destroyer,imperial,ISD,executor,super star destroyer",
        "content": "The Imperial-class Star Destroyer is 1,600 meters long with a crew of over 37,000. It carries 72 TIE fighters, 20 AT-ATs, 30 AT-STs, and a full legion of stormtroopers. The mere appearance of a Star Destroyer in a system is usually enough to quell dissent. The Super Star Destroyer Executor is over 12 kilometers long.",
        "category": "item",
        "priority": 7,
    },
    {
        "title": "TIE Fighter Corps",
        "keywords": "tie fighter,tie interceptor,tie bomber,fighter pilot,imperial pilot",
        "content": "TIE fighters lack shields and hyperdrive — cheap, fast, and expendable. TIE pilots are elite but considered disposable by command. TIE Interceptors are faster with better firepower, used by ace squadrons. TIE Bombers deliver heavy ordnance against capital ships and ground targets.",
        "category": "item",
        "priority": 5,
    },
    {
        "title": "The Tarkin Doctrine",
        "keywords": "tarkin,doctrine,fear,death star,rule,terror",
        "content": "Governor Tarkin proposed that the Empire rule through fear of force rather than force itself. The Death Star was the ultimate expression of this doctrine. After its destruction at Yavin, the Emperor doubled down — assigning Darth Vader a personal fleet and appointing more Grand Moffs with expanded military resources.",
        "category": "history",
        "priority": 7,
    },

    # ── MOS EISLEY DETAIL (WEG40069) ──────────────────────────────
    {
        "title": "Mos Eisley Slang",
        "keywords": "slang,bantha fodder,binary,bloated one,jawa trader,sand mine",
        "content": "Mos Eisley has its own vocabulary. 'Bantha Fodder' means worthless. 'Buy the Depp' means to die violently. 'Feed the Sarlacc' means to disappear forever. 'Jawa Trader' is anyone dishonest. 'Moisture Boy' mocks naive newcomers from farms. 'Suns-scorched ball' refers to Tatooine itself.",
        "category": "location",
        "zone_scope": "tatooine_mos_eisley,tatooine_outskirts,tatooine_docking",
        "priority": 4,
    },
    {
        "title": "Chalmun's Cantina Operations",
        "keywords": "cantina,chalmun,wuher,modal nodes,figrin,band,no droids",
        "content": "Chalmun's Cantina is owned by a Wookiee named Chalmun who won it in a sabacc game. Wuher tends bar and enforces the no-droids policy. Figrin Da'n and the Modal Nodes provide entertainment. The cantina serves as neutral ground — violence is discouraged but not uncommon. The back rooms host private deals.",
        "category": "location",
        "zone_scope": "tatooine_mos_eisley",
        "priority": 6,
    },
    {
        "title": "Gep's Grill and the Market Place",
        "keywords": "market,gep,grill,bantha burger,fillin,norun,whiphid",
        "content": "The Market Place is an open-air bazaar where farmers sell produce and hunters trade meat. Gep's Grill sells Bantha Burgers for 1.5 credits and Dewback Ribs. The stall owners Fillin Ta and Norun Gep are Whiphid meat traders who also run small-scale smuggling on the side.",
        "category": "location",
        "zone_scope": "tatooine_mos_eisley",
        "priority": 4,
    },
    {
        "title": "Spaceport Express",
        "keywords": "spaceport express,omon gantum,messenger,courier,delivery",
        "content": "Spaceport Express is a messenger and courier service run by the Quarren Omon Gantum. It handles legal goods but has been infiltrated by smugglers using it to move contraband. The service is popular because it asks few questions about package contents.",
        "category": "location",
        "zone_scope": "tatooine_mos_eisley",
        "priority": 3,
    },

    # ── TATOOINE WILDERNESS (WEG40124) ────────────────────────────
    {
        "title": "Jawa Society",
        "keywords": "jawa,sandcrawler,scavenger,droid,ion blaster,trade",
        "content": "Jawas are meter-tall scavengers who roam Tatooine's deserts in massive sandcrawlers. They salvage droids and technology from crashed ships, repairing and reselling them to moisture farmers. Jawas travel in clans of 20-30 and communicate in a rapid, chittering trade language.",
        "category": "species",
        "zone_scope": "tatooine_outskirts,tatooine_mos_eisley",
        "priority": 5,
    },
    {
        "title": "Tusken Raiders",
        "keywords": "tusken,sand people,raider,gaderffii,bantha,desert,attack",
        "content": "Tusken Raiders are fierce nomadic warriors native to Tatooine. They consider all water and territory their birthright and attack settlers who encroach on their lands. They ride single-file on banthas to hide their numbers, wield gaderffii sticks, and fire crude cycler rifles.",
        "category": "species",
        "zone_scope": "tatooine_outskirts",
        "priority": 6,
    },
    {
        "title": "Tatooine's Twin Suns",
        "keywords": "tatooine,tatoo,twin suns,desert,moisture,water,heat",
        "content": "Tatooine orbits the twin suns Tatoo I and Tatoo II. The brutal heat makes water the most precious commodity. Moisture farms extract water from the atmosphere using vaporators. Sandstorms can blind ship sensors and cut off settlements for weeks. The mining industry that sustained Mos Eisley collapsed long ago.",
        "category": "location",
        "zone_scope": "tatooine_mos_eisley,tatooine_outskirts",
        "priority": 6,
    },
    {
        "title": "Owen and Beru Lars",
        "keywords": "lars,owen,beru,moisture farm,luke,homestead",
        "content": "Owen Lars was a moisture farmer who raised Luke Skywalker. He and his wife Beru were murdered by stormtroopers searching for stolen Death Star plans. The Lars homestead is now abandoned. Owen was a hard-working, protective man who wanted to keep Luke from the wider galaxy.",
        "category": "history",
        "zone_scope": "tatooine_outskirts",
        "priority": 5,
    },

    # ── TRADING & ECONOMY (WEG40027) ──────────────────────────────
    {
        "title": "Speculative Trading",
        "keywords": "trade,cargo,speculative,buy,sell,profit,merchant",
        "content": "Speculative trading means buying cargo at one planet and selling at another for profit. It requires capital, market knowledge, and bargaining skill. Trading houses with established contacts dominate — independent traders compete on the margins. Roughly 20 percent of experienced traders' deals go sour.",
        "category": "item",
        "priority": 5,
    },
    {
        "title": "Trade Good Categories",
        "keywords": "trade goods,low tech,high tech,metals,minerals,luxury,foodstuffs,medicinal",
        "content": "The galaxy trades in eight categories: Low Technology (crafts, cloth), Mid Technology (textiles, mechanical weapons), High Technology (computers, lasers), Metals (steel, iron), Minerals (ores, salt), Luxury Goods (spices, gems, art), Foodstuffs (grain, meat), and Medicinal Goods (drugs, herbs).",
        "category": "item",
        "priority": 4,
    },
    {
        "title": "Drop-Point Delivery",
        "keywords": "delivery,cargo,drop point,freight,hauling,fee,transport",
        "content": "Drop-point delivery is the bread and butter of tramp freighters — hauling cargo from A to B for a fee. Standard fees are 5-10 credits per ton per day based on a x2 hyperdrive. Safest income but least profitable. Finding customers requires a bureaucracy skill check.",
        "category": "item",
        "priority": 4,
    },
    {
        "title": "The Black Market",
        "keywords": "black market,illegal,contraband,fence,restricted,underground",
        "content": "The black market operates on every populated world. Finding a contact requires a streetwise roll. Black marketeers sell legal goods at x2, restricted at x4, illegal at x5 their base price. They buy at x0.5 to x2.5 depending on legality. Imperial infraction classes range from 1 (ship impounded, prison) to 5 (fines).",
        "category": "item",
        "priority": 5,
    },
    {
        "title": "Loan Sharks",
        "keywords": "loan,shark,debt,payment,interest,credit,borrow",
        "content": "Loan sharks offer credits at crushing interest rates. Miss one payment and you get a warning. Miss two and you get a beating. Miss three and bounty hunters come calling. Smart captains avoid loans — but sometimes a ship modification or emergency repair leaves no other option.",
        "category": "item",
        "priority": 4,
    },

    # ── SHIP SYSTEMS (WEG40048 + WEG40027) ────────────────────────
    {
        "title": "Ship Modification Basics",
        "keywords": "modification,ship,upgrade,install,shipyard,repair,customize",
        "content": "Ship modifications cost money and cargo space. Ion drives, shields, hull, and weapons all add weight that reduces cargo capacity. Used parts cost 50 percent less but break more often. A mechanic can install modifications themselves with starship repair rolls, cutting labor cost by half.",
        "category": "item",
        "priority": 5,
    },
    {
        "title": "Hyperdrive Classes",
        "keywords": "hyperdrive,multiplier,x1,x2,backup,hyperspace,jump",
        "content": "Hyperdrive multipliers determine travel speed — lower is faster. Military-grade x1 costs 15,000 credits and weighs 18 tons. Stock freighters typically have x2 (10,000 credits). Removing a backup hyperdrive frees cargo space but risks stranding in deep space.",
        "category": "item",
        "priority": 5,
    },
    {
        "title": "Astrogation Hazards",
        "keywords": "astrogation,mishap,hyperspace,navigation,off course,mynock",
        "content": "Astrogation errors can be catastrophic. Standard journeys require difficulty 11-15. Without a nav computer, difficulty jumps to 21-30. Mishaps include hyperdrive cutout, radiation fluctuations, going off-course, mynock infestations, close calls with gravity wells, and collisions.",
        "category": "item",
        "priority": 5,
    },
    {
        "title": "Docking Fees and Ship Costs",
        "keywords": "docking,fee,hangar,spaceport,maintenance,fuel,restock",
        "content": "Standard-class spaceports charge 50 credits per day for docking. Imperial-class ports charge up to 150. Maintenance costs 10 credits multiplied by crew plus passengers, times days since last restock. Lightly damaged ships cost 1,000 credits to repair, heavily damaged 2,000, severely damaged 3,000.",
        "category": "item",
        "priority": 4,
    },

    # ── GALACTIC LORE (WEG40092 + WEG40093) ───────────────────────
    {
        "title": "Imperial Customs Operations",
        "keywords": "customs,inspection,scan,cargo,manifest,permit,patrol",
        "content": "Imperial Customs uses patrol ships and boarding parties to inspect cargo. Outer Rim patrols are infrequent and understaffed — agents can often be bribed. Core world inspections are thorough. A captain must apply for weapon permits — bureaucracy vs. weapon damage code determines approval.",
        "category": "faction",
        "priority": 5,
    },
    {
        "title": "Imperial Law Infractions",
        "keywords": "infraction,crime,class,punishment,impound,fine,arrest",
        "content": "The Empire classifies spacer crimes in five classes. Class One (conspiracy, cloaking devices, attacking Imperial ships): ship impounded, 5-30 years prison. Class Two (illegal weapons, rated-X goods): arrest, heavy fines. Class Three (customs evasion): fines 2,000-10,000. Class Four (expired permits): fines 500-2,000. Class Five (paperwork errors): warnings.",
        "category": "faction",
        "priority": 5,
    },
    {
        "title": "Corellian Shipyards",
        "keywords": "corellian,CEC,shipyard,engineering,YT,freighter,corvette",
        "content": "Corellian Engineering Corporation produces the galaxy's most popular starships, including YT-series freighters and CR90 corvettes. Corellians have a reputation as exceptional pilots and engineers. The shipyards in Coronet City are among the largest non-Imperial facilities in the galaxy.",
        "category": "location",
        "zone_scope": "corellia_coronet",
        "priority": 5,
    },
    {
        "title": "Nar Shaddaa Criminal Networks",
        "keywords": "nar shaddaa,hutt,criminal,network,undercity,spice,vice",
        "content": "Nar Shaddaa's criminal networks operate in layers. The Hutt Cartel controls the macro economy from upper towers. Mid-level operators work the promenades and cantinas. The Undercity harbors the desperate: gangs, fugitives, debtors, and those who have fallen through every safety net the galaxy never had.",
        "category": "location",
        "zone_scope": "nar_shaddaa_upper,nar_shaddaa_lower,nar_shaddaa_undercity",
        "priority": 6,
    },
    {
        "title": "Kessel Spice Mining",
        "keywords": "kessel,spice,mine,glitterstim,prisoner,imperial,warden",
        "content": "Kessel's spice mines are among the most brutal labor operations in the galaxy. Prisoners mine glitterstim spice in absolute darkness — it is light-sensitive. Imperial wardens run the operation ruthlessly. Guards are well-armed but poorly motivated, many serving punishment postings.",
        "category": "location",
        "zone_scope": "kessel_mines",
        "priority": 6,
    },

    # ── CREATURES (WEG40093) ──────────────────────────────────────
    {
        "title": "Banthas",
        "keywords": "bantha,beast,mount,tusken,tatooine,herd",
        "content": "Banthas are massive, shaggy beasts native to Tatooine. They serve as mounts for Tusken Raiders and as livestock. Bantha meat is a staple food. An adult bantha stands over 2 meters tall and weighs several tons. They are docile unless provoked and form deep bonds with Tusken riders.",
        "category": "species",
        "zone_scope": "tatooine_outskirts",
        "priority": 4,
    },
    {
        "title": "Dewbacks",
        "keywords": "dewback,lizard,mount,patrol,imperial,desert",
        "content": "Dewbacks are large reptiles used as patrol mounts on Tatooine. Imperial sandtroopers ride them through Mos Eisley's streets. They are cold-blooded and sluggish at night but well-adapted to desert heat. Dewback meat is edible and sold at market stalls.",
        "category": "species",
        "zone_scope": "tatooine_outskirts,tatooine_mos_eisley",
        "priority": 4,
    },
    {
        "title": "Mynocks",
        "keywords": "mynock,parasite,ship,power,silicon,space,pest",
        "content": "Mynocks are silicon-based parasites that attach to starships and feed on power cables. They inhabit asteroid fields, derelict ships, and dark spaces between stars. A mynock infestation can drain a ship's power systems. Common hazard for ships in debris fields or poorly-maintained stations.",
        "category": "species",
        "priority": 4,
    },
    {
        "title": "The Rancor",
        "keywords": "rancor,jabba,pit,monster,dathomir,beast",
        "content": "Rancors are massive carnivores native to Dathomir. Jabba the Hutt kept one beneath his throne room, feeding it prisoners. Standing over 5 meters tall with razor claws and armored hide, a rancor is nearly impossible to kill with personal weapons. Luke Skywalker killed Jabba's rancor by crushing it under a gate.",
        "category": "species",
        "zone_scope": "tatooine_outskirts",
        "priority": 5,
    },

    # ── GG10 Bounty Hunters (WEG40073) ────────────────────────────────────────

    {
        "title": "The Bounty Hunter Creed",
        "keywords": "bounty,hunter,creed,acquisition,code,ethics,honor",
        "content": "Most bounty hunters adhere to an unwritten code of ethics called the Bounty Hunter Creed. Three rules define it. First: People Don't Have Bounties, Only Acquisitions Have Bounties — once a bounty is posted, the target loses their rights and becomes an 'acquisition.' Second: Capture By Design, Kill By Necessity — killing is business, but unnecessary killing is murder. Third: No Hunter Shall Slay Another Hunter — hunters consider themselves a special breed and never take up arms against a fellow hunter who follows the creed. Those who break the creed become acquisitions themselves.",
        "category": "faction",
        "priority": 6,
    },
    {
        "title": "Imperial Peace-Keeping Certificate",
        "keywords": "IPKC,license,bounty,hunter,permit,imperial,certificate,legal",
        "content": "An Imperial Peace-Keeping Certificate is the license required to operate as a bounty hunter in the Empire. It costs 500 credits and must be renewed annually. The IPKC entitles the holder to carry weapons that would otherwise be illegal and to transport captured individuals. It is valid in most regions, though some Core Worlds prohibit bounty hunting entirely. Imperial officials review the holder's record at each renewal — flagrant violations of Imperial law can result in revocation, though the Empire usually prefers token fines and stern warnings.",
        "category": "faction",
        "priority": 5,
    },
    {
        "title": "Imperial Enforcement DataCore",
        "keywords": "datacore,bounty,IOCI,database,posting,wanted,criminal",
        "content": "The Imperial Enforcement DataCore is a specialized database maintained by the Imperial Office of Criminal Investigations. It lists all legal bounties in the Empire — who is wanted, by whom, and for how much. Hunters access it at local Imperial offices or through posting agencies and guild houses. A datacard listing a specific bounty costs 10 credits. Searching boards on other planets costs 50 credits. Posting agencies charge 10 to 25 credits per day for DataCore access and maintain their own supplemental intelligence on targets.",
        "category": "faction",
        "priority": 5,
    },
    {
        "title": "Bounty Classifications",
        "keywords": "bounty,classification,most wanted,galactic,regional,sector,local,corporate",
        "content": "Imperial bounties fall under eight classifications. Most Wanted and Galactic postings appear on all DataCore boards across the Empire. Regional bounties cover multiple sectors. Sector, System, and Local bounties are progressively more limited in scope. Corporate bounties are posted by companies and are only legally binding within that company's territory. A separate 'Locate and Detain' list covers individuals the Empire wants alive for questioning — killing a Locate and Detain target can result in penalties up to and including execution of the hunter.",
        "category": "faction",
        "priority": 5,
    },
    {
        "title": "Bounty Hunter Guilds",
        "keywords": "guild,syndicate,house,benelex,paramexor,neuvalis,renliss,membership",
        "content": "Bounty hunter guilds — also called syndicates or houses — are privately established organizations that broker contracts between hunters and those posting bounties. Major guilds include House Benelex (kidnapping retrievals, Outer Rim), House Neuvalis (the largest with nearly 7,000 hunters, bounties under 20,000 credits only), House Paramexor (murder contracts exclusively), and House Renliss (female hunters only, bounties on males). Guilds take a 'gap' of 3 to 10 percent from each bounty's face value. In return they provide equipment, repairs, training, intelligence, legal mediation, and sanctuary from Imperial officials.",
        "category": "faction",
        "priority": 5,
    },
    {
        "title": "Three Types of Bounty Hunters",
        "keywords": "imperial hunter,guild hunter,independent,bounty,category,type",
        "content": "Bounty hunters fall into three categories. Imperial hunters work exclusively for the Empire, taking only government-authorized bounties — they are often ex-military and receive equipment discounts and subsidized transport. Guild hunters operate through their syndicate, which assigns contracts and takes a percentage — they get equipment, training, and sanctuary but have no choice in assignments. Independent hunters work alone, taking any contract from any source — they keep everything they earn but bear all expenses and have no institutional support.",
        "category": "faction",
        "priority": 4,
    },
    {
        "title": "The SEPI Principle",
        "keywords": "SEPI,selection,evaluation,preparation,implementation,hunt,method,bounty",
        "content": "Experienced bounty hunters follow the SEPI principle — Selection, Evaluation, Preparation, and Implementation. Selection means choosing the right target based on bounty value, danger, and the hunter's strengths. Evaluation means researching the target's habits, associates, hideouts, and capabilities. Preparation means acquiring permits, equipment, transportation, and local contacts before beginning the hunt. Implementation is the hunt itself. Hunters who skip steps — especially Evaluation and Preparation — tend to end up dead.",
        "category": "faction",
        "priority": 4,
    },
    {
        "title": "Bounty Posting Format",
        "keywords": "bounty,posting,wanted,format,alive,dead,originator,receiver,application",
        "content": "Official Imperial bounty postings follow a standard format: the target's name, species, sex, age, homeworld, and known associates; the bounty amount in credits; the classification (Galactic, Regional, Sector, etc.); application conditions (Alive, Dead or Alive, or Dead); any bonus for special conditions; determents or restrictions on methods; the crimes warranting the bounty; the originator who posted it; and the receiver to whom the acquisition must be delivered. Typical bounties range from 2,000 credits for minor sector violations to 25,000 or more for galactic-class fugitives.",
        "category": "faction",
        "priority": 4,
    },

    # ── Cracken's Rebel Field Guide (WEG40046) — Session 24 ──────────

    {
        "title": "General Airen Cracken",
        "keywords": "cracken,rebel,general,intelligence,contruum,sabotage",
        "content": "General Airen Cracken is the Rebel Alliance's chief intelligence officer. Born on Contruum, he ran a mechanic's shop before the Empire arrived. When Imperial Command demanded the planet's borium, Cracken organized his employees into a guerrilla force specializing in mechanical sabotage. His saboteurs left calling cards reading 'Cracken's Crew Says Hello.' He eventually joined the Alliance formally and rose to command through field ingenuity rather than military academy training.",
        "category": "character",
        "priority": 5,
    },
    {
        "title": "Jury-Rigging Equipment",
        "keywords": "jury-rig,modify,improve,breakdown,malfunction,repair,tinker",
        "content": "Field modification of equipment — called jury-rigging — can temporarily boost a device's performance by up to 3D, but the improvement is unreliable. Jury-rigged equipment has a chance of breakdown every time it is used. The more powerful the modification, the greater the risk. Modifications take about an hour, or one minute if rushed at higher difficulty. When jury-rigged equipment fails, weapons may explode, vehicles may lose power, and non-lethal devices simply stop working.",
        "category": "item",
        "priority": 5,
    },
    {
        "title": "Transponder Codes",
        "keywords": "transponder,code,identity,ship,boss,registration,signal",
        "content": "Every starship has a unique transponder code burned into its sublight engine. The code broadcasts the ship's name, type, owner, and registration data continuously. The code is extremely difficult to alter because it is embedded in the engine itself — tampering can fuse the wiring irreparably. False transponder codes can be added by analyzing the ship's signal and overlaying matching frequencies, but more than three false codes begin to bleed into each other and look suspicious on scanners.",
        "category": "item",
        "priority": 6,
    },
    {
        "title": "Bureau of Ships and Services (BoSS)",
        "keywords": "boss,bureau,ships,services,registration,transponder,gatherers",
        "content": "The Bureau of Ships and Services is one of the oldest institutions in the galaxy, predating the Empire by millennia. BoSS maintains records on every registered starship via transponder code tracking. The organization is technically independent — BoSS families pass positions by heredity and keep their files in nearly indecipherable internal codes. The Empire tolerates BoSS because it needs the registration system. BoSS field operatives, called Gatherers, collect data across the galaxy and are trained in computer skills, espionage, and sometimes combat.",
        "category": "faction",
        "priority": 5,
    },
    {
        "title": "Cybernetic Enhancements",
        "keywords": "cybernetics,prosthetic,enhancement,cyborg,implant,machine",
        "content": "Cybernetic enhancements are available but deeply stigmatized across the galaxy. The average citizen fears the blurring line between being and machine. People with visible prosthetics face discrimination and curtailment of civil rights. Enhanced beings often hide their modifications. The technology improves physical abilities but reportedly reduces empathy and emotional connection. Force users with cybernetics find it harder to tap the Force and are more vulnerable to the Dark Side.",
        "category": "item",
        "priority": 4,
    },
    {
        "title": "How Blasters Work",
        "keywords": "blaster,gas,xciter,galven,power pack,tibanna,bolt",
        "content": "Blasters fire by exciting gas in a chamber. The trigger opens the energy converter valve, releasing gas into the XCiter where it is energized by the power pack. The excited gas passes through the Actuating Blaster Module and is focused by the galven pattern in the barrel into a beam of intense energy. The visible light is a byproduct — the energy itself is what causes damage. Different gases produce different power levels and bolt colors. Tibanna gas from Cloud City is among the most powerful but hardest to acquire.",
        "category": "item",
        "priority": 4,
    },
    {
        "title": "Acquiring Blaster Gas",
        "keywords": "blaster,gas,tibanna,supply,piracy,donation,black market,mining",
        "content": "The Rebel Alliance acquires blaster gas through three channels: donations from sympathetic mining colonies, piracy of Imperial-allied corporate transports, and black market purchases. Cloud City is a reliable source for spin-sealed Tibanna gas, though officially the city only sells 'star drive engine coolant' to avoid Imperial attention. The Empire controls gas distribution by granting munitions monopolies to loyal corporations, making supply a constant challenge for the Alliance.",
        "category": "item",
        "priority": 4,
    },
    {
        "title": "Imperial Lift-Mines",
        "keywords": "mine,lift-mine,repulsorlift,norsam,blockade,minefield",
        "content": "The Norsam DR-X55 Imperial lift-mine floats above a planet's surface using repulsorlifts, set at specific altitudes to intercept speeders and low-flying vehicles. Top-of-the-line models detect craft up to 100 meters away and adjust altitude to intercept. Imperial policy staggers mines at different heights — low mines against speeder bikes, mid-range against landspeeders, high against airspeeders. Mine fields require a piloting maneuver roll for every mine within 20 meters of the flight path.",
        "category": "item",
        "priority": 4,
    },
    {
        "title": "Merr-Sonn Defender Ion Mines",
        "keywords": "ion,mine,space,blockade,merr-sonn,defender,cloaking",
        "content": "Merr-Sonn Defender Ion Mines are space-based weapons used to blockade planets. The mines use cloaking revvers and scatter particle beams to remain nearly invisible. When a ship comes within ten kilometers, the mine fires a powerful ion attack that neutralizes the vessel, leaving it adrift until Imperial forces arrive to board. Getting through a Defender blockade requires detecting the mines with an Easy Mechanical roll, then a starship piloting maneuver action opposed by each mine's 6D fire control.",
        "category": "item",
        "priority": 5,
    },
    {
        "title": "Computer Data Files in the Galaxy",
        "keywords": "computer,data,file,datapad,holistic,HDT,slicing,portable",
        "content": "Computer data files in the Star Wars galaxy use Holistic Data Transfer languages — AI-enhanced shorthand that lets files provide more information than they literally contain by making educated deductions. Files are rated by die codes from 1D to 13D, with higher ratings exponentially more expensive. A 4D file costs 1,000 credits while a 10D file costs 100,000. Pocket datapads store up to 5D of files, portable computers up to 20D, and capital starship computers up to 30D. MicroThrust portable computers can add their power rating as bonus dice to a programmer's skill.",
        "category": "item",
        "priority": 4,
    },
]


async def seed_lore(db, era: Optional[str] = None) -> int:
    """Insert seed lore entries, skipping any whose title already exists.

    Idempotent: safe to re-run after adding new SEED_ENTRIES.
    Returns the count of newly inserted entries.

    Drop F.6a.2: When `era` is provided, this function attempts to load
    `data/worlds/<era>/lore.yaml` via the F.6a.1 loader and seed from
    that corpus instead of `SEED_ENTRIES`. Any failure (missing file,
    parse error, validation error) falls back to `SEED_ENTRIES` with a
    warning, so booting in a partially-set-up era never breaks the lore
    system. When `era` is None (the legacy boot path), behavior is
    unchanged: seed straight from `SEED_ENTRIES`.

    The byte-equivalence assertion (`tests/test_f6a2_world_lore_yaml.py`)
    proves that loading GCW lore.yaml produces the same seeded entries
    as the hardcoded SEED_ENTRIES path.
    """
    if era is None:
        return await _seed_from_entries(db, SEED_ENTRIES)

    # Era path — try YAML, fall back to SEED_ENTRIES on any error.
    try:
        from pathlib import Path
        from engine.world_loader import load_era_manifest, load_lore as _load_lore
        manifest = load_era_manifest(Path("data") / "worlds" / era)
        corpus = _load_lore(manifest)
    except Exception as e:
        log.warning(
            "[world_lore] Era-aware seed for %r failed at load (%s); "
            "falling back to SEED_ENTRIES.", era, e,
        )
        return await _seed_from_entries(db, SEED_ENTRIES)

    if corpus is None:
        log.info(
            "[world_lore] Era %r has no lore content_ref; "
            "falling back to SEED_ENTRIES.", era,
        )
        return await _seed_from_entries(db, SEED_ENTRIES)

    if corpus.report.errors:
        log.warning(
            "[world_lore] Era %r lore.yaml has %d validation error(s); "
            "falling back to SEED_ENTRIES. First: %s",
            era, len(corpus.report.errors), corpus.report.errors[0],
        )
        return await _seed_from_entries(db, SEED_ENTRIES)

    return await seed_lore_from_corpus(db, corpus)


async def seed_lore_from_corpus(db, corpus) -> int:
    """Seed the world_lore table from a LoreCorpus produced by F.6a.1.

    Idempotent: skips any entry whose title already exists. Returns the
    count of newly inserted entries. The corpus's `.report.errors` is
    NOT re-checked here — caller is responsible for deciding whether
    to seed a corpus with errors. (`seed_lore(db, era=...)` falls back
    to SEED_ENTRIES rather than seeding a broken corpus; tools that
    want to force-seed a partial corpus can call this function directly.)
    """
    entries = [
        {
            "title":      e.title,
            "keywords":   e.keywords,
            "content":    e.content,
            "category":   e.category or "general",
            "zone_scope": e.zone_scope,
            "priority":   e.priority,
        }
        for e in corpus.entries
    ]
    return await _seed_from_entries(db, entries)


async def _seed_from_entries(db, entries: list[dict]) -> int:
    """Insert each entry whose title isn't already in world_lore.

    Shared insertion path for both `seed_lore` (legacy SEED_ENTRIES) and
    `seed_lore_from_corpus` (F.6a.1 LoreCorpus). Idempotent. Returns
    the count of newly inserted entries.
    """
    try:
        rows = await db.fetchall("SELECT title FROM world_lore")
        existing_titles = {r["title"] for r in (rows or [])}

        count = 0
        now = time.time()
        for entry in entries:
            if entry["title"] in existing_titles:
                continue  # Already present, skip
            await db.execute(
                "INSERT INTO world_lore (title, keywords, content, category, "
                "zone_scope, priority, active, created_at) "
                "VALUES (?, ?, ?, ?, ?, ?, 1, ?)",
                (entry["title"], entry["keywords"], entry["content"],
                 entry.get("category", "general"),
                 entry.get("zone_scope", None),
                 entry.get("priority", 5), now),
            )
            count += 1
        if count > 0:
            await db.commit()
            clear_cache()
        log.info("[world_lore] Seeded %d new lore entries (%d already existed).",
                 count, len(existing_titles))
        return count
    except Exception as e:
        log.warning("[world_lore] Seed failed: %s", e)
        return 0
