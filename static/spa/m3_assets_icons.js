/* ============================================================================
   m3_assets_icons.js — 24×24 viewBox icons for the SPA HUD, sheet, holocron.

   Drop 4.1b · Tier 1 #4 · ported from map_v3/assets-icons.jsx (May 26 2026).

   Four icon families:
     - SERVICE_ICONS   — vendor, trainer, cantina, medical, dock, crafting,
                         mission_board, mail, comlink, bank
     - STATUS_ICONS    — stunned, wounded, in_cover, aim_held, force_focused
     - ATTR_ICONS      — dex, kno, mec, per, str, tec
     - FACTION_ICONS   — republic, cis, hutt, jedi, bounty_guild, black_sun,
                         mandalorian

   Each entry is a builder function: builder({ c, size }) → <svg> element.

   Per L1.5 (May 26 2026 amendment in Tier 1 #3 era-fidelity work): faction
   set is CW-canonical. NO empire/rebel icons.

   Each icon is a self-contained <svg> with its own viewBox, suitable for
   inline placement in HUD chips, sheet rows, holocron entries. Distinct
   from STYLE_PRIMITIVES (which return <g> for composition into the map).
   ============================================================================ */
(function(){
'use strict';

var svgEl = window.M3Tokens.svgEl;

// Common Icon wrapper. Returns a self-contained <svg> with the given
// stroke color, viewBox '0 0 24 24', and the supplied <path>/<circle>
// children. An optional title element provides hover-tooltip text.
function Icon(opts, children) {
  var c = opts.c || 'currentColor';
  var size = opts.size || 24;
  var sw = opts.sw || 1.6;
  var svgChildren = [];
  if (opts.title) {
    svgChildren.push(svgEl('title', null, [opts.title]));
  }
  for (var i = 0; i < children.length; i++) svgChildren.push(children[i]);
  return svgEl('svg', {
    width: size, height: size, viewBox: '0 0 24 24',
    fill: 'none', stroke: c, strokeWidth: sw,
    strokeLinecap: 'round', strokeLinejoin: 'round'
  }, svgChildren);
}

// ── SERVICE ICONS ────────────────────────────────────────────────────
var SERVICE_ICONS = {
  vendor: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Vendor' }, [
      svgEl('path', { d: 'M 3 8 L 21 8 L 19 12 L 5 12 Z' }),
      svgEl('path', { d: 'M 5 12 L 5 19 L 19 19 L 19 12' }),
      svgEl('path', { d: 'M 9 19 L 9 14 L 15 14 L 15 19' })
    ]);
  },
  trainer: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Trainer' }, [
      svgEl('circle', { cx: 12, cy: 6, r: 2.5 }),
      svgEl('path', { d: 'M 12 9 L 12 17' }),
      svgEl('path', { d: 'M 8 13 L 16 13' }),
      svgEl('path', { d: 'M 9 21 L 12 17 L 15 21' })
    ]);
  },
  cantina: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Cantina' }, [
      svgEl('path', { d: 'M 6 3 L 18 3 L 18 6 Q 12 10 12 14 L 12 19' }),
      svgEl('path', { d: 'M 6 3 L 6 6 Q 12 10 12 14' }),
      svgEl('path', { d: 'M 8 21 L 16 21', strokeWidth: 2 })
    ]);
  },
  medical: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Medical' }, [
      svgEl('rect', { x: 3, y: 6, width: 18, height: 14, rx: 1 }),
      svgEl('path', {
        d: 'M 10 10 L 14 10 L 14 13 L 17 13 L 17 17 L 14 17 L 14 20 L 10 20 L 10 17 L 7 17 L 7 13 L 10 13 Z'
      })
    ]);
  },
  dock: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Docking' }, [
      svgEl('circle', { cx: 12, cy: 12, r: 9 }),
      svgEl('circle', { cx: 12, cy: 12, r: 4 }),
      svgEl('path', { d: 'M 12 3 L 12 6' }),
      svgEl('path', { d: 'M 12 18 L 12 21' }),
      svgEl('path', { d: 'M 3 12 L 6 12' }),
      svgEl('path', { d: 'M 18 12 L 21 12' })
    ]);
  },
  crafting: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Crafting' }, [
      svgEl('path', { d: 'M 14 4 L 20 10 L 14 16' }),
      svgEl('path', { d: 'M 4 14 L 14 4 L 20 10 L 10 20 Z' })
    ]);
  },
  mission_board: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Mission Board' }, [
      svgEl('rect', { x: 4, y: 3, width: 16, height: 18, rx: 1 }),
      svgEl('path', { d: 'M 7 8 L 17 8' }),
      svgEl('path', { d: 'M 7 12 L 17 12' }),
      svgEl('path', { d: 'M 7 16 L 13 16' })
    ]);
  },
  mail: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Mail Terminal' }, [
      svgEl('rect', { x: 3, y: 6, width: 18, height: 12, rx: 1 }),
      svgEl('path', { d: 'M 3 7 L 12 14 L 21 7' })
    ]);
  },
  comlink: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Comlink' }, [
      svgEl('rect', { x: 9, y: 3, width: 6, height: 18, rx: 1 }),
      svgEl('path', { d: 'M 10 7 L 14 7' }),
      svgEl('circle', { cx: 12, cy: 17, r: 1 })
    ]);
  },
  bank: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Bank' }, [
      svgEl('path', { d: 'M 3 9 L 12 4 L 21 9 L 21 11 L 3 11 Z' }),
      svgEl('path', { d: 'M 6 11 L 6 18' }),
      svgEl('path', { d: 'M 10 11 L 10 18' }),
      svgEl('path', { d: 'M 14 11 L 14 18' }),
      svgEl('path', { d: 'M 18 11 L 18 18' }),
      svgEl('path', { d: 'M 3 18 L 21 18 L 21 20 L 3 20 Z' })
    ]);
  }
};

