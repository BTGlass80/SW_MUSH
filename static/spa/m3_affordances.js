/* ============================================================================
   m3_affordances.js — Context-aware clickable affordances (UX Drop 1)

   Closes the "friction-to-action" loop on the HERE panel + the qa-row smart
   buttons. Pure client render over fields the server already produces — no new
   verbs, no phantom fields. Every affordance is a SHORTCUT for a parser command
   the player can still type; nothing here gates pace or information.

   What it surfaces (all server-driven):
     - Clickable entity NAMES → `look <name>` (mirrors the click-to-move
       sendCmd() dispatch pattern in client.html: a click issues the verb).
     - CLAIM on an NPC row when `npc.is_bounty_target` (the caller's OWN claimed
       bounty target is standing here) → the real `+bounty/collect` verb (which
       takes NO argument — it operates on the caller's single active contract).
     - SELL on a vendor-droid row when the player has sellable loadout
       (`hud.loadout` present) → `sell` (verb already exists).
     - FLEE injected into the qa-row when `hud.in_combat` → the real `flee`
       verb (key "flee", aliases run/retreat — verified in combat_commands.py).

   Discipline (roadmap §"Context-aware affordances"):
     - Server stays authoritative for WHICH verbs. The client renders the action
       list the server sends; new affordances each map to a confirmed real verb.
     - No modals / focus-steal. Names + buttons are inline markup on the existing
       HERE rows and qa-row injection seam. No `prefers-reduced-motion` violation
       (no animation added here).
     - Web-only; telnet keeps `look`/`sell`/`+bounty/collect`/`flee` as typed
       verbs and simply doesn't get the buttons.

   DI: `init({ sendCmd })` is called once from client.html so the module never
   reaches into client.html internals beyond the one dispatch function. If init
   is skipped the module falls back to a global `window.sendCmd` if present.
   ============================================================================ */
(function () {
  'use strict';

  var _sendCmd = null;

  function _dispatch(cmd) {
    var fn = _sendCmd || (typeof window !== 'undefined' ? window.sendCmd : null);
    if (typeof fn === 'function') {
      try { fn(cmd); } catch (e) { /* never let a click throw */ }
    }
  }

  // ── Clickable entity name ─────────────────────────────────────────────────
  // Turn a HERE-panel name element into a click target that examines the entity
  // (`look <name>`). Additive only: keeps the existing classes/text, adds a
  // pointer affordance + keyboard accessibility (Enter/Space), and a title.
  // Returns the same element for chaining.
  function makeNameClickable(nameEl, name) {
    if (!nameEl || !name) return nameEl;
    nameEl.classList.add('here-name-clickable');
    nameEl.setAttribute('role', 'button');
    nameEl.setAttribute('tabindex', '0');
    nameEl.title = 'Examine ' + name;
    nameEl.addEventListener('click', function () { _dispatch('look ' + name); });
    nameEl.addEventListener('keydown', function (ev) {
      // a11y: activate on Enter / Space, the standard button keys. Does not
      // steal focus from the command line — focus only lands here on Tab.
      if (ev.key === 'Enter' || ev.key === ' ' || ev.key === 'Spacebar') {
        ev.preventDefault();
        _dispatch('look ' + name);
      }
    });
    return nameEl;
  }

  // ── Bounty-target row decoration ──────────────────────────────────────────
  // When an NPC is the caller's claimed bounty target, mark the row (reusing the
  // hostile-glow styling vocabulary via the `bounty-target` class) so the win
  // condition is VISIBLE. The CLAIM button itself is injected by the server's
  // npc.actions list ("claim") through the existing HERE action-button loop;
  // this only adds the row highlight + a marker badge.
  function decorateBountyRow(rowEl, npc) {
    if (!rowEl || !npc || !npc.is_bounty_target) return;
    rowEl.classList.add('bounty-target');
    rowEl.title = 'Your bounty target — defeat then CLAIM';
  }

  // Map the server `claim` action verb → the real parser command.
  // `+bounty/collect` takes NO argument (it resolves the caller's single active
  // contract), so we send it bare regardless of npc/contract id.
  function commandForAction(action, npc) {
    if (action === 'claim') return '+bounty/collect';
    // Default: "<verb> <name>" — the legacy HERE button contract.
    return action + ' ' + (npc && npc.name ? npc.name : '');
  }

  function titleForAction(action, npc) {
    var nm = (npc && npc.name) ? npc.name : 'target';
    switch (action) {
      case 'claim':  return 'Collect the bounty on ' + nm;
      case 'sell':   return 'Sell goods to ' + nm;
      default:       return null;
    }
  }

  // ── SELL presence ─────────────────────────────────────────────────────────
  // The player can sell iff they carry something sellable. The server already
  // ships `hud.loadout` (weapon/armor/consumables); its presence is the
  // client-derivable signal. The `sell` verb validates the actual sale
  // server-side, so a false positive is harmless (it just opens the sell flow).
  function hasSellableLoadout(hud) {
    var lo = hud && hud.loadout;
    if (!lo || typeof lo !== 'object') return false;
    if (lo.weapon || lo.armor) return true;
    return Array.isArray(lo.consumables) && lo.consumables.length > 0;
  }

  // ── qa-row context descriptors ────────────────────────────────────────────
  // Returns the list of EXTRA quick-button descriptors to inject given the
  // current room/combat context. Mirrors the {label,qa,cmd,action,tip} shape
  // the existing _buildExploreButtons uses. The caller decides insertion point.
  function extraQuickButtons(ctx) {
    ctx = ctx || {};
    var inject = [];
    if (ctx.inCombat) {
      // FLEE → the real disengage verb. Highest priority in a fight.
      inject.push({
        label: 'FLEE', qa: 'FLEE', cmd: 'flee', action: 'send',
        tip: 'Attempt to disengage and escape the fight',
      });
    }
    if (ctx.hasBountyTarget) {
      inject.push({
        label: 'CLAIM', qa: 'CLAIM', cmd: '+bounty/collect', action: 'send',
        tip: 'Collect the bounty on your defeated target',
      });
    }
    return inject;
  }

  // Does the room_contents payload (object form {npcs,...}) contain at least one
  // of the caller's bounty targets? Tolerant of the array/absent shapes.
  function roomHasBountyTarget(roomContents) {
    if (!roomContents || typeof roomContents !== 'object') return false;
    var npcs = roomContents.npcs;
    if (!Array.isArray(npcs)) return false;
    return npcs.some(function (n) { return n && n.is_bounty_target; });
  }

  function init(deps) {
    deps = deps || {};
    if (typeof deps.sendCmd === 'function') _sendCmd = deps.sendCmd;
  }

  window.M3Affordances = {
    init: init,
    makeNameClickable: makeNameClickable,
    decorateBountyRow: decorateBountyRow,
    commandForAction: commandForAction,
    titleForAction: titleForAction,
    hasSellableLoadout: hasSellableLoadout,
    extraQuickButtons: extraQuickButtons,
    roomHasBountyTarget: roomHasBountyTarget,
  };
})();
