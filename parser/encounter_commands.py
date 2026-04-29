# -*- coding: utf-8 -*-
"""
parser/encounter_commands.py — Space Encounter Commands
Space Overhaul v3, Drop 1

Commands:
  respond <number|key>  — Select a choice in the active encounter
  stationact <number|key> — Station-specific action during multi-crew encounters
"""

import logging
from parser.commands import BaseCommand, CommandContext, AccessLevel

log = logging.getLogger(__name__)


class RespondCommand(BaseCommand):
    """Select a choice in the active space encounter."""
    name = "respond"
    aliases = ["resp"]
    help_text = (
        "Respond to an active space encounter by choosing an option.\n"
        "  respond 1       — choose option #1\n"
        "  respond bluff   — choose by name\n"
        "\n"
        "When an encounter presents choices (Imperial patrol, pirate demand, etc.),\n"
        "use this command to select your response. The choice may trigger skill checks\n"
        "depending on the option selected."
    )

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be in the game to use this.")
            return

        choice_input = ctx.args.strip()
        if not choice_input:
            await ctx.session.send_line(
                "  Usage: respond <number or choice name>\n"
                "  Example: respond 1, respond bluff"
            )
            return

        # Find the ship the player is on
        ship = await _get_ship_for_session(ctx)
        if ship is None:
            await ctx.session.send_line("  You're not aboard a ship.")
            return

        from engine.space_encounters import get_encounter_manager
        mgr = get_encounter_manager()

        handled = await mgr.handle_response(
            ship["id"], choice_input, ctx.session, ctx.db, ctx.session_mgr
        )

        if not handled:
            await ctx.session.send_line(
                "  No active encounter to respond to."
            )


class StationActCommand(BaseCommand):
    """Perform a station-specific action during a multi-crew encounter."""
    name = "stationact"
    aliases = ["sa"]
    help_text = (
        "Perform a station-specific action during a space encounter.\n"
        "  stationact 1           — choose station action #1\n"
        "  stationact hide_cargo  — choose by name\n"
        "\n"
        "During multi-crew encounters, each station may have specific actions\n"
        "available. Use this command to act from your station."
    )

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be in the game to use this.")
            return

        action_input = ctx.args.strip()
        if not action_input:
            await ctx.session.send_line(
                "  Usage: stationact <number or action name>"
            )
            return

        ship = await _get_ship_for_session(ctx)
        if ship is None:
            await ctx.session.send_line("  You're not aboard a ship.")
            return

        from engine.space_encounters import get_encounter_manager
        mgr = get_encounter_manager()
        enc = mgr.get_encounter(ship["id"])

        if enc is None:
            await ctx.session.send_line("  No active encounter.")
            return

        # Station actions are handled the same way as respond for now.
        # In Drop 10, this will dispatch to per-station action prompts.
        # For now, it's an alias that routes through the same handler.
        handled = await mgr.handle_response(
            ship["id"], action_input, ctx.session, ctx.db, ctx.session_mgr
        )

        if not handled:
            await ctx.session.send_line(
                "  No station actions available right now."
            )


class EncounterStatusCommand(BaseCommand):
    """Show the current encounter status."""
    name = "encounter"
    aliases = ["enc"]
    help_text = (
        "Show the status of your current space encounter, if any.\n"
        "  encounter  — display current encounter and available choices"
    )

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be in the game.")
            return

        ship = await _get_ship_for_session(ctx)
        if ship is None:
            await ctx.session.send_line("  You're not aboard a ship.")
            return

        from engine.space_encounters import get_encounter_manager
        mgr = get_encounter_manager()
        enc = mgr.get_encounter(ship["id"])

        if enc is None:
            await ctx.session.send_line("  No active encounter.")
            return

        AMBER = "\033[1;33m"
        CYAN = "\033[0;36m"
        DIM = "\033[2m"
        GREEN = "\033[1;32m"
        RST = "\033[0m"

        lines = [
            f"  {AMBER}[ENCOUNTER]{RST} {enc.encounter_type.title()} — {enc.state}",
            f"  {DIM}ID: {enc.id}  Zone: {enc.zone_id}{RST}",
        ]

        if enc.prompt:
            lines.append(f"  {enc.prompt}")

        if enc.chosen_key:
            lines.append(f"  {GREEN}Response: {enc.chosen_key}{RST}")
        elif enc.choices:
            remaining = enc.time_remaining()
            if remaining > 0:
                lines.append(f"  {AMBER}Time remaining: {int(remaining)}s{RST}")
            lines.append(f"  {DIM}Use 'respond <number>' to choose.{RST}")

        if enc.outcome:
            lines.append(f"  {GREEN}Outcome: {enc.outcome}{RST}")

        await ctx.session.send_line("\n".join(lines))


