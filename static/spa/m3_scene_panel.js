/* ============================================================================
   m3_scene_panel.js — Active-scene header card (UX Drop 5: presence + social).

   The right-rail SCENE card. A lean, read-only HEADER for the RP scene running
   in the player's current room: scene title + type, and a participant roster
   with a per-player IC pose-count chip ("who's posing, and how much").

   It is a *header*, never the body. Real-time pose fidelity continues to flow
   over the existing typed `pose_event` broadcast into the main event log — the
   card NEVER blocks, throttles, or summarizes that stream. The sidebar is a
   secondary, social-proof view; the pose log stays the source of truth at full
   speed. Pure render over the `hud.active_scene` block
   (server/session.py::_hud_scene_context). Zero new socket cadence: rides the
   existing HUD tick. Absent/empty active_scene ⇒ the consumer hides the card.

   Payload (hud.active_scene):
     {
       scene_id: 12,
       title: "Cantina standoff",
       type: "Social",
       started_at: 1718900000.0,
       creator_name: "Rax" | null,
       pose_count: 7,                                  // total IC poses
       participants: [ {id, name, pose_count}, ... ]   // viewer included
     }

   XSS contract: scene title, type, creator_name and player names are
   server-authored free text — every one is written via textContent or routed
   through the injected escapeHtml, never raw innerHTML.

   Dependency injection (mirrors m3_combat_theater.js / m3_situation_board.js):
     · init({ escapeHtml })  — injects the shared client escape; falls back to
       a built-in so the module is unit-testable standalone under jsdom.
   ============================================================================ */
(function(){
'use strict';

// ── Module-private escape hook (DI, mirrors m3_situation_board.init). ──
var _escapeHtml = _defaultEscapeHtml;

function init(deps) {
  deps = deps || {};
  if (typeof deps.escapeHtml === 'function') _escapeHtml = deps.escapeHtml;
}

function _defaultEscapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ── tiny element helper (mirror m3_situation_board.el(); textContent is the
//    safe path — server text never reaches innerHTML here). ──
function el(tag, attrs, children){
  var n = document.createElement(tag);
  if (attrs){
    Object.keys(attrs).forEach(function(k){
      if (k === 'text') { n.textContent = attrs[k]; }
      else if (k === 'class') { n.className = attrs[k]; }
      else if (k === 'title') { n.setAttribute('title', attrs[k]); }
      else { n.setAttribute(k, attrs[k]); }
    });
  }
  (children || []).forEach(function(c){
    if (c == null) return;
    n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  });
  return n;
}

function humanize(code){
  if (!code) return '';
  return String(code).replace(/_/g, ' ').replace(/\b\w/g, function(m){
    return m.toUpperCase();
  });
}

/* render(activeScene) → DOM node, or null when there is no scene.

   `activeScene` is hud.active_scene. A falsy / non-object value, or a value
   with no participants AND no title, returns null so the consumer hides the
   card (idle room). Defensive about shape: every field is optional. */
function render(activeScene){
  if (!activeScene || typeof activeScene !== 'object') return null;

  var title       = activeScene.title || '';
  var sceneType   = activeScene.type || '';
  var creator     = activeScene.creator_name || '';
  var totalPoses  = Number(activeScene.pose_count) || 0;
  var participants = Array.isArray(activeScene.participants)
    ? activeScene.participants : [];

  // Nothing to show at all ⇒ hide. (A live scene always has at least the
  // creator as a participant, but be defensive about a malformed push.)
  if (!title && participants.length === 0) return null;

  var root = el('div', { class: 'scene-card' });

  // ── Header line: title + type chip. ──
  var head = el('div', { class: 'scene-head' });
  head.appendChild(el('span', {
    class: 'scene-title',
    text: title || 'Untitled scene',
    title: title || 'Untitled scene',
  }));
  if (sceneType) {
    head.appendChild(el('span', {
      class: 'scene-type-chip',
      text: humanize(sceneType),
    }));
  }
  root.appendChild(head);

  // ── Sub-line: total IC poses + creator (read-only social proof). ──
  var meta = el('div', { class: 'scene-meta' });
  meta.appendChild(el('span', {
    class: 'scene-pose-total',
    text: totalPoses + (totalPoses === 1 ? ' pose' : ' poses'),
  }));
  if (creator) {
    meta.appendChild(el('span', {
      class: 'scene-creator',
      text: 'by ' + creator,
      title: 'Started by ' + creator,
    }));
  }
  root.appendChild(meta);

  // ── Participant roster: name + per-player pose-count chip. ──
  if (participants.length) {
    var roster = el('div', { class: 'scene-roster' });
    participants.forEach(function(p){
      if (!p) return;
      var row = el('div', { class: 'scene-part' });
      row.appendChild(el('span', { class: 'scene-part-icon', text: '👤' }));
      row.appendChild(el('span', {
        class: 'scene-part-name',
        text: p.name || 'Someone',
        title: p.name || 'Someone',
      }));
      var n = Number(p.pose_count) || 0;
      var chip = el('span', {
        class: 'scene-pose-chip' + (n === 0 ? ' zero' : ''),
        text: String(n),
        title: n + (n === 1 ? ' IC pose' : ' IC poses'),
      });
      row.appendChild(chip);
      roster.appendChild(row);
    });
    root.appendChild(roster);
  }

  return root;
}

window.M3ScenePanel = {
  render: render,
  init: init,
};

})();