// ── STATUS ICONS ─────────────────────────────────────────────────────
var STATUS_ICONS = {
  stunned: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Stunned' }, [
      svgEl('path', { d: 'M 8 4 L 16 4 L 8 12 L 16 12 L 8 20 L 16 20' })
    ]);
  },
  wounded: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Wounded' }, [
      svgEl('path', { d: 'M 12 3 Q 14 7 14 10 Q 14 14 12 16 Q 10 14 10 10 Q 10 7 12 3 Z',
                      fill: o.c }),
      svgEl('circle', { cx: 12, cy: 18, r: 1.5, fill: o.c })
    ]);
  },
  in_cover: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'In Cover' }, [
      svgEl('path', { d: 'M 4 20 L 4 12 L 8 8 L 12 12 L 12 20' }),
      svgEl('path', { d: 'M 12 20 L 12 14 L 16 10 L 20 14 L 20 20' }),
      svgEl('circle', { cx: 8, cy: 6, r: 2 })
    ]);
  },
  aim_held: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Aim Held' }, [
      svgEl('circle', { cx: 12, cy: 12, r: 8 }),
      svgEl('circle', { cx: 12, cy: 12, r: 3 }),
      svgEl('path', { d: 'M 12 1 L 12 5' }),
      svgEl('path', { d: 'M 12 19 L 12 23' }),
      svgEl('path', { d: 'M 1 12 L 5 12' }),
      svgEl('path', { d: 'M 19 12 L 23 12' })
    ]);
  },
  force_focused: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Force Focused' }, [
      svgEl('circle', { cx: 12, cy: 12, r: 3 }),
      svgEl('path', { d: 'M 12 4 Q 18 8 12 12 Q 6 16 12 20' }),
      svgEl('path', { d: 'M 12 4 Q 6 8 12 12 Q 18 16 12 20' })
    ]);
  }
};

// ── ATTRIBUTE GLYPHS ─────────────────────────────────────────────────
var ATTR_ICONS = {
  dex: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Dexterity' }, [
      svgEl('path', { d: 'M 4 18 Q 8 4 12 12 Q 16 20 20 6' })
    ]);
  },
  kno: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Knowledge' }, [
      svgEl('path', { d: 'M 4 4 L 4 20 L 12 18 L 20 20 L 20 4 L 12 6 Z' }),
      svgEl('path', { d: 'M 12 6 L 12 18' })
    ]);
  },
  mec: function(o) {
    var children = [svgEl('circle', { cx: 12, cy: 12, r: 4 })];
    // 6 spokes around the center
    [0, 60, 120, 180, 240, 300].forEach(function(a) {
      var rad = a * Math.PI / 180;
      children.push(svgEl('line', {
        x1: 12 + Math.cos(rad) * 5, y1: 12 + Math.sin(rad) * 5,
        x2: 12 + Math.cos(rad) * 8, y2: 12 + Math.sin(rad) * 8
      }));
    });
    return Icon({ c: o.c, size: o.size, title: 'Mechanical' }, children);
  },
  per: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Perception' }, [
      svgEl('path', { d: 'M 2 12 Q 12 4 22 12 Q 12 20 2 12 Z' }),
      svgEl('circle', { cx: 12, cy: 12, r: 3 })
    ]);
  },
  str: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Strength' }, [
      svgEl('path', { d: 'M 6 6 L 4 12 L 6 18' }),
      svgEl('path', { d: 'M 18 6 L 20 12 L 18 18' }),
      svgEl('rect', { x: 6, y: 10, width: 12, height: 4 })
    ]);
  },
  tec: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Technical' }, [
      svgEl('path', { d: 'M 4 4 L 20 4 L 20 20 L 4 20 Z' }),
      svgEl('path', { d: 'M 8 8 L 16 8' }),
      svgEl('path', { d: 'M 8 12 L 14 12' }),
      svgEl('path', { d: 'M 8 16 L 16 16' })
    ]);
  }
};