class InvestigateCommand(BaseCommand):
    """Investigate a fully-resolved anomaly to trigger its encounter."""
    name = "investigate"
    aliases = ["inv_anomaly"]
    help_text = (
        "Investigate a fully-resolved anomaly to see what's there.\n"
        "  investigate <anomaly_id>  — approach and interact with the anomaly\n"
        "\n"
        "Anomalies must be fully resolved via 'deepscan' first.\n"
        "Derelicts use 'salvage' instead."
    )

    async def execute(self, ctx: CommandContext):
        char = ctx.session.character
        if not char:
            await ctx.session.send_line("  You must be in the game.")
            return

        if not ctx.args.strip():
            await ctx.session.send_line("  Usage: investigate <anomaly_id>")
            return

        try:
            anomaly_id = int(ctx.args.strip())
        except ValueError:
            await ctx.session.send_line("  Usage: investigate <anomaly_id>")
            return

        ship = await _get_ship_for_session(ctx)
        if ship is None:
            await ctx.session.send_line("  You're not aboard a ship.")
            return
        if ship.get("docked_at"):
            await ctx.session.send_line("  Must be in open space.")
            return

        from engine.json_safe import load_ship_systems
        systems = load_ship_systems(ship)
        zone_id = systems.get("current_zone", "")

        from engine.space_anomalies import get_anomaly_by_id, remove_anomaly

        anomaly = get_anomaly_by_id(zone_id, anomaly_id)
        if anomaly is None:
            await ctx.session.send_line(
                f"  No anomaly #{anomaly_id} in this zone.")
            return

        if anomaly.resolution < anomaly.scans_needed:
            await ctx.session.send_line(
                f"  Anomaly #{anomaly_id} not fully resolved. "
                f"Use 'deepscan {anomaly_id}' to scan further.")
            return

        # Derelicts use 'salvage' command
        if anomaly.anomaly_type == "derelict":
            await ctx.session.send_line(
                "  Use 'salvage' to strip a derelict for components.")
            return

        # Map anomaly type to encounter type
        encounter_type_map = {
            "distress":     "distress",
            "cache":        "cache",
            "pirates":      "pirate_nest",
            "mineral_vein": "mineral_vein",
            "imperial":     "imperial",
            "mynock":       "mynock",
        }

        enc_type = encounter_type_map.get(anomaly.anomaly_type)
        if not enc_type:
            await ctx.session.send_line(
                f"  Can't investigate anomaly type '{anomaly.anomaly_type}'.")
            return

        from engine.space_encounters import get_encounter_manager
        mgr = get_encounter_manager()

        enc = await mgr.create_encounter(
            encounter_type=enc_type,
            zone_id=zone_id,
            target_ship_id=ship["id"],
            target_bridge_room=ship.get("bridge_room_id", 0),
            db=ctx.db,
            session_mgr=ctx.session_mgr,
            context={
                "anomaly_id": anomaly_id,
                "anomaly_type": anomaly.anomaly_type,
            },
        )

        if enc:
            # Consume the anomaly
            remove_anomaly(zone_id, anomaly_id)
        else:
            await ctx.session.send_line(
                "  Can't investigate right now (encounter cooldown or "
                "another encounter active).")


# ── Helper ───────────────────────────────────────────────────────────────────

async def _get_ship_for_session(ctx: CommandContext):
    """Get the ship dict for the player's current location (bridge room)."""
    room_id = ctx.session.character.get("room_id", 0)
    if not room_id:
        return None
    return await ctx.db.get_ship_by_bridge(room_id)


# ── Registration ─────────────────────────────────────────────────────────────

def register_encounter_commands(registry):
    """Register encounter commands with the command registry."""
    registry.register(RespondCommand())
    registry.register(StationActCommand())
    registry.register(EncounterStatusCommand())
    registry.register(InvestigateCommand())
    log.info("[encounters] encounter commands registered")
