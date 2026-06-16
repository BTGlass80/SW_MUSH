# -*- coding: utf-8 -*-
"""
REST API for web character creation.

Mounts on the existing aiohttp server under /api/.
Provides read-only data endpoints (species, skills, templates),
validation, atomic account+character creation, and token-based auth.
"""
import base64
import hashlib
import hmac as _hmac
import json
import logging
import os
import time
from collections import defaultdict
from typing import TYPE_CHECKING, Optional

import yaml
from aiohttp import web

from engine.chargen_validator import (
    validate_chargen_submission,
    validate_account_fields,
    MAX_BACKGROUND_LEN,
)
from engine.character import Character, ATTRIBUTE_NAMES
from engine.creation import TEMPLATES
from engine.dice import DicePool

if TYPE_CHECKING:
    from engine.character import SkillRegistry
    from engine.species import SpeciesRegistry
    from db.database import Database

log = logging.getLogger(__name__)

# ── Token auth ──────────────────────────────────────────────────────────
#
# The HMAC secret for login tokens is persisted to a gitignored 0600 key file
# so that a server restart does not silently invalidate every outstanding token
# (which would force a mass re-auth). The path is overridable via env for tests
# and multi-instance deploys. It is loaded lazily on first token use, so merely
# importing this module (e.g. across the test suite) never creates the file.

TOKEN_SECRET_ENV_VAR = "SWMUSH_TOKEN_SECRET_FILE"
_DEFAULT_TOKEN_SECRET_FILE = "token_secret.key"
_TOKEN_SECRET_BYTES = 32
# Windows os.open defaults to TEXT mode, which would translate any 0x0A byte in
# the random secret to 0x0D0A on write and corrupt it. O_BINARY is Windows-only
# (0 elsewhere), so this is a no-op on POSIX.
_O_BINARY = getattr(os, "O_BINARY", 0)

_TOKEN_SECRET: Optional[bytes] = None


