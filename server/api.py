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

_TOKEN_SECRET = os.urandom(32)


def create_login_token(account_id: int, ttl: int = 300) -> str:
    """Create a signed, expiring login token for auto-login after chargen."""
    payload = json.dumps({"aid": account_id, "exp": int(time.time()) + ttl})
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = _hmac.new(
        _TOKEN_SECRET, payload_b64.encode(), hashlib.sha256
    ).hexdigest()[:16]
    return f"{payload_b64}.{sig}"


def verify_login_token(token: str) -> Optional[int]:
    """Verify a login token. Returns account_id or None."""
    try:
        payload_b64, sig = token.rsplit(".", 1)
        expected = _hmac.new(
            _TOKEN_SECRET, payload_b64.encode(), hashlib.sha256
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

def _get_client_ip(request: web.Request) -> str:
    """Get client IP, respecting X-Forwarded-For if present."""
    forwarded = request.headers.get("X-Forwarded-For")
    if forwarded:
        return forwarded.split(",")[0].strip()
    peername = request.transport.get_extra_info("peername")
    return peername[0] if peername else "unknown"


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

            # Background → description
            char_obj.description = char_data.get("background", "")

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

            char_obj.description = char_data.get("background", "")

            # Chargen rationale notes (optional, mirrors handle_submit).
            cgn = char_data.get("chargen_notes", "") or ""
            if isinstance(cgn, str) and cgn:
                char_obj.chargen_notes = cgn[:2000]

            # Tutorial Landing Pad placement
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
                    "Could not find tutorial Landing Pad", exc_info=True
                )

            db_fields = char_obj.to_db_dict()
            char_id = await self.db.create_character(
                account_id=account_id, fields=db_fields
            )

            log.info(
                "Web chargen (embedded): character '%s' (id=%d) "
                "for account %d",
                char_obj.name, char_id, account_id,
            )

            return web.json_response({
                "success": True,
                "character_id": char_id,
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
