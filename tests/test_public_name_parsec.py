# -*- coding: utf-8 -*-
"""Regression guard: the PUBLIC-facing name is **Parsec** (Brian 2026-06-18).

The old working title "Star Wars D6 MUSH" / "SW MUSH" must not appear in the
user-visible branding surfaces. `SW_MUSH` / `sw_mush` remains valid ONLY as the
internal/repo name and the db filename. Plan-permitted prose ("set in the Star
Wars galaxy") and the trademark disclaimer are intentionally kept, so this guard
targets the *title/wordmark* specifically, not every "Star Wars" substring.
"""
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def _read(*parts):
    with open(os.path.join(ROOT, *parts), encoding="utf-8") as f:
        return f.read()


PORTAL = _read("static", "portal.html")
CLIENT = _read("static", "client.html")
CONFIG = _read("server", "config.py")


def test_config_game_name_is_parsec():
    assert 'game_name: str = "Parsec"' in CONFIG
    assert 'game_name: str = "Star Wars D6 MUSH"' not in CONFIG


def test_portal_wordmark_and_meta_are_parsec():
    assert "<h1>PARSEC</h1>" in PORTAL
    assert '<meta property="og:site_name" content="Parsec">' in PORTAL
    # The old working title is gone from EVERY portal surface — including the
    # nav logo (which used a middot: "SW · D6 MUSH"). No "MUSH" anywhere.
    assert "Star Wars D6 MUSH" not in PORTAL
    assert "MUSH" not in PORTAL


def test_client_branding_is_parsec():
    assert "<title>Parsec</title>" in CLIENT
    assert "PARSEC · AUTH" in CLIENT
    assert "SW MUSH" not in CLIENT


def test_telnet_banner_detrademarked_and_rebranded():
    from server.config import Config
    banner = Config().welcome_banner
    # Movie-quote trademark phrases removed.
    assert "long time ago in a galaxy far" not in banner
    assert "wretched hive" not in banner
    # The PARSEC block-letter wordmark is present.
    assert "██████" in banner  # ██████
