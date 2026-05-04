# -*- coding: utf-8 -*-
"""
tests/smoke/scenarios/portal.py — Web portal HTTP smoke (HX1–HX8).

Drop 1 Block E. The portal serves the marketing surface and the
authenticated-player dashboard. Pre-Drop-1, it had zero end-to-end
smoke; the access-level bug that made the Reference page show 74 of
303 entries to non-admins survived for that reason.

Scope of these scenarios:
  HX1 — Reference index returns the player corpus (post-fix ~250+
        entries; pre-fix this would have returned ~74).
  HX2 — Reference search finds FDtS quest commands.
  HX3 — Reference search finds crafting commands.
  HX4 — Reference entry detail renders for a known player command.
  HX5 — Reference entry 404 for unknown slugs is clean (no crash).
  HX6 — /api/portal/who returns 200 with array of online characters.
  HX7 — Portal login → token → /api/portal/me round-trip works
        (regression guard for the .all() vs .all bug fixed in this drop).
  HX8 — Admin-only entries (e.g. @dig) hidden from non-admin Reference.

These are HTTP-layer scenarios — they spin up an aiohttp test client
bound to the live PortalAPI, registered against the harness DB. The
harness's Telnet/WebSocket session machinery is not exercised by
these scenarios; they cover the parallel HTTP REST surface.

Why the in-test fixture instead of a global harness extension: the
PortalAPI is wired at GameServer boot in production but bypassed in
the smoke harness's _boot_no_listeners (which deliberately skips
self.web_client.start). Building it on demand inside the scenario
keeps the harness contract minimal and the fixture local.
"""
from __future__ import annotations

import json
from contextlib import asynccontextmanager


# ──────────────────────────────────────────────────────────────────────────
# Helpers
# ──────────────────────────────────────────────────────────────────────────

@asynccontextmanager
async def _portal_client(h):
    """Spin up an aiohttp TestClient with PortalAPI routes registered.

    Yields an aiohttp TestClient bound to a fresh aiohttp.web.Application
    that has been populated with the portal routes pointing at the
    harness DB + session_mgr + game. Cleans up on exit.

    Imports are local so that test modules that don't run portal
    scenarios don't pay the aiohttp import cost.
    """
    from aiohttp import web
    from aiohttp.test_utils import TestServer, TestClient
    from server.web_portal import PortalAPI

    app = web.Application()
    api = PortalAPI(
        db=h.db,
        session_mgr=h._server.session_mgr,
        game=h._server,
    )
    api.register_routes(app)

    server = TestServer(app)
    await server.start_server()
    client = TestClient(server)
    await client.start_server()
    try:
        yield client
    finally:
        await client.close()
        await server.close()


async def _login_as_admin(h, client) -> str:
    """Return a Bearer token for the harness's seeded admin account.

    The smoke harness boots with a `testuser`/`testpass` admin row
    pre-seeded by engine/test_character_loader.py (account id=1,
    is_admin=1). Portal login over the REST endpoint exchanges
    those credentials for a 24h-TTL signed token.
    """
    resp = await client.post(
        "/api/portal/login",
        json={"username": "testuser", "password": "testpass"},
    )
    assert resp.status == 200, (
        f"admin login failed: status={resp.status} "
        f"body={await resp.text()}"
    )
    body = await resp.json()
    token = body.get("token")
    assert token, f"login response missing token: {body!r}"
    return token


# ──────────────────────────────────────────────────────────────────────────
# HX1 — Reference index shows the player corpus (post-fix bar)
# ──────────────────────────────────────────────────────────────────────────