// ── FACTION SIGILS ───────────────────────────────────────────────────
// CW-canonical set per Tier 1 #3 era-fidelity work + L1.5 amendment.
// NO empire/rebel sigils.
var FACTION_ICONS = {
  republic: function(o) {
    var children = [svgEl('circle', { cx: 12, cy: 12, r: 9 })];
    // 8 spokes radiating from center
    for (var i = 0; i < 8; i++) {
      var a = (i / 8) * Math.PI * 2 - Math.PI / 2;
      children.push(svgEl('line', {
        x1: 12, y1: 12,
        x2: 12 + Math.cos(a) * 8, y2: 12 + Math.sin(a) * 8
      }));
    }
    children.push(svgEl('circle', { cx: 12, cy: 12, r: 2, fill: o.c, stroke: 'none' }));
    return Icon({ c: o.c, size: o.size, title: 'Galactic Republic' }, children);
  },
  cis: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'CIS · Separatists' }, [
      svgEl('path', { d: 'M 12 3 L 21 12 L 12 21 L 3 12 Z' }),
      svgEl('path', { d: 'M 12 7 L 17 12 L 12 17 L 7 12 Z', fill: o.c, stroke: 'none' })
    ]);
  },
  hutt: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Hutt Cartel' }, [
      svgEl('path', { d: 'M 6 4 L 18 4 L 20 8 L 18 20 L 6 20 L 4 8 Z' }),
      svgEl('circle', { cx: 9, cy: 10, r: 1, fill: o.c, stroke: 'none' }),
      svgEl('circle', { cx: 15, cy: 10, r: 1, fill: o.c, stroke: 'none' }),
      svgEl('path', { d: 'M 8 15 Q 12 17 16 15' })
    ]);
  },
  jedi: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Jedi Order' }, [
      svgEl('circle', { cx: 12, cy: 12, r: 8 }),
      svgEl('path', { d: 'M 12 4 Q 8 12 12 20 Q 16 12 12 4 Z',
                      fill: o.c, stroke: 'none', opacity: 0.5 })
    ]);
  },
  bounty_guild: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Bounty Hunters Guild' }, [
      svgEl('path', { d: 'M 12 3 L 14 8 L 19 8 L 15 12 L 17 18 L 12 14 L 7 18 L 9 12 L 5 8 L 10 8 Z' })
    ]);
  },
  black_sun: function(o) {
    var children = [svgEl('circle', { cx: 12, cy: 12, r: 4, fill: o.c, stroke: 'none' })];
    // 8 radiating spokes
    for (var i = 0; i < 8; i++) {
      var a = (i / 8) * Math.PI * 2;
      var x = 12 + Math.cos(a) * 9;
      var y = 12 + Math.sin(a) * 9;
      children.push(svgEl('path', {
        d: 'M ' + (12 + Math.cos(a) * 5) + ' ' + (12 + Math.sin(a) * 5) + ' L ' + x + ' ' + y,
        strokeWidth: 2.5
      }));
    }
    return Icon({ c: o.c, size: o.size, title: 'Black Sun' }, children);
  },
  mandalorian: function(o) {
    return Icon({ c: o.c, size: o.size, title: 'Mandalorian Clans' }, [
      svgEl('path', { d: 'M 4 8 Q 12 2 20 8 L 20 14 Q 12 22 4 14 Z' }),
      svgEl('path', { d: 'M 9 10 L 11 12 L 9 14' }),
      svgEl('path', { d: 'M 15 10 L 13 12 L 15 14' }),
      svgEl('path', { d: 'M 12 14 L 12 18' })
    ]);
  }
};

window.M3AssetsIcons = {
  Icon: Icon,
  SERVICE_ICONS: SERVICE_ICONS,
  STATUS_ICONS: STATUS_ICONS,
  ATTR_ICONS: ATTR_ICONS,
  FACTION_ICONS: FACTION_ICONS
};

})();