def _load_or_create_token_secret() -> bytes:
    """Return the 32-byte HMAC secret, persisting a fresh one on first run.

    Restart-stable: outstanding login tokens survive a reboot. The file is
    created 0600 (best-effort — Windows honors only the read-only bit). On any
    IO/permission failure we fall back to an ephemeral in-process secret and
    warn; auth still works, tokens just won't survive a restart (the prior
    behavior), so this degrades safely rather than failing closed.
    """
    path = os.environ.get(TOKEN_SECRET_ENV_VAR) or _DEFAULT_TOKEN_SECRET_FILE
    try:
        with open(path, "rb") as fh:
            raw = fh.read()
        if len(raw) >= _TOKEN_SECRET_BYTES:
            return raw[:_TOKEN_SECRET_BYTES]
        log.warning(
            "Token secret file %r too short (%d bytes); regenerating",
            path, len(raw),
        )
    except FileNotFoundError:
        pass
    except OSError:
        log.warning(
            "Could not read token secret file %r; using an ephemeral secret",
            path, exc_info=True,
        )
        return os.urandom(_TOKEN_SECRET_BYTES)
    secret = os.urandom(_TOKEN_SECRET_BYTES)
    # Write to a sibling temp file and atomically replace, so a failed or
    # partial write never truncates an existing valid secret (which would loop
    # token invalidation on every restart). os.replace is atomic on POSIX and
    # Windows when src/dst share a directory.
    tmp_path = path + ".tmp"
    try:
        fd = os.open(tmp_path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC | _O_BINARY, 0o600)
        try:
            os.write(fd, secret)
        finally:
            os.close(fd)
        os.replace(tmp_path, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
    except OSError:
        log.warning(
            "Could not persist token secret to %r; using an ephemeral secret "
            "(tokens will not survive a restart)",
            path, exc_info=True,
        )
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
    return secret


def _get_token_secret() -> bytes:
    """Lazily load (and process-cache) the persisted HMAC secret."""
    global _TOKEN_SECRET
    if _TOKEN_SECRET is None:
        _TOKEN_SECRET = _load_or_create_token_secret()
    return _TOKEN_SECRET


def create_login_token(account_id: int, ttl: int = 300) -> str:
    """Create a signed, expiring login token for auto-login after chargen."""
    payload = json.dumps({"aid": account_id, "exp": int(time.time()) + ttl})
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = _hmac.new(
        _get_token_secret(), payload_b64.encode(), hashlib.sha256
    ).hexdigest()[:16]
    return f"{payload_b64}.{sig}"


def verify_login_token(token: str) -> Optional[int]:
    """Verify a login token. Returns account_id or None."""
    try:
        payload_b64, sig = token.rsplit(".", 1)
        expected = _hmac.new(
            _get_token_secret(), payload_b64.encode(), hashlib.sha256
        ).hexdigest()[:16]
        if not _hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        if time.time() > payload["exp"]:
            return None
        return payload["aid"]
    except Exception:
        log.warning("Token verification failed", exc_info=True)
        return None


# ── Rate limiting ───────────────────────────────────────────────────────

_rate_limits: dict[str, list[float]] = defaultdict(list)
RATE_LIMIT_WINDOW = 60  # seconds
RATE_LIMIT_MAX = 3  # max requests per window


def _check_rate_limit(ip: str) -> bool:
    """Returns True if the request is allowed, False if rate-limited."""
    now = time.time()
    timestamps = _rate_limits[ip]
    # Prune old entries
    _rate_limits[ip] = [t for t in timestamps if now - t < RATE_LIMIT_WINDOW]
    if len(_rate_limits[ip]) >= RATE_LIMIT_MAX:
        return False
    _rate_limits[ip].append(now)
    return True


# ── Helpers ─────────────────────────────────────────────────────────────

# X-Forwarded-For is attacker-controlled unless the request actually arrives
# through a reverse proxy we operate. Trusting the leading XFF entry blindly
# lets a direct client spoof its source IP and defeat the per-IP rate limiters
# (chargen create, portal login throttle). So XFF is honored ONLY when the
# direct peer is an operator-configured trusted proxy; otherwise the direct peer
# address is used. Default (no proxies configured) = direct connection =
# peername only = un-spoofable. Configure via SWMUSH_TRUSTED_PROXIES (a
# comma-separated allowlist of the proxy IPs that sit in front of the app).
TRUSTED_PROXIES_ENV_VAR = "SWMUSH_TRUSTED_PROXIES"


def _load_trusted_proxies() -> frozenset:
    raw = os.environ.get(TRUSTED_PROXIES_ENV_VAR, "")
    return frozenset(p.strip() for p in raw.split(",") if p.strip())


_TRUSTED_PROXIES = _load_trusted_proxies()


def _get_client_ip(request: web.Request) -> str:
    """Resolve the client IP, spoof-resistant.

    Honors X-Forwarded-For only when the direct peer is a configured trusted
    proxy, in which case it returns the right-most XFF entry that is not itself
    a trusted proxy (the real client at the edge of our trusted hop chain). With
    no proxies configured (the default) XFF is ignored and the direct peer
    address is returned, so a raw-socket client cannot spoof its source IP.
    """
    transport = request.transport
    peername = transport.get_extra_info("peername") if transport else None
    peer_ip = peername[0] if peername else "unknown"
    if _TRUSTED_PROXIES and peer_ip in _TRUSTED_PROXIES:
        forwarded = request.headers.get("X-Forwarded-For")
        if forwarded:
            hops = [p.strip() for p in forwarded.split(",") if p.strip()]
            for candidate in reversed(hops):
                if candidate not in _TRUSTED_PROXIES:
                    return candidate
            # Every hop is itself a trusted proxy (or none present) — never
            # trust attacker-suppliable XFF data; the direct peer is the
            # un-spoofable answer. Falls through to `return peer_ip`.
    return peer_ip


def _species_to_json(species) -> dict:
    """Serialize a Species object to JSON-safe dict."""
    attrs = {}
    for attr_name in ATTRIBUTE_NAMES:
        r = species.attributes.get(attr_name)
        if r:
            attrs[attr_name] = {
                "min": {"dice": r.min_pool.dice, "pips": r.min_pool.pips},
                "max": {"dice": r.max_pool.dice, "pips": r.max_pool.pips},
            }
    abilities = []
    for ab in species.special_abilities:
        abilities.append({"name": ab.name, "description": ab.description})

    return {
        "name": species.name,
        "description": species.description,
        "homeworld": species.homeworld,
        "attribute_dice": {
            "dice": species.attribute_dice.dice,
            "pips": species.attribute_dice.pips,
        },
        "skill_dice": {
            "dice": species.skill_dice.dice,
            "pips": species.skill_dice.pips,
        },
        "move": species.move,
        "attributes": attrs,
        "special_abilities": abilities,
        "story_factors": species.story_factors,
    }


# ── API class ───────────────────────────────────────────────────────────

class ChargenAPI:
    """REST API handler for web character creation."""

    def __init__(
        self,
        species_reg: "SpeciesRegistry",
        skill_reg: "SkillRegistry",
        db: "Database",
    ):
        self.species_reg = species_reg
        self.skill_reg = skill_reg
        self.db = db
        self._skill_descs: dict = {}
        self._template_descs: dict = {}
        self._load_skill_descriptions()

    def _load_skill_descriptions(self):
        """Load extended skill descriptions from YAML."""
        data_dir = os.path.join(
            os.path.dirname(os.path.dirname(__file__)), "data"
        )
        desc_path = os.path.join(data_dir, "skill_descriptions.yaml")
        if os.path.exists(desc_path):
            try:
                with open(desc_path, "r", encoding="utf-8") as f:
                    data = yaml.safe_load(f)
                self._skill_descs = data.get("skills", {})
                self._template_descs = data.get("templates", {})
                self._attr_descs = data.get("attributes", {})
                log.info("Loaded skill descriptions for chargen API")
            except Exception as e:
                log.warning("Failed to load skill_descriptions.yaml: %s", e)

    def register_routes(self, app: web.Application):
        """Register all API routes on the aiohttp app."""
        app.router.add_get("/api/chargen/species", self.handle_species_list)
        app.router.add_get(
            "/api/chargen/species/{name}", self.handle_species_detail
        )
        app.router.add_get("/api/chargen/skills", self.handle_skills)
        app.router.add_get("/api/chargen/templates", self.handle_templates)
        app.router.add_post("/api/chargen/validate", self.handle_validate)
        app.router.add_post("/api/chargen/submit", self.handle_submit)
        app.router.add_post(
            "/api/chargen/create-character", self.handle_create_character
        )
        app.router.add_get(
            "/api/chargen/check-name/{name}", self.handle_check_name
        )
        # ── Drop 2b (May 19 2026 evening): chain selection endpoint ──
        # GET /api/chargen/chains returns the tutorial chain list for
        # the active era plus the is_first_character flag, computed
        # server-side from the account's character count. The SPA
        # consumes this to render chain cards on the new tutorial-chain
        # step. Token-authed (same token issued in chargen_start).
        app.router.add_get(
            "/api/chargen/chains", self.handle_chains
        )
        log.info("Chargen API routes registered")

    # ── GET /api/chargen/species ────────────────────────────────────────

    async def handle_species_list(self, request: web.Request) -> web.Response:
        species_list = []
        for sp in self.species_reg.list_all():
            species_list.append(_species_to_json(sp))
        return web.json_response({"species": species_list})

    # ── GET /api/chargen/species/{name} ─────────────────────────────────

    async def handle_species_detail(
        self, request: web.Request
    ) -> web.Response:
        name = request.match_info["name"]
        sp = self.species_reg.get(name)
        if not sp:
            return web.json_response(
                {"error": f"Unknown species: '{name}'"}, status=404
            )
        return web.json_response(_species_to_json(sp))

    # ── GET /api/chargen/skills ─────────────────────────────────────────

    async def handle_skills(self, request: web.Request) -> web.Response:
        result = {}
        for attr in ATTRIBUTE_NAMES:
            attr_desc = self._attr_descs.get(attr, {})
            skills_data = []
            for sd in self.skill_reg.skills_for_attribute(attr):
                # Merge with extended descriptions
                # YAML keys use underscores, skill registry uses spaces
                desc_key = sd.key.replace(" ", "_").replace("/", "_")
                ext = self._skill_descs.get(attr, {}).get(desc_key, {})
                if not ext:
                    ext = self._skill_descs.get(attr, {}).get(sd.key, {})
                skills_data.append({
                    "name": sd.name,
                    "key": sd.key,
                    "specializations": sd.specializations,
                    "description": ext.get("description", ""),
                    "game_use": ext.get("game_use", ""),
                    "tip": ext.get("tip", ""),
                    "tags": ext.get("tags", []),
                    "priority": ext.get("priority", "normal"),
                })
            result[attr] = {
                "description": attr_desc.get("short", ""),
                "gameplay_note": attr_desc.get("gameplay_note", ""),
                "skills": skills_data,
            }
        return web.json_response({"attributes": result})

    # ── GET /api/chargen/templates ──────────────────────────────────────

    async def handle_templates(self, request: web.Request) -> web.Response:
        templates = []
        for key, tmpl in TEMPLATES.items():
            ext = self._template_descs.get(key, {})
            templates.append({
                "key": key,
                "label": tmpl.get("label", key.title()),
                "species": tmpl.get("species", "Human"),
                "attributes": tmpl["attributes"],
                "skills": tmpl["skills"],
                "description": ext.get("description", ""),
                "tagline": ext.get("tagline", ""),
                "gameplay": ext.get("gameplay", ""),
                "key_skills": ext.get("key_skills", []),
            })
        return web.json_response({"templates": templates})

    # ── POST /api/chargen/validate ──────────────────────────────────────

    async def handle_validate(self, request: web.Request) -> web.Response:
        try:
            data = await request.json()
        except (json.JSONDecodeError, Exception):
            return web.json_response(
                {"valid": False, "errors": ["Invalid JSON body"]}, status=400
            )

        errors = validate_chargen_submission(
            data, self.species_reg, self.skill_reg
        )
        return web.json_response({
            "valid": len(errors) == 0,
            "errors": errors,
        })

    # ── GET /api/chargen/check-name/{name} ──────────────────────────────

    async def handle_check_name(self, request: web.Request) -> web.Response:
        name = request.match_info["name"]
        existing = await self.db.get_character_by_name(name)
        return web.json_response({
            "available": existing is None,
            "name": name,
        })

    # ── POST /api/chargen/submit ────────────────────────────────────────

    async def handle_submit(self, request: web.Request) -> web.Response:
        # Rate limit
        ip = _get_client_ip(request)
        if not _check_rate_limit(ip):
            return web.json_response(
                {
                    "success": False,
                    "errors": {
                        "rate_limit": [
                            "Too many requests. Please wait a minute."
                        ]
                    },
                },
                status=429,
            )

        try:
            data = await request.json()
        except (json.JSONDecodeError, Exception):
            return web.json_response(
                {
                    "success": False,
                    "errors": {"validation": ["Invalid JSON body"]},
                },
                status=400,
            )

        # Body must be a JSON object — a non-dict (array/string/number)
        # would crash the data.get(...) calls below with an unhandled
        # AttributeError -> 500. Reject as malformed.
        if not isinstance(data, dict):
            return web.json_response(
                {
                    "success": False,
                    "errors": {"validation": ["Request body must be a JSON object."]},
                },
                status=400,
            )

        # Extract fields
        username = data.get("username", "")
        password = data.get("password", "")
        char_data = data.get("character", {})

        all_errors: dict[str, list[str]] = {}

        # 1. Validate account fields
        acct_errors = validate_account_fields(username, password)
        if acct_errors:
            all_errors["account"] = acct_errors

        # 2. Validate character build
        char_errors = validate_chargen_submission(
            char_data, self.species_reg, self.skill_reg
        )
        if char_errors:
            all_errors["validation"] = char_errors

        # Return early if validation fails
        if all_errors:
            return web.json_response(
                {"success": False, "errors": all_errors}, status=400
            )

        # 3. Create account atomically
        account_id = await self.db.create_account(username, password)
        if account_id is None:
            return web.json_response(
                {
                    "success": False,
                    "errors": {"account": ["Username already taken."]},
                },
                status=409,
            )

        # 4. Build Character object and save
        try:
            char_obj = Character()
            char_obj.name = char_data["name"].strip()
            char_obj.species_name = char_data["species"]

            # Set species move
            species = self.species_reg.get(char_data["species"])
            if species:
                char_obj.move = species.move

            # Set attributes
            for attr in ATTRIBUTE_NAMES:
                val = char_data["attributes"].get(attr)
                if val:
                    char_obj.set_attribute(attr, DicePool.parse(str(val)))

            # Set skills (bonus above attribute)
            for skill_name, skill_val in char_data.get("skills", {}).items():
                bonus = DicePool.parse(str(skill_val))
                if bonus.total_pips() > 0:
                    char_obj.skills[skill_name.lower()] = bonus

            # Force sensitivity
            force_sensitive = char_data.get("force_sensitive", False)
            char_obj.force_sensitive = force_sensitive
            if force_sensitive:
                char_obj.force_points = 2
                # Set Force attributes to 0D (unlocked but untrained)
                char_obj.set_attribute("control", DicePool(0, 0))
                char_obj.set_attribute("sense", DicePool(0, 0))
                char_obj.set_attribute("alter", DicePool(0, 0))

            # Background → description (coerce + cap to bound the DB write;
            # an unauthenticated POST could otherwise store a 256 KiB blob).
            background = char_data.get("background", "") or ""
            if not isinstance(background, str):
                background = str(background)
            char_obj.description = background[:MAX_BACKGROUND_LEN]

            # Chargen rationale notes (optional, separate from
            # description; defaults to '' for older clients).
            cgn = char_data.get("chargen_notes", "") or ""
            if isinstance(cgn, str) and cgn:
                char_obj.chargen_notes = cgn[:2000]  # cap matches +chargen_notes

            # Place in tutorial Landing Pad if it exists
            try:
                landing_pad_rows = await self.db.fetchall(
                    "SELECT id FROM rooms WHERE name = 'Landing Pad' "
                    "AND properties LIKE '%tutorial_zone%' ORDER BY id LIMIT 1"
                )
                if landing_pad_rows:
                    char_obj.room_id = landing_pad_rows[0]["id"]
            except Exception:
                log.warning("Could not find tutorial Landing Pad", exc_info=True)

            db_fields = char_obj.to_db_dict()
            char_id = await self.db.create_character(
                account_id=account_id, fields=db_fields
            )

            # Generate auto-login token
            token = create_login_token(account_id)

            log.info(
                "Web chargen: created account '%s' (id=%d) + character '%s' (id=%d)",
                username, account_id, char_obj.name, char_id,
            )

            return web.json_response({
                "success": True,
                "character_id": char_id,
                "token": token,
                "redirect": f"/client.html?token={token}",
            })

        except Exception as e:
            err_str = str(e)
            if "UNIQUE constraint" in err_str and "name" in err_str.lower():
                return web.json_response(
                    {
                        "success": False,
                        "errors": {
                            "character": [
                                f"The name '{char_data.get('name', '')}' "
                                f"is already taken."
                            ]
                        },
                    },
                    status=409,
                )
            log.error("Chargen submit failed: %s", e, exc_info=True)
            return web.json_response(
                {
                    "success": False,
                    "errors": {
                        "server": [
                            "An unexpected error occurred. Please try again."
                        ]
                    },
                },
                status=500,
            )

    # ── GET /api/chargen/chains ─────────────────────────────────────────
    #
    # Drop 2b (May 19 2026 evening). Returns the active era's tutorial
    # chain list plus the is_first_character flag computed from the
    # account's character count. Token-authed; same token issued by
    # game_server._run_web_chargen in the chargen_start payload.
    #
    # Response shape:
    #     {
    #         "is_first_character": bool,
    #         "chains": [
    #             {
    #                 "chain_id": str,
    #                 "chain_name": str,
    #                 "description": str,
    #                 "archetype_label": str,
    #                 "faction_alignment": str | None,
    #                 "duration_minutes": int,
    #                 "locked": bool,
    #                 "locked_reason": str,  # "" if not locked
    #                 "starting_room": str,  # slug; "" for locked stubs
    #             },
    #             ...
    #         ]
    #     }
    #
    # Locked status is computed via
    # engine.tutorial_chains.is_chain_locked_for_character with the
    # chargen sentinel `faction_intent="__chargen_any__"` so faction-
    # gated chains all show at chargen — picking a chain IS the
    # faction commitment. Jedi-Path chains stay locked at chargen
    # (require village_chosen_path which doesn't exist yet for a
    # fresh character).
    #
    # If the era has no chains.yaml (e.g. GCW), returns an empty
    # chains list; the SPA should treat that as "skip this step."
    async def handle_chains(self, request: web.Request) -> web.Response:
        # Token from query param so the SPA can use a plain GET.
        token = request.query.get("token", "")
        account_id = verify_login_token(token)
        if account_id is None:
            return web.json_response(
                {
                    "success": False,
                    "errors": {"auth": ["Invalid or expired session."]},
                },
                status=401,
            )

        # Compute is_first_character. Server is the authority — the
        # SPA's UI hint is convenience.
        existing_chars = await self.db.get_characters(account_id)
        is_first_character = len(existing_chars) == 0

        # Load the chain corpus for the active era.
        from engine.tutorial_chains import (
            load_tutorial_chains, is_chain_locked_for_character,
        )
        corpus = load_tutorial_chains()
        if corpus is None or not corpus.ok or not corpus.chains:
            # Era has no chain-based tutorials (e.g. GCW), or the
            # corpus failed to load. Return empty list; SPA skips
            # the chain step.
            return web.json_response({
                "is_first_character": is_first_character,
                "chains": [],
            })

        # Build per-chain locked status using the chargen sentinel.
        # See engine/creation_wizard._chargen_attrs_for_chain_check
        # for the original of this attrs dict.
        chargen_attrs = {
            "chargen_complete": True,
            "faction_intent": "__chargen_any__",
            "force_sensitive": False,  # neutral; force chains stay locked
            "jedi_path_unlocked": False,
        }
        chains_json = []
        for chain in corpus.chains:
            is_locked, reason = is_chain_locked_for_character(
                chain, chargen_attrs,
            )
            chains_json.append({
                "chain_id": chain.chain_id,
                "chain_name": chain.chain_name,
                "description": chain.description,
                "archetype_label": chain.archetype_label,
                "faction_alignment": chain.faction_alignment,
                "duration_minutes": chain.duration_minutes,
                "locked": bool(is_locked),
                "locked_reason": reason if is_locked else "",
                "starting_room": chain.starting_room or "",
            })

        return web.json_response({
            "is_first_character": is_first_character,
            "chains": chains_json,
        })

    # ── POST /api/chargen/create-character ──────────────────────────────

    async def handle_create_character(
        self, request: web.Request
    ) -> web.Response:
        """
        Create a character for an existing account (embedded chargen flow).

        Authenticated via a token in the request body (issued by the
        server when it sends chargen_start to a WebSocket session).
        """
        # Rate limit
        ip = _get_client_ip(request)
        if not _check_rate_limit(ip):
            return web.json_response(
                {
                    "success": False,
                    "errors": {
                        "rate_limit": [
                            "Too many requests. Please wait a minute."
                        ]
                    },
                },
                status=429,
            )

        try:
            data = await request.json()
        except (json.JSONDecodeError, Exception):
            return web.json_response(
                {
                    "success": False,
                    "errors": {"validation": ["Invalid JSON body"]},
                },
                status=400,
            )

        # Body must be a JSON object — a non-dict body would crash the
        # data.get(...) calls below with an unhandled AttributeError -> 500.
        if not isinstance(data, dict):
            return web.json_response(
                {
                    "success": False,
                    "errors": {"validation": ["Request body must be a JSON object."]},
                },
                status=400,
            )

        # Verify token
        token = data.get("token", "")
        account_id = verify_login_token(token)
        if account_id is None:
            return web.json_response(
                {
                    "success": False,
                    "errors": {"auth": ["Invalid or expired session."]},
                },
                status=401,
            )

        # Verify account exists
        account = await self.db.get_account(account_id)
        if not account:
            return web.json_response(
                {
                    "success": False,
                    "errors": {"auth": ["Account not found."]},
                },
                status=401,
            )

        # Check character limit (default 3)
        existing_chars = await self.db.get_characters(account_id)
        max_chars = 3  # matches config.max_characters_per_account
        if len(existing_chars) >= max_chars:
            return web.json_response(
                {
                    "success": False,
                    "errors": {"character": [
                        f"You already have {len(existing_chars)} character(s). "
                        f"Maximum is {max_chars} per account."
                    ]},
                },
                status=400,
            )

        # ── Drop 2b (May 19 2026 evening): chain/skip pre-validation ──
        #
        # The body may now include `chain_id` (str — selected tutorial
        # chain) and `skip_tutorial` (bool — alt-character bypass).
        # Server is the authority here; the SPA's UI hint is
        # convenience. Rules:
        #   - skip_tutorial=True is REJECTED when this is the
        #     account's first character (len(existing_chars)==0).
        #   - chain_id is validated against the active era's
        #     chains.yaml. Locked chains (Jedi-Path) are rejected.
        #   - chain_id and skip_tutorial are mutually exclusive; if
        #     both are present, skip_tutorial wins ONLY when
        #     skip_tutorial is True (otherwise chain_id is used).
        #   - Eras without a chains corpus (GCW) silently ignore both
        #     fields — no chain, no skip kit, falls back to the
        #     legacy Landing Pad placement.
        is_first_character = (len(existing_chars) == 0)
        chain_id = data.get("chain_id")
        # chain_id feeds corpus.by_id().get(chain_id); an unhashable type
        # (list/dict) would raise TypeError there -> unhandled 500. Reject
        # any non-string chain_id as malformed before it reaches the lookup.
        if chain_id is not None and not isinstance(chain_id, str):
            return web.json_response(
                {
                    "success": False,
                    "errors": {"chain": ["chain_id must be a string."]},
                },
                status=400,
            )
        skip_tutorial = bool(data.get("skip_tutorial", False))

        if skip_tutorial and is_first_character:
            return web.json_response(
                {
                    "success": False,
                    "errors": {"chain": [
                        "Skip is not available for your first character. "
                        "Pick a tutorial chain — every operative needs a "
                        "starting profession. You can skip on a later "
                        "character."
                    ]},
                },
                status=400,
            )

        # Resolve the chain corpus once for the active era.
        from engine.tutorial_chains import (
            load_tutorial_chains, is_chain_locked_for_character,
        )
        corpus = load_tutorial_chains()

        # If chain_id is given, validate it against the corpus.
        selected_chain = None
        if chain_id and not skip_tutorial:
            if corpus is None or not corpus.ok or not corpus.chains:
                # No corpus but a chain_id was sent — treat as a
                # client-side bug. Reject loudly so the SPA can
                # surface the inconsistency.
                return web.json_response(
                    {
                        "success": False,
                        "errors": {"chain": [
                            "This era does not support tutorial "
                            "chain selection."
                        ]},
                    },
                    status=400,
                )
            selected_chain = corpus.by_id().get(chain_id)
            if selected_chain is None:
                return web.json_response(
                    {
                        "success": False,
                        "errors": {"chain": [
                            f"Unknown chain '{chain_id}'."
                        ]},
                    },
                    status=400,
                )
            # Re-check lock status with the chargen sentinel — this
            # mirrors creation_wizard._select_chain_by_id's defense
            # against direct-id input bypassing the menu filter.
            _cb = data.get("character")
            _char_body = _cb if isinstance(_cb, dict) else {}
            chargen_attrs = {
                "chargen_complete": True,
                "faction_intent": "__chargen_any__",
                "force_sensitive": bool(
                    _char_body.get("force_sensitive", False)
                ),
                "jedi_path_unlocked": False,
            }
            is_locked, reason = is_chain_locked_for_character(
                selected_chain, chargen_attrs,
            )
            if is_locked:
                return web.json_response(
                    {
                        "success": False,
                        "errors": {"chain": [reason or (
                            f"Chain '{chain_id}' is not available."
                        )]},
                    },
                    status=400,
                )

        char_data = data.get("character", {})

        # Validate character build
        char_errors = validate_chargen_submission(
            char_data, self.species_reg, self.skill_reg
        )
        if char_errors:
            return web.json_response(
                {"success": False, "errors": {"validation": char_errors}},
                status=400,
            )

        # Build Character object and save
        try:
            char_obj = Character()
            char_obj.name = char_data["name"].strip()
            char_obj.species_name = char_data["species"]

            species = self.species_reg.get(char_data["species"])
            if species:
                char_obj.move = species.move

            for attr in ATTRIBUTE_NAMES:
                val = char_data["attributes"].get(attr)
                if val:
                    char_obj.set_attribute(attr, DicePool.parse(str(val)))

            for skill_name, skill_val in char_data.get("skills", {}).items():
                bonus = DicePool.parse(str(skill_val))
                if bonus.total_pips() > 0:
                    char_obj.skills[skill_name.lower()] = bonus

            force_sensitive = char_data.get("force_sensitive", False)
            char_obj.force_sensitive = force_sensitive
            if force_sensitive:
                char_obj.force_points = 2
                char_obj.set_attribute("control", DicePool(0, 0))
                char_obj.set_attribute("sense", DicePool(0, 0))
                char_obj.set_attribute("alter", DicePool(0, 0))

            # Background → description (coerce + cap; mirrors handle_submit).
            background = char_data.get("background", "") or ""
            if not isinstance(background, str):
                background = str(background)
            char_obj.description = background[:MAX_BACKGROUND_LEN]

            # Chargen rationale notes (optional, mirrors handle_submit).
            cgn = char_data.get("chargen_notes", "") or ""
            if isinstance(cgn, str) and cgn:
                char_obj.chargen_notes = cgn[:2000]

            # ── Drop 2b (May 19 2026 evening): chain-aware placement ──
            # If a tutorial chain was selected and has a starting_room
            # slug, resolve the slug to a room_id and place the
            # character there. Mirrors
            # server/game_server.py::_run_character_creation
            # lines ~1078-1124 (Telnet path), so the two paths route
            # identically.
            placed_via_chain = False
            if selected_chain is not None and selected_chain.starting_room:
                slug = selected_chain.starting_room
                try:
                    chain_room_rows = await self.db.fetchall(
                        "SELECT id FROM rooms WHERE properties LIKE ? "
                        "ORDER BY id LIMIT 1",
                        (f'%"slug": "{slug}"%',),
                    )
                    if chain_room_rows:
                        char_obj.room_id = chain_room_rows[0]["id"]
                        placed_via_chain = True
                        log.info(
                            "[Drop 2b] Web chargen routing '%s' to "
                            "chain starting room %s (id=%d).",
                            char_obj.name, slug, char_obj.room_id,
                        )
                    else:
                        log.warning(
                            "[Drop 2b] Chain starting_room slug %r "
                            "did not resolve; falling back to "
                            "Landing Pad placement.", slug,
                        )
                except Exception:
                    log.warning(
                        "[Drop 2b] Chain starting_room lookup failed; "
                        "falling back to Landing Pad placement.",
                        exc_info=True,
                    )

            # Fallback: legacy Landing Pad placement (no chain
            # selected, or chain slug failed to resolve).
            if not placed_via_chain:
                try:
                    landing_pad_rows = await self.db.fetchall(
                        "SELECT id FROM rooms WHERE name = 'Landing Pad' "
                        "AND properties LIKE '%tutorial_zone%' "
                        "ORDER BY id LIMIT 1"
                    )
                    if landing_pad_rows:
                        char_obj.room_id = landing_pad_rows[0]["id"]
                except Exception:
                    log.warning(
                        "Could not find tutorial Landing Pad",
                        exc_info=True
                    )

            db_fields = char_obj.to_db_dict()

            # ── Drop 2b (May 19 2026 evening): merge tutorial_chain
            # block + faction_intent into attributes JSON. Mirrors
            # server/game_server.py::_run_character_creation
            # lines ~1129-1165 (Telnet path).
            if selected_chain is not None:
                import time as _t
                try:
                    attrs_dict = json.loads(
                        db_fields.get("attributes") or "{}"
                    )
                except json.JSONDecodeError:
                    attrs_dict = {}
                attrs_dict["tutorial_chain"] = {
                    "chain_id": selected_chain.chain_id,
                    "step": 1,
                    "started_at": _t.time(),
                    "completed_steps": [],
                    "completion_state": "active",
                }
                if selected_chain.faction_alignment:
                    attrs_dict["faction_intent"] = (
                        selected_chain.faction_alignment
                    )
                db_fields["attributes"] = json.dumps(attrs_dict)

            char_id = await self.db.create_character(
                account_id=account_id, fields=db_fields
            )

            # ── Drop 2b: skip starter kit application ──
            # If the alt skipped the tutorial, apply the era's skip
            # starter kit: credits + inventory items. Resources too,
            # though CW's kit ships with resources=[].
            # Reads data/worlds/<era>/skip_starter_kit.yaml via the
            # era manifest's content_refs.skip_starter_kit.
            skip_kit_message = ""
            if skip_tutorial:
                from engine.tutorial_chains import load_skip_starter_kit
                kit = load_skip_starter_kit()
                if kit is not None:
                    try:
                        kit_credits = int(kit.get("credits", 0))
                        if kit_credits > 0:
                            # Chargen initialization, NOT a running-economy
                            # faucet: this sets a brand-new character's
                            # starting credits (absolute), consistent with the
                            # unlogged create_character INSERT on the regular
                            # tutorial path. Intentionally not routed through
                            # the adjust_credits delta-chokepoint; allowlisted
                            # in tests/test_ledger_chokepoint_complete.py.
                            await self.db.save_character(
                                char_id, credits=kit_credits,
                            )
                        for item in (kit.get("items") or []):
                            if isinstance(item, dict):
                                await self.db.add_to_inventory(
                                    char_id, dict(item),
                                )
                        skip_kit_message = kit.get("message", "") or ""
                        log.info(
                            "[Drop 2b] Applied skip starter kit to "
                            "'%s' (id=%d): %d credits, %d items.",
                            char_obj.name, char_id, kit_credits,
                            len(kit.get("items") or []),
                        )
                    except Exception:
                        log.warning(
                            "[Drop 2b] Skip starter kit application "
                            "failed for char_id=%d; character was "
                            "created but kit may be incomplete.",
                            char_id, exc_info=True,
                        )
                else:
                    log.info(
                        "[Drop 2b] Skip requested but no kit "
                        "configured for the active era; alt starts "
                        "with default chargen credits/inventory."
                    )

            log.info(
                "Web chargen (embedded): character '%s' (id=%d) "
                "for account %d",
                char_obj.name, char_id, account_id,
            )

            response_payload = {
                "success": True,
                "character_id": char_id,
            }
            if skip_kit_message:
                response_payload["skip_kit_message"] = skip_kit_message
            return web.json_response(response_payload)

        except Exception as e:
            err_str = str(e)
            if "UNIQUE constraint" in err_str and "name" in err_str.lower():
                return web.json_response(
                    {
                        "success": False,
                        "errors": {
                            "character": [
                                f"The name '{char_data.get('name', '')}' "
                                f"is already taken."
                            ]
                        },
                    },
                    status=409,
                )
            log.error(
                "Chargen create-character failed: %s", e, exc_info=True
            )
            return web.json_response(
                {
                    "success": False,
                    "errors": {
                        "server": [
                            "An unexpected error occurred. Please try again."
                        ]
                    },
                },
                status=500,
            )