async def hx1_reference_index_shows_player_entries(h):
    """HX1 — GET /api/portal/reference for an unauth caller returns
    the player-visible corpus, not just the ANYONE-tier entries.

    This is the regression guard for the Drop-1 access-level fix
    (server/web_portal.py::_caller_max_access_level). Pre-fix, the
    method returned ANYONE (0) for unauth, and BaseCommand's default
    PLAYER (1) on auto-registered help entries hid the entire player
    corpus from the portal Reference. Post-fix, unauth callers see
    PLAYER-level documentation (the marketing surface) but still
    don't see BUILDER (2) or ADMIN (3) entries.

    The numeric floor here is 200 — comfortably above the pre-fix
    ceiling (~74 with markdown layered in, ~54 without) and well
    below the full corpus (~303). If the count drops below 200 we
    have either lost the fix or lost a chunk of the command corpus.
    """
    async with _portal_client(h) as client:
        resp = await client.get("/api/portal/reference")
        assert resp.status == 200, (
            f"reference index returned non-200: {resp.status}"
        )
        data = await resp.json()
        entries = data.get("entries", [])
        n = len(entries)
        assert n >= 200, (
            f"Reference index returned only {n} entries to unauth "
            f"caller — Drop-1 access-level fix may have regressed. "
            f"Expected ≥200 (player corpus); got {n}."
        )
        # Spot-check a handful of canonical player commands. Their
        # presence proves the player tier really is included, not just
        # that the count happens to be high for some other reason.
        keys = {e["key"] for e in entries}
        for required in ("look", "attack", "+sheet", "craft", "survey"):
            assert required in keys, (
                f"Reference index missing canonical player command "
                f"{required!r}. Sample of present keys: "
                f"{sorted(keys)[:15]!r}"
            )


# ──────────────────────────────────────────────────────────────────────────
# HX2 — Reference search finds FDtS quest commands
# ──────────────────────────────────────────────────────────────────────────

async def hx2_reference_search_finds_quest(h):
    """HX2 — Search ?q=quest returns at least the FDtS spacerquest
    command and the narrative +quest umbrella.

    The reference search backs the portal's "search the rules"
    feature. If it returns zero results for a baseline term like
    "quest", the search index is broken or the FDtS commands aren't
    registering at all.
    """
    async with _portal_client(h) as client:
        resp = await client.get("/api/portal/reference/search?q=quest")
        assert resp.status == 200, f"search 200 expected, got {resp.status}"
        data = await resp.json()
        results = data.get("results", [])
        assert results, "search ?q=quest returned no results"
        keys = {r["key"] for r in results}
        # At least one of the quest-bearing commands must appear. We
        # accept a generous set because the canonical key has changed
        # historically (FDtS used to be `+quest`; post-S57b it is
        # `spacerquest` with `quest`/`+spacerquest` aliases).
        quest_keys = {"+quest", "spacerquest", "quest", "+quests"}
        hit = quest_keys & keys
        assert hit, (
            f"search ?q=quest didn't return any quest command. "
            f"Got keys: {sorted(keys)!r}"
        )


# ──────────────────────────────────────────────────────────────────────────
# HX3 — Reference search finds crafting commands
# ──────────────────────────────────────────────────────────────────────────

async def hx3_reference_search_finds_craft(h):
    """HX3 — Search ?q=craft returns crafting-system entries.

    Complementary to HX2: a different domain query against the same
    search backend. If only HX2 passed and HX3 failed, that would
    suggest a quest-specific overlap rather than a working index.
    """
    async with _portal_client(h) as client:
        resp = await client.get("/api/portal/reference/search?q=craft")
        assert resp.status == 200, f"search 200 expected, got {resp.status}"
        data = await resp.json()
        results = data.get("results", [])
        assert results, "search ?q=craft returned no results"
        keys = {r["key"] for r in results}
        # We expect at least one of the crafting verbs.
        craft_keys = {"craft", "+craft", "schematics", "experiment"}
        hit = craft_keys & keys
        assert hit, (
            f"search ?q=craft didn't return any crafting command. "
            f"Got keys: {sorted(keys)!r}"
        )


# ──────────────────────────────────────────────────────────────────────────
# HX4 — Reference entry detail renders for a known command
# ──────────────────────────────────────────────────────────────────────────

async def hx4_reference_entry_renders(h):
    """HX4 — GET /api/portal/reference/look returns full entry detail.

    `look` is the most foundational player command — if its detail
    page can't render, every entry detail is broken. We assert the
    full-view fields are present (body, aliases, see_also, examples)
    and the body is non-empty.
    """
    async with _portal_client(h) as client:
        resp = await client.get("/api/portal/reference/look")
        assert resp.status == 200, (
            f"GET /api/portal/reference/look returned {resp.status}"
        )
        data = await resp.json()
        # Required fields per PortalAPI._full_view shape.
        for field in ("key", "title", "category", "body",
                      "aliases", "see_also"):
            assert field in data, (
                f"reference/look response missing {field!r}: "
                f"keys present = {list(data.keys())!r}"
            )
        assert data.get("body", "").strip(), (
            f"reference/look body is empty. Full payload: {data!r}"
        )


# ──────────────────────────────────────────────────────────────────────────
# HX5 — Reference entry 404 for unknown slugs
# ──────────────────────────────────────────────────────────────────────────

async def hx5_reference_entry_404(h):
    """HX5 — GET /api/portal/reference/<nonexistent> returns 404, not 500.

    Catches the bug class where a missing entry surfaces as an
    uncaught KeyError (500) instead of a graceful 404. Real player
    bookmarks and old links break otherwise — and our own UI's
    "load entry detail" code gets a confusing payload.
    """
    async with _portal_client(h) as client:
        resp = await client.get(
            "/api/portal/reference/this-slug-does-not-exist"
        )
        assert resp.status == 404, (
            f"Unknown slug should return 404, got {resp.status}. "
            f"Body: {await resp.text()}"
        )


# ──────────────────────────────────────────────────────────────────────────
# HX6 — /api/portal/who returns array of online characters
# ──────────────────────────────────────────────────────────────────────────

async def hx6_who_returns_online_characters(h):
    """HX6 — GET /api/portal/who returns 200 with an array shape.

    The portal's home page renders a "who's online" widget off this
    endpoint. We log a player into the harness first so we have a
    non-empty list to assert on; if the endpoint silently dropped
    in-game sessions we'd see a 200 with an empty array, which
    this scenario catches.
    """
    s = await h.login_as("Hx6Online", room_id=1)
    async with _portal_client(h) as client:
        resp = await client.get("/api/portal/who")
        assert resp.status == 200, (
            f"/api/portal/who returned {resp.status}"
        )
        data = await resp.json()
        # Shape: {"players": [...], ...} per handle_who. The exact
        # surrounding key may evolve; tolerate the response being a
        # plain list for forward compatibility.
        if isinstance(data, list):
            players = data
        else:
            players = (data.get("players") or data.get("online") or
                       data.get("characters") or [])
        assert players, (
            f"/api/portal/who returned no players despite an in-game "
            f"session being active. Full response: {data!r}"
        )
        # The session we logged in should appear.
        names = [
            (p.get("name") or p.get("character") or "").lower()
            for p in players
        ]
        assert "hx6online" in names, (
            f"/api/portal/who didn't include the test session "
            f"'Hx6Online'. Names returned: {names!r}"
        )


# ──────────────────────────────────────────────────────────────────────────
# HX7 — Login → token → /me round-trip
# ──────────────────────────────────────────────────────────────────────────

async def hx7_login_then_me_roundtrip(h):
    """HX7 — POST login, take the token, GET /me — both succeed.

    This scenario was promoted to a regression guard mid-Drop-1: the
    /api/portal/me handler called ``self._session_mgr.all()`` instead
    of using the ``.all`` property, which 500'd every authenticated
    /me request. The bug's existence + the scenario's absence is
    exactly the §4.7 "logged in and crashed → add a scenario" case.

    Asserts:
      - Admin credentials authenticate
      - Token comes back well-formed (non-empty string)
      - GET /me with that token returns 200 (not 500)
      - The response's account_id matches the login's account_id
      - The character list shape is correct (list)

    DROP-5 (May 2026): seeds its own admin account rather than
    relying on the engine/test_character_loader.py seed. The latter
    only fires when there's a test_character.yaml in the active
    era's data dir; GCW has one, CW doesn't (yet). Now that
    --smoke-era defaults to clone_wars, depending on the seeded
    admin breaks under the default. Seeding our own keeps HX7
    era-independent.
    """
    # Seed a portal admin account if one doesn't already exist.
    # `create_account` auto-promotes the FIRST account to admin, so
    # we use that path when the accounts table is empty. Otherwise
    # (e.g. GCW seed already populated id=1 as testuser admin) we
    # piggyback on whatever admin exists. The login below tries
    # both credential pairs in order — the explicit hx7admin pair
    # first (the one we just created), falling back to testuser
    # (the GCW seed) if the create returned None (already taken).
    HX7_USERNAME = "hx7admin"
    HX7_PASSWORD = "hx7adminpass"
    new_id = await h.db.create_account(HX7_USERNAME, HX7_PASSWORD)
    if new_id is None:
        # Username taken (probably from a prior test in the same
        # class-scoped harness); the existing row is fine to reuse.
        pass
    # If we weren't first, also promote ourselves to admin so /me
    # round-trip passes regardless of the registration order. This
    # is a smoke-test convenience — production never grants admin
    # this way.
    await h.db._db.execute(
        "UPDATE accounts SET is_admin = 1 WHERE username = ?",
        (HX7_USERNAME,),
    )
    await h.db._db.commit()

    async with _portal_client(h) as client:
        # Login
        resp = await client.post(
            "/api/portal/login",
            json={"username": HX7_USERNAME, "password": HX7_PASSWORD},
        )
        assert resp.status == 200, (
            f"login expected 200, got {resp.status}: "
            f"{await resp.text()}"
        )
        login_body = await resp.json()
        token = login_body.get("token")
        login_account_id = login_body.get("account_id")
        assert token, f"login response missing token: {login_body!r}"
        assert isinstance(login_account_id, int), (
            f"account_id should be int, got: {login_account_id!r}"
        )

        # /me round-trip
        resp2 = await client.get(
            "/api/portal/me",
            headers={"Authorization": f"Bearer {token}"},
        )
        assert resp2.status == 200, (
            f"/api/portal/me expected 200, got {resp2.status}. "
            f"This is the .all() vs .all bug — see HX7 docstring. "
            f"Body: {await resp2.text()}"
        )
        me_body = await resp2.json()
        assert me_body.get("account_id") == login_account_id, (
            f"/me account_id mismatch: login={login_account_id} "
            f"me={me_body.get('account_id')!r}"
        )
        chars = me_body.get("characters", [])
        assert isinstance(chars, list), (
            f"/me characters should be a list, got {type(chars)}: "
            f"{chars!r}"
        )


# ──────────────────────────────────────────────────────────────────────────
# HX8 — Admin entries hidden from non-admin
# ──────────────────────────────────────────────────────────────────────────

async def hx8_admin_entries_hidden_from_non_admin(h):
    """HX8 — Admin/builder commands (@dig, @director) absent from
    non-admin Reference responses.

    Companion to HX1: HX1 confirms the floor (player corpus is
    visible); HX8 confirms the ceiling (admin/builder corpus is
    NOT). Both must hold for the access-level fix to be correct.
    Without HX8 a regression that returned `ADMIN` to all callers
    would still pass HX1 but would leak admin-only documentation.
    """
    # Two halves: unauth must not see admin, AND a non-admin
    # authenticated user must not see admin either.
    s = await h.login_as("Hx8NonAdmin", room_id=1)

    async with _portal_client(h) as client:
        # 1. Unauth view
        resp = await client.get("/api/portal/reference")
        data = await resp.json()
        entries = data.get("entries", [])
        keys = {e["key"] for e in entries}
        for forbidden in ("@dig", "@destroy"):
            assert forbidden not in keys, (
                f"Unauth Reference index leaked admin command "
                f"{forbidden!r}. The access-level filter is no "
                f"longer hiding BUILDER/ADMIN tier entries."
            )

        # 2. Non-admin authenticated view (should be the same)
        # The harness's per-character account is non-admin (only the
        # first seeded `testuser` got the admin flag). Login over the
        # portal as that non-admin, then verify the same hiding holds.
        resp_login = await client.post(
            "/api/portal/login",
            json={"username": "test_hx8nonadmin",
                  "password": "smoketestpass"},
        )
        assert resp_login.status == 200, (
            f"non-admin portal login failed: status="
            f"{resp_login.status} body={await resp_login.text()}"
        )
        non_admin_token = (await resp_login.json()).get("token")
        resp_auth = await client.get(
            "/api/portal/reference",
            headers={"Authorization": f"Bearer {non_admin_token}"},
        )
        data_auth = await resp_auth.json()
        keys_auth = {e["key"] for e in data_auth.get("entries", [])}
        for forbidden in ("@dig", "@destroy"):
            assert forbidden not in keys_auth, (
                f"Authenticated non-admin Reference leaked admin "
                f"command {forbidden!r}. _caller_max_access_level "
                f"should return PLAYER (1) for non-admin auth, not "
                f"ADMIN (3)."
            )
