/* ============================================================================
   m3_holocron.js — Holocron in-game lore browser.

   Drop 4.7 · Tier 1 #4 · ported from map_v3/holocron.jsx (536 JSX LOC)
   in SW_MUSH_UIUX_Bugfix_26May26.zip (May 27 2026).

   In the design canon (vision_doc §6, holocron_design): every clickable
   noun in the game opens the holocron to the right entry. Categories:
   planets, species, factions, weapons, vehicles, NPCs, lore. "Known"
   vs "unknown" indicators per the vision doc — players earn knowledge
   by exposure.

   What this module ships:
     · M3Holocron.buildHolocron(p, hooks?)                  standalone container
     · M3Holocron.buildHolocronModal(p, hooks?)             popup with chrome
     · M3Holocron.buildHolocronContent(p, hooks?)           3-column body
     · M3Holocron.buildCategoryNav(p, categories, hooks?)   left column
     · M3Holocron.buildEntryList(p, entries, hooks?)        left column lower
     · M3Holocron.buildReadingPane(p, selected, hooks?)     center column
     · M3Holocron.buildCrossRefs(p, selected, hooks?)       right column
     · M3Holocron.HOLOCRON_DATA_FIXTURE                     demo data
     · M3Holocron.HOLOCRON_LORE_NOUNS                       cross-ref nouns

   B3 era-contamination clean — the fixture entry is the Hutt Cartel
   page from the Clone Wars era (≈22-19 BBY); references the Republic
   and CIS, not the Empire. STORY_NOUNS (in m3_sheet.js) and
   HOLOCRON_LORE_NOUNS (here) are independent lists by design — the
   sheet's noun list points at the player's narrative scope; the
   holocron's points at the lore catalog.

   Dependencies (loaded earlier in the SPA load order):
     · window.M3AssetsIcons.FACTION_ICONS (m3_assets_icons.js Drop 4.1c)
       — consumed for the title-strip faction badge. Falls back to a
       small placeholder if the asset module isn't loaded or the icon
       throws.

   What this module does NOT ship:
     · Live category switching / entry selection state. The JSX uses
       a single hardcoded HOLOCRON_DATA fixture with `selected` baked
       in; the vanilla version accepts hooks (onCategoryClick,
       onEntryClick) and renders whatever data the caller passes.
     · Real noun cross-reference wiring. The JSX shows hover-noun
       highlighting; the vanilla version renders the spans with
       'cursor: help' but no actual cross-reference dispatch — that's
       a future drop with a real lore-noun registry.
     · Holocron data backend. Same as sheet-v2's character data —
       the eventual wire-in supplies a real entry from the lore
       catalog.

   Loading order in client.html: after m3_assets_icons.js. Placed
   alongside m3_sheet.js in the SPA script-tag block.
   ============================================================================ */
(function(){
'use strict';

// ─── Module-private state ────────────────────────────────────────────
var _escapeHtml = null;

function init(deps) {
  deps = deps || {};
  _escapeHtml = deps.escapeHtml || _defaultEscapeHtml;
}

function _defaultEscapeHtml(s) {
  return String(s == null ? '' : s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;')
    .replace(/'/g, '&#39;');
}

// ─── htmlEl / svgEl: same shape as m3_sheet.js (Drop 4.6) ────────────
function htmlEl(tag, props, children) {
  var el = document.createElement(tag);
  if (props) {
    for (var key in props) {
      if (!Object.prototype.hasOwnProperty.call(props, key)) continue;
      var val = props[key];
      if (val === undefined || val === null || val === false) continue;
      if (key === 'style') {
        applyStyle(el, val);
      } else if (key === 'className') {
        el.className = String(val);
      } else if (key === 'onClick' && typeof val === 'function') {
        el.addEventListener('click', val);
      } else if (key.indexOf('on') === 0 && typeof val === 'function') {
        el.addEventListener(key.slice(2).toLowerCase(), val);
      } else {
        el.setAttribute(key, String(val));
      }
    }
  }
  if (children) {
    for (var i = 0; i < children.length; i++) {
      var child = children[i];
      if (child === null || child === undefined || child === false) continue;
      if (typeof child === 'string' || typeof child === 'number') {
        el.appendChild(document.createTextNode(String(child)));
      } else {
        el.appendChild(child);
      }
    }
  }
  return el;
}

function svgEl(tag, attrs, children) {
  var el = document.createElementNS('http://www.w3.org/2000/svg', tag);
  if (attrs) {
    for (var key in attrs) {
      if (!Object.prototype.hasOwnProperty.call(attrs, key)) continue;
      var val = attrs[key];
      if (val === undefined || val === null || val === false) continue;
      if (key === 'style') applyStyle(el, val);
      else el.setAttribute(_camelToKebabSvg(key), String(val));
    }
  }
  if (children) {
    for (var i = 0; i < children.length; i++) {
      var child = children[i];
      if (child === null || child === undefined || child === false) continue;
      if (typeof child === 'string' || typeof child === 'number') {
        el.appendChild(document.createTextNode(String(child)));
      } else {
        el.appendChild(child);
      }
    }
  }
  return el;
}

function _camelToKebabSvg(k) {
  if (k === 'viewBox' || k === 'preserveAspectRatio' ||
      k === 'gradientTransform' || k === 'patternTransform' ||
      k === 'patternUnits' || k === 'patternContentUnits') return k;
  return k.replace(/[A-Z]/g, function(c) { return '-' + c.toLowerCase(); });
}

function applyStyle(el, style) {
  if (!style) return;
  for (var k in style) {
    if (!Object.prototype.hasOwnProperty.call(style, k)) continue;
    var v = style[k];
    if (v === null || v === undefined || v === false) continue;
    el.style[k] = (typeof v === 'number' && !_isUnitlessCss(k)) ? (v + 'px') : v;
  }
}

function _isUnitlessCss(k) {
  return (k === 'opacity' || k === 'zIndex' || k === 'fontWeight' ||
          k === 'flex' || k === 'flexGrow' || k === 'flexShrink' ||
          k === 'lineHeight' || k === 'order');
}

// ─── Lore-noun cross-ref list ───────────────────────────────────────
// These are the nouns the Hutt Cartel summary paragraphs highlight as
// cross-referenceable. In production each is hover-link to its own
// holocron entry. List is per-entry in the JSX source; for the vanilla
// version, the caller can override via hooks.loreNouns if their entry
// needs different noun coverage.
var HOLOCRON_LORE_NOUNS = [
  'Hutt Cartel', 'Council of Elders', 'Kajidic', 'Outer Rim',
  'Nal Hutta', 'Nar Shaddaa', "Smuggler's Moon", 'Tatooine',
  'Klatooine', "Si'klaata Cluster", 'Republic', 'Hutt law',
  'Clone Wars', 'CIS', 'Jabba Desilijic Tiure', 'Jabba', 'Ziro'
];

// ─── HOLOCRON_DATA sample fixture ───────────────────────────────────
// B3-clean — Clone Wars era references only. Used as default if caller
// doesn't pass data; also used by the regression tests to pin the
// fixture shape contract.
var HOLOCRON_DATA_FIXTURE = {
  categories: [
    { id: 'planets',  label: 'PLANETS',   icon: '◉', count: 47 },
    { id: 'species',  label: 'SPECIES',   icon: '✺', count: 124 },
    { id: 'factions', label: 'FACTIONS',  icon: '◈', count: 18, active: true },
    { id: 'weapons',  label: 'WEAPONS',   icon: '⋈', count: 82 },
    { id: 'vehicles', label: 'VEHICLES',  icon: '◬', count: 56 },
    { id: 'npcs',     label: 'PERSONS',   icon: '☖', count: 211 },
    { id: 'lore',     label: 'EVENTS',    icon: '✦', count: 38 },
  ],
  entries: {
    factions: [
      { slug: 'republic',     label: 'Galactic Republic',    era: 'Active', known: 'full' },
      { slug: 'cis',          label: 'CIS Separatists',      era: 'Active', known: 'full' },
      { slug: 'jedi_order',   label: 'Jedi Order',           era: 'Active', known: 'partial' },
      { slug: 'sith',         label: 'Sith',                 era: 'Hidden', known: 'rumor' },
      { slug: 'hutt_cartel',  label: 'Hutt Cartel',          era: 'Active', known: 'full', selected: true },
      { slug: 'bounty_guild', label: 'Bounty Hunters Guild', era: 'Active', known: 'partial' },
      { slug: 'black_sun',    label: 'Black Sun',            era: 'Active', known: 'rumor' },
      { slug: 'mandalorian',  label: 'Mandalorian Clans',    era: 'Active', known: 'partial' },
      { slug: 'death_watch',  label: 'Death Watch',          era: 'Active', known: 'rumor' },
      { slug: 'falleen',      label: 'Falleen Syndicate',    era: 'Active', known: 'rumor' },
    ],
  },
  selected: {
    category: 'factions',
    slug: 'hutt_cartel',
    title: 'Hutt Cartel',
    sub: 'Criminal Syndicate · Outer Rim · Active',
    factionId: 'hutt',
    // Clone-Wars-era summary; Republic + CIS framing.
    summary: [
      'The Hutt Cartel — also called the Council of Elders, in its own ' +
      'tongue Huttese Kajidic — is the loose confederation of Hutt crime ' +
      'lords that dominates the criminal underworld of the Outer Rim. ' +
      'The Cartel is not a state; it is an alliance of competing kajidics ' +
      '(clans), each ruled by a Hutt lord who governs a slice of the spice ' +
      'trade, slave trafficking, bounty issuance, gambling, and protection ' +
      'rackets.',
      "Headquartered on the swamp-world of Nal Hutta and operating most " +
      "visibly through its moon Nar Shaddaa — the 'Smuggler's Moon' — the " +
      "Cartel maintains influence across the Outer Rim from Tatooine to " +
      "Klatooine to the Si'klaata Cluster. Where the Republic's writ ends, " +
      "Hutt law begins.",
      'During the Clone Wars (~22–19 BBY), the Cartel has played both ' +
      'sides: officially neutral, privately trading with the Republic, ' +
      'the CIS, and anyone else with credits. The young Hutt lord Jabba ' +
      "Desilijic Tiure of Tatooine has become the de facto face of the " +
      "Cartel's external dealings since his uncle Ziro's recent disgrace.",
    ],
    stats: [
      ['Headquarters',   'Nal Hutta'],
      ['Founded',        '~25,000 BBY (Hutt Empire successor)'],
      ['Member species', 'Hutt (ruling) · diverse (subjects)'],
      ['Territory',      'Hutt Space + Outer Rim influence'],
      ['Membership',     '~200 ruling Hutts · countless retainers'],
      ['Posture (CW)',   'Officially neutral'],
      ['PC standing',    'Friendly (favors owed)'],
    ],
    leaders: [
      { name: 'Jabba Desilijic Tiure', role: 'Tatooine boss',          standing: 'friendly' },
      { name: 'Gardulla the Elder',    role: 'Slave-trade matriarch', standing: 'neutral'  },
      { name: 'Marlo the Hutt',        role: 'Spice supply lord',     standing: 'unknown'  },
    ],
    relatedPlanets: [
      { slug: 'tatooine',    label: 'Tatooine',    note: "Jabba's seat" },
      { slug: 'nal_hutta',   label: 'Nal Hutta',   note: 'Capital' },
      { slug: 'nar_shaddaa', label: 'Nar Shaddaa', note: "Smuggler's Moon" },
      { slug: 'klatooine',   label: 'Klatooine',   note: 'Vassal world' },
    ],
    relatedFactions: [
      { slug: 'bounty_guild', label: 'Bounty Hunters Guild', relation: 'Allied' },
      { slug: 'black_sun',    label: 'Black Sun',            relation: 'Rival' },
      { slug: 'pyke',         label: 'Pyke Syndicate',       relation: 'Subordinate' },
    ],
    known: {
      full: [
        'General structure & leadership',
        'Tatooine operations',
        'Mos Eisley contacts',
        'Jabba Desilijic Tiure',
        'Standard rates of "tribute"',
      ],
      partial: [
        'Nal Hutta politics',
        'Spice supply chain',
      ],
      unknown: [
        'Desilijic family tree',
        "Ziro Desilijic's recent moves",
        'Cartel war reserves',
      ],
    },
    quote: '"In the Outer Rim, there is no law. There is the Hutts, and there are those who pay the Hutts."',
    quoteSource: '— Captain Vex, Senate Bureau of Intelligence (field briefing)',
  },
};

// ─── Lore-noun highlighting ─────────────────────────────────────────
// Splits a paragraph on the noun list; returns an array of DOM nodes
// + string fragments. The JSX wraps each match in a clickable <span>;
// the vanilla version does the same, with a `data-lore-noun` attribute
// so test code and consumers can find them.
function highlightLore(text, p, nounsOverride) {
  if (!text) return [''];
  var nouns = nounsOverride || HOLOCRON_LORE_NOUNS;
  var escapeRegex = function(s) { return s.replace(/[.*+?^${}()|[\]\\]/g, '\\$&'); };
  var re = new RegExp('(' + nouns.map(escapeRegex).join('|') + ')', 'g');
  var parts = String(text).split(re);
  return parts.map(function(part) {
    if (nouns.indexOf(part) !== -1) {
      return htmlEl('span', {
        'data-lore-noun': part,
        title: 'Open holocron: ' + part,
        style: {
          color: p.amber,
          borderBottom: '1px dotted ' + p.amber,
          cursor: 'help',
        }
      }, [part]);
    }
    return part;
  });
}

// ─── SubHead helper ─────────────────────────────────────────────────
function buildSubHead(p, text) {
  return htmlEl('div', {
    style: {
      fontSize: 9, letterSpacing: 3, color: p.amber, fontWeight: 600,
      borderBottom: '1px dashed ' + p.inkFaint, paddingBottom: 3,
    }
  }, [text]);
}

// ─── KnowledgeRow helper ────────────────────────────────────────────
function buildKnowledgeRow(p, color, label, items) {
  var dot = htmlEl('div', {
    style: { width: 6, height: 6, borderRadius: '50%', background: color,
             boxShadow: '0 0 3px ' + color }
  });
  var head = htmlEl('div', {
    'data-knowledge-label': label,
    style: {
      display: 'flex', alignItems: 'center', gap: 6,
      fontSize: 9, letterSpacing: 1.5, marginBottom: 4,
    }
  }, [dot, htmlEl('span', { style: { color: color, fontWeight: 700 } }, [label])]);

  var itemRows = (items || []).map(function(item) {
    var prefix = (label === 'UNKNOWN') ? '? ' : '› ';
    return htmlEl('div', {
      style: {
        fontSize: 10, color: p.ink, padding: '1px 12px',
        opacity: (label === 'UNKNOWN') ? 0.5 : 0.9,
      }
    }, [prefix + item]);
  });

  return htmlEl('div', {
    style: { marginTop: 8 }
  }, [head].concat(itemRows));
}

// ════════════════════════════════════════════════════════════════════
// CATEGORY NAV — left column, top portion
// ════════════════════════════════════════════════════════════════════
function buildCategoryNav(p, categories, hooks) {
  hooks = hooks || {};
  var onCategoryClick = hooks.onCategoryClick || null;

  var header = htmlEl('div', {
    style: {
      padding: '10px 14px', fontSize: 9, letterSpacing: 2.5, color: p.inkDim,
      borderBottom: '1px solid ' + p.inkFaint,
    }
  }, ['CATEGORIES']);

  var rows = (categories || []).map(function(c) {
    var rowProps = {
      'data-category-id': c.id,
      style: {
        padding: '7px 14px',
        background: c.active ? (p.amber + '22') : 'transparent',
        borderLeft: c.active ? ('2px solid ' + p.amber) : '2px solid transparent',
        display: 'flex', alignItems: 'center', justifyContent: 'space-between',
        cursor: 'pointer',
        fontSize: 11,
      }
    };
    if (typeof onCategoryClick === 'function') {
      rowProps.onClick = function() { onCategoryClick(c.id); };
    }
    return htmlEl('div', rowProps, [
      htmlEl('span', { style: { display: 'flex', alignItems: 'center', gap: 8 } }, [
        htmlEl('span', {
          style: { color: c.active ? p.amber : p.inkDim, fontSize: 12 }
        }, [c.icon]),
        htmlEl('span', {
          style: { color: c.active ? p.inkBright : p.ink, letterSpacing: 2 }
        }, [c.label]),
      ]),
      htmlEl('span', { style: { color: p.inkDim, fontSize: 9 } }, [String(c.count)]),
    ]);
  });

  return htmlEl('div', {
    style: { flex: '0 0 auto' }
  }, [header].concat([htmlEl('div', null, rows)]));
}

// ════════════════════════════════════════════════════════════════════
// ENTRY LIST — left column, bottom portion (within active category)
// ════════════════════════════════════════════════════════════════════
function buildEntryList(p, entries, categoryLabel, hooks) {
  hooks = hooks || {};
  var onEntryClick = hooks.onEntryClick || null;

  var header = htmlEl('div', {
    style: {
      padding: '10px 14px', fontSize: 9, letterSpacing: 2.5, color: p.inkDim,
      borderTop: '1px solid ' + p.inkFaint,
      borderBottom: '1px solid ' + p.inkFaint,
      marginTop: 8,
    }
  }, [categoryLabel + ' · ' + (entries || []).length + ' ENTRIES']);

  var rows = (entries || []).map(function(e) {
    var knownColor = (e.known === 'full')    ? p.green
                   : (e.known === 'partial') ? p.amber
                   :                           p.red;
    var rowProps = {
      'data-entry-slug': e.slug,
      style: {
        padding: '6px 14px',
        background: e.selected ? (p.amber + '33') : 'transparent',
        borderLeft: e.selected ? ('2px solid ' + p.amber) : '2px solid transparent',
        cursor: 'pointer',
        borderBottom: '1px dashed ' + p.inkFaint,
      }
    };
    if (typeof onEntryClick === 'function') {
      rowProps.onClick = function() { onEntryClick(e.slug); };
    }
    return htmlEl('div', rowProps, [
      htmlEl('div', {
        style: {
          fontSize: 10.5, color: e.selected ? p.inkBright : p.ink,
          fontWeight: e.selected ? 600 : 400,
          display: 'flex', justifyContent: 'space-between', alignItems: 'center',
        }
      }, [
        htmlEl('span', null, [e.label]),
        htmlEl('div', {
          style: {
            width: 5, height: 5, borderRadius: '50%',
            background: knownColor,
            boxShadow: '0 0 3px ' + knownColor,
          }
        }),
      ]),
      htmlEl('div', {
        style: { fontSize: 8, color: p.inkDim, letterSpacing: 1, marginTop: 1 }
      }, [
        String(e.era || '').toUpperCase() + ' · ' + String(e.known || '').toUpperCase()
      ]),
    ]);
  });

  return htmlEl('div', {
    style: { display: 'flex', flexDirection: 'column', flex: 1, overflow: 'hidden' }
  }, [
    header,
    htmlEl('div', {
      style: { flex: 1, overflowY: 'auto' }
    }, rows),
  ]);
}

// ════════════════════════════════════════════════════════════════════
// READING PANE — center column (title strip + quote + summary + stats
//                + leaders)
// ════════════════════════════════════════════════════════════════════
function buildReadingPane(p, sel, hooks) {
  hooks = hooks || {};
  if (!sel) {
    return htmlEl('div', {
      style: { padding: 22, color: p.inkDim, fontSize: 11 }
    }, ['(no entry selected)']);
  }

  // Title strip with faction-icon badge.
  var FACTION_ICONS = (window.M3AssetsIcons && window.M3AssetsIcons.FACTION_ICONS) || {};
  var badge;
  var iconFn = FACTION_ICONS[sel.factionId];
  if (typeof iconFn === 'function') {
    try {
      var iconEl = iconFn({ c: p.amber, size: 42 });
      if (iconEl && iconEl.nodeType) badge = iconEl;
    } catch (e) { /* fall through */ }
  }
  if (!badge) {
    // Fallback — simple amber diamond placeholder.
    badge = svgEl('svg', { viewBox: '0 0 30 30', width: 42, height: 42 }, [
      svgEl('polygon', {
        points: '15,3 26,9 26,21 15,27 4,21 4,9',
        fill: 'none', stroke: p.amber, strokeWidth: 1.5
      }),
      svgEl('polygon', {
        points: '15,9 21,12 21,18 15,21 9,18 9,12',
        fill: p.amber + '55', stroke: p.inkBright, strokeWidth: 0.8
      }),
    ]);
  }
  var badgeBox = htmlEl('div', {
    style: {
      width: 56, height: 56,
      border: '1px solid ' + p.amber,
      background: p.amber + '11',
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      flexShrink: 0,
    }
  }, [badge]);

  var titleBlock = htmlEl('div', null, [
    htmlEl('div', {
      style: { fontSize: 9, letterSpacing: 3, color: p.inkDim }
    }, [String(sel.category || '').toUpperCase() + ' · CRIMINAL ORGANIZATION']),
    htmlEl('div', {
      style: {
        fontSize: 28, letterSpacing: 2, color: p.inkBright, fontWeight: 700,
        lineHeight: 1.1, marginTop: 4,
        textShadow: '0 0 6px ' + p.amber + '55',
      }
    }, [String(sel.title || '').toUpperCase()]),
    htmlEl('div', {
      style: { fontSize: 10, letterSpacing: 1.5, color: p.inkDim, marginTop: 4 }
    }, [sel.sub || '']),
  ]);

  var titleStrip = htmlEl('div', {
    style: { display: 'flex', alignItems: 'flex-start', gap: 18, marginBottom: 14 }
  }, [badgeBox, titleBlock]);

  // Quote block.
  var quoteBlock = htmlEl('div', {
    style: {
      padding: '10px 16px', marginBottom: 20,
      borderLeft: '3px solid ' + p.amber,
      background: p.amber + '11',
      fontFamily: "'IBM Plex Sans', sans-serif",
      fontSize: 14, fontStyle: 'italic', color: p.inkBright,
      lineHeight: 1.5,
    }
  }, [
    sel.quote || '',
    htmlEl('div', {
      style: {
        fontSize: 10, color: p.inkDim, marginTop: 6, fontStyle: 'normal',
        letterSpacing: 1,
      }
    }, [sel.quoteSource || '']),
  ]);

  // Summary paragraphs with highlighted lore nouns.
  var summaryParas = (sel.summary || []).map(function(para) {
    return htmlEl('p', {
      style: { margin: '0 0 14px' }
    }, highlightLore(para, p, hooks.loreNouns));
  });
  var summaryBlock = htmlEl('div', {
    style: {
      fontFamily: "'IBM Plex Sans', sans-serif",
      fontSize: 14, lineHeight: 1.7, color: p.ink,
    }
  }, summaryParas);

  // Stats grid.
  var statRows = (sel.stats || []).map(function(pair) {
    return htmlEl('div', {
      style: {
        padding: '5px 10px',
        background: 'rgba(0,0,0,0.3)',
        border: '1px solid ' + p.inkFaint,
        display: 'flex', justifyContent: 'space-between',
      }
    }, [
      htmlEl('span', {
        style: { color: p.inkDim, fontSize: 10, letterSpacing: 1.5 }
      }, [String(pair[0]).toUpperCase()]),
      htmlEl('span', {
        style: { color: p.inkBright, fontSize: 10, letterSpacing: 0.5 }
      }, [String(pair[1])]),
    ]);
  });
  var statsBlock = htmlEl('div', {
    style: { marginTop: 20 }
  }, [
    buildSubHead(p, 'RECORD · STATISTICS'),
    htmlEl('div', {
      style: { display: 'grid', gridTemplateColumns: '1fr 1fr', gap: 4, marginTop: 8 }
    }, statRows),
  ]);

  // Notable leaders.
  var leaderRows = (sel.leaders || []).map(function(l) {
    var standingColor = (l.standing === 'friendly') ? p.green
                       : (l.standing === 'unknown') ? p.inkDim
                       :                              p.amber;
    return htmlEl('div', {
      'data-leader-name': l.name,
      style: {
        padding: '6px 10px',
        background: 'rgba(0,0,0,0.3)',
        border: '1px solid ' + p.inkFaint,
        display: 'grid', gridTemplateColumns: '1fr 1fr auto',
        gap: 8, alignItems: 'baseline',
      }
    }, [
      htmlEl('span', {
        style: { fontFamily: "'IBM Plex Sans'", fontSize: 13, color: p.inkBright, fontWeight: 600 }
      }, [l.name]),
      htmlEl('span', { style: { fontSize: 10, color: p.inkDim } }, [l.role]),
      htmlEl('span', {
        style: { fontSize: 9, letterSpacing: 1.5, color: standingColor }
      }, [String(l.standing || '').toUpperCase()]),
    ]);
  });
  var leadersBlock = htmlEl('div', {
    style: { marginTop: 18 }
  }, [
    buildSubHead(p, 'NOTABLE FIGURES'),
    htmlEl('div', {
      style: { display: 'flex', flexDirection: 'column', gap: 4, marginTop: 8 }
    }, leaderRows),
  ]);

  return htmlEl('div', {
    style: { overflowY: 'auto', padding: '22px 36px' }
  }, [
    titleStrip,
    quoteBlock,
    summaryBlock,
    statsBlock,
    leadersBlock,
    htmlEl('div', { style: { height: 24 } }),
  ]);
}

// ════════════════════════════════════════════════════════════════════
// CROSS-REFS — right column (related planets + factions + known)
// ════════════════════════════════════════════════════════════════════
function buildCrossRefs(p, sel, hooks) {
  hooks = hooks || {};
  if (!sel) {
    return htmlEl('div', {
      style: { borderLeft: '1px solid ' + p.inkDim, background: 'rgba(0,0,0,0.3)',
               padding: '16px 14px' }
    }, []);
  }
  var onCrossRefClick = hooks.onCrossRefClick || null;

  function buildCrossRefRow(item, kind, colorOverride) {
    var props = {
      'data-cross-ref-slug': item.slug,
      'data-cross-ref-kind': kind,
      style: {
        padding: '5px 8px', marginBottom: 2,
        border: '1px solid ' + p.inkFaint,
        background: 'rgba(0,0,0,0.3)',
        cursor: 'pointer',
      }
    };
    if (typeof onCrossRefClick === 'function') {
      props.onClick = function() { onCrossRefClick(item.slug, kind); };
    }
    return htmlEl('div', props, [
      htmlEl('div', {
        style: { fontSize: 11, color: colorOverride || p.cyan, letterSpacing: 0.5 }
      }, [item.label]),
      htmlEl('div', {
        style: { fontSize: 9, color: p.inkDim, marginTop: 1 }
      }, [item.note || item.relation || '']),
    ]);
  }

  var planetsBlock = htmlEl('div', {
    style: { marginTop: 6, marginBottom: 14 }
  }, (sel.relatedPlanets || []).map(function(r) {
    return buildCrossRefRow(r, 'planet', p.cyan);
  }));

  var factionsBlock = htmlEl('div', {
    style: { marginTop: 6, marginBottom: 14 }
  }, (sel.relatedFactions || []).map(function(r) {
    return buildCrossRefRow(r, 'faction', p.amber);
  }));

  var known = sel.known || {};
  var knownBlock = htmlEl('div', null, [
    buildSubHead(p, 'YOUR KNOWLEDGE'),
    buildKnowledgeRow(p, p.green, 'KNOWN',   known.full),
    buildKnowledgeRow(p, p.amber, 'PARTIAL', known.partial),
    buildKnowledgeRow(p, p.red,   'UNKNOWN', known.unknown),
  ]);

  // Earn-more hint
  var hint = htmlEl('div', {
    style: {
      marginTop: 14, padding: '8px 10px',
      background: p.cyan + '11',
      border: '1px solid ' + p.cyan + '66',
      fontSize: 10, color: p.cyan, letterSpacing: 1, lineHeight: 1.5,
    }
  }, ['↪ Visit Nal Hutta or earn favor from a Hutt lord to learn more.']);

  return htmlEl('div', {
    style: {
      borderLeft: '1px solid ' + p.inkDim,
      background: 'rgba(0,0,0,0.3)',
      overflow: 'auto',
      padding: '16px 14px',
    }
  }, [
    buildSubHead(p, 'RELATED · PLANETS'),
    planetsBlock,
    buildSubHead(p, 'RELATED · FACTIONS'),
    factionsBlock,
    knownBlock,
    hint,
  ]);
}

// ════════════════════════════════════════════════════════════════════
// HOLOCRON CONTENT — full 3-column body
// ════════════════════════════════════════════════════════════════════
function buildHolocronContent(p, hooks) {
  hooks = hooks || {};
  var data = hooks.data || HOLOCRON_DATA_FIXTURE;
  var sel = data.selected;

  // TOP BAR — icon + title + search + close
  var holoIcon = svgEl('svg', {
    width: 28, height: 28, viewBox: '0 0 30 30',
    style: { filter: 'drop-shadow(0 0 4px ' + p.amber + ')' }
  }, [
    svgEl('polygon', {
      points: '15,3 26,9 26,21 15,27 4,21 4,9',
      fill: 'none', stroke: p.amber, strokeWidth: 1.5
    }),
    svgEl('polygon', {
      points: '15,9 21,12 21,18 15,21 9,18 9,12',
      fill: p.amber + '55', stroke: p.inkBright, strokeWidth: 0.8
    }),
  ]);

  var titleBlock = htmlEl('div', null, [
    htmlEl('div', {
      style: { fontSize: 10, letterSpacing: 3, color: p.inkDim, marginBottom: 2 }
    }, ['HOLOCRON · KNOWLEDGE ARCHIVE']),
    htmlEl('div', {
      style: { fontSize: 18, letterSpacing: 2, color: p.inkBright, fontWeight: 600 }
    }, [sel ? sel.title : '']),
  ]);

  var leftCluster = htmlEl('div', {
    style: { display: 'flex', alignItems: 'center', gap: 16 }
  }, [holoIcon, titleBlock]);

  var totalEntries = 0;
  (data.categories || []).forEach(function(c) { totalEntries += (c.count || 0); });
  var searchBar = htmlEl('div', {
    style: {
      display: 'flex', alignItems: 'center', gap: 8,
      padding: '6px 12px', minWidth: 280,
      background: p.skyDeep, border: '1px solid ' + p.inkDim,
    }
  }, [
    htmlEl('span', { style: { color: p.amber, fontSize: 14 } }, ['⌕']),
    htmlEl('span', {
      style: { color: p.inkDim, fontSize: 11, flex: 1 }
    }, ['Search ' + totalEntries + ' entries…']),
    htmlEl('span', {
      style: { color: p.inkFaint, fontSize: 9, letterSpacing: 1 }
    }, ['⌘K']),
  ]);

  var closeBtnProps = {
    style: {
      padding: '4px 10px', background: 'transparent',
      border: '1px solid ' + p.inkDim, color: p.ink,
      fontSize: 10, letterSpacing: 2, cursor: 'pointer',
    }
  };
  if (typeof hooks.onClose === 'function') {
    closeBtnProps.onClick = hooks.onClose;
  }
  var closeBtn = htmlEl('button', closeBtnProps, ['ESC ✕']);

  var topBar = htmlEl('div', {
    style: {
      height: 60, padding: '12px 20px',
      borderBottom: '1px solid ' + p.inkDim,
      background: 'linear-gradient(180deg, ' + p.sky + ', ' + p.skyDeep + ')',
      display: 'flex', alignItems: 'center', justifyContent: 'space-between',
    }
  }, [leftCluster, searchBar, closeBtn]);

  // LEFT column — categories + entry list
  var entries = (data.entries && data.entries[sel && sel.category]) || [];
  var activeCat = (data.categories || []).filter(function(c) { return c.active; })[0]
                  || (data.categories || [])[0]
                  || { label: '' };
  var leftCol = htmlEl('div', {
    style: {
      borderRight: '1px solid ' + p.inkDim,
      background: 'rgba(0,0,0,0.3)',
      overflow: 'hidden',
      display: 'flex', flexDirection: 'column',
    }
  }, [
    buildCategoryNav(p, data.categories, hooks),
    buildEntryList(p, entries, activeCat.label, hooks),
  ]);

  var centerCol = buildReadingPane(p, sel, hooks);
  var rightCol = buildCrossRefs(p, sel, hooks);

  var body = htmlEl('div', {
    style: {
      position: 'absolute', top: 60, left: 0, right: 0, bottom: 0,
      display: 'grid', gridTemplateColumns: '220px 1fr 280px',
    }
  }, [leftCol, centerCol, rightCol]);

  return htmlEl('div', {
    style: {
      position: 'relative', overflow: 'hidden',
      fontFamily: "'IBM Plex Mono', monospace",
      color: p.ink,
      width: hooks.width || '100%',
      height: hooks.height || '100%',
    }
  }, [topBar, body]);
}

// ════════════════════════════════════════════════════════════════════
// HOLOCRON — standalone container
// ════════════════════════════════════════════════════════════════════
function buildHolocron(p, hooks) {
  hooks = hooks || {};
  var width  = hooks.width  || 1280;
  var height = hooks.height || 920;
  return htmlEl('div', {
    'data-holocron-mode': 'standalone',
    style: {
      width: width, height: height, position: 'relative', overflow: 'hidden',
      background: 'linear-gradient(180deg, ' + p.skyDeep + ', #000)',
      border: '1px solid ' + p.inkDim,
      fontFamily: "'IBM Plex Mono', monospace",
      color: p.ink,
      boxShadow: 'inset 0 0 40px ' + p.skyDeep + ', 0 0 0 1px #000, 0 20px 50px rgba(0,0,0,0.7)',
    }
  }, [buildHolocronContent(p, hooks)]);
}

// ════════════════════════════════════════════════════════════════════
// HOLOCRON MODAL — popup with drag chrome + traffic-lights + backdrop
// (The drag logic — pointerdown/move/up — is wired through pointer
//  events on the chrome bar. Caller supplies `onClose` and may opt in
//  to `draggable: true`.)
// ════════════════════════════════════════════════════════════════════
function buildHolocronModal(p, hooks) {
  hooks = hooks || {};
  var width = hooks.width || 1080;
  var height = hooks.height || 720;
  var draggable = !!hooks.draggable;
  var onClose = hooks.onClose || null;

  // Drag state — closure variables on the modal element.
  var dragState = { active: false, x: 0, y: 0, baseX: 0, baseY: 0 };
  var offset = { x: 0, y: 0 };

  // Backdrop scrim
  var backdropProps = {
    'data-holocron-mode': 'modal',
    style: {
      position: 'absolute', inset: 0, zIndex: 200,
      display: 'flex', alignItems: 'center', justifyContent: 'center',
      background: 'rgba(0,0,0,0.45)',
      backdropFilter: 'blur(1px)',
      animation: 'holoFade 200ms ease-out',
    }
  };
  if (typeof onClose === 'function') {
    backdropProps.onClick = function(e) {
      if (e.target === backdrop) onClose();
    };
  }
  var backdrop = htmlEl('div', backdropProps, []);

  // Window wrapper
  var wrap = htmlEl('div', {
    style: {
      width: width, height: height,
      position: 'relative', overflow: 'hidden',
      transform: 'translate(0px, 0px)',
      background: 'linear-gradient(180deg, ' + p.skyDeep + ', #000)',
      border: '1px solid ' + p.amber,
      fontFamily: "'IBM Plex Mono', monospace",
      color: p.ink,
      boxShadow: '0 0 0 1px #000, 0 0 30px ' + p.amber + '55, 0 40px 80px rgba(0,0,0,0.85), inset 0 0 40px ' + p.skyDeep,
      animation: 'holoPop 220ms cubic-bezier(.4,.0,.2,1)',
    }
  }, []);
  wrap.addEventListener('click', function(e) { e.stopPropagation(); });

  // Drag handle bar (traffic lights + title + ESC hint)
  var redLight = htmlEl('div', {
    style: {
      width: 11, height: 11, borderRadius: '50%',
      background: p.red, cursor: 'pointer',
      boxShadow: '0 0 4px ' + p.red + '88, inset 0 -1px 1px rgba(0,0,0,0.4)',
    }
  });
  if (typeof onClose === 'function') {
    redLight.addEventListener('click', onClose);
  }
  var amberLight = htmlEl('div', {
    style: {
      width: 11, height: 11, borderRadius: '50%',
      background: p.amber, opacity: 0.65,
      boxShadow: 'inset 0 -1px 1px rgba(0,0,0,0.4)',
    }
  });
  var greenLight = htmlEl('div', {
    style: {
      width: 11, height: 11, borderRadius: '50%',
      background: p.green, opacity: 0.65,
      boxShadow: 'inset 0 -1px 1px rgba(0,0,0,0.4)',
    }
  });
  var trafficLights = htmlEl('div', {
    style: { display: 'flex', gap: 6, alignItems: 'center' }
  }, [redLight, amberLight, greenLight]);

  var titleLabel = htmlEl('div', {
    style: {
      position: 'absolute', left: '50%', transform: 'translateX(-50%)',
      fontSize: 9, letterSpacing: 3, color: p.amber, fontWeight: 600,
    }
  }, ['HOLOCRON']);

  var hint = htmlEl('div', {
    style: { marginLeft: 'auto', fontSize: 8, color: p.inkDim, letterSpacing: 1.5 }
  }, [(draggable ? '✥ DRAG' : '') + ' · ESC TO CLOSE']);

  var dragBar = htmlEl('div', {
    style: {
      position: 'absolute', top: 0, left: 0, right: 0, height: 22,
      zIndex: 5,
      background: 'linear-gradient(180deg, ' + p.amber + '33, transparent)',
      borderBottom: '1px solid ' + p.amber + '55',
      display: 'flex', alignItems: 'center', padding: '0 10px',
      cursor: draggable ? 'grab' : 'default',
      userSelect: 'none',
    }
  }, [trafficLights, titleLabel, hint]);

  // Drag handlers
  if (draggable) {
    dragBar.addEventListener('pointerdown', function(e) {
      dragState.active = true;
      dragState.x = e.clientX;
      dragState.y = e.clientY;
      dragState.baseX = offset.x;
      dragState.baseY = offset.y;
      try { dragBar.setPointerCapture(e.pointerId); } catch (err) {}
    });
    dragBar.addEventListener('pointermove', function(e) {
      if (!dragState.active) return;
      offset.x = dragState.baseX + (e.clientX - dragState.x);
      offset.y = dragState.baseY + (e.clientY - dragState.y);
      wrap.style.transform = 'translate(' + offset.x + 'px, ' + offset.y + 'px)';
    });
    function endDrag(e) {
      dragState.active = false;
      try { dragBar.releasePointerCapture(e.pointerId); } catch (err) {}
    }
    dragBar.addEventListener('pointerup', endDrag);
    dragBar.addEventListener('pointercancel', endDrag);
  }

  // Content area (below the drag bar)
  var contentArea = htmlEl('div', {
    style: { position: 'absolute', top: 22, left: 0, right: 0, bottom: 0 }
  }, [
    buildHolocronContent(p, {
      data: hooks.data,
      onCategoryClick: hooks.onCategoryClick,
      onEntryClick:    hooks.onEntryClick,
      onCrossRefClick: hooks.onCrossRefClick,
      onClose:         onClose,
      loreNouns:       hooks.loreNouns,
      width:  width,
      height: height - 22,
    }),
  ]);

  wrap.appendChild(dragBar);
  wrap.appendChild(contentArea);
  backdrop.appendChild(wrap);

  return backdrop;
}

// ─── exports ─────────────────────────────────────────────────────────
window.M3Holocron = {
  SCHEMA_VERSION: 1,

  // Wiring
  init: init,

  // Top-level
  buildHolocron:         buildHolocron,
  buildHolocronModal:    buildHolocronModal,
  buildHolocronContent:  buildHolocronContent,

  // Sub-builders
  buildCategoryNav:      buildCategoryNav,
  buildEntryList:        buildEntryList,
  buildReadingPane:      buildReadingPane,
  buildCrossRefs:        buildCrossRefs,

  // Helpers
  buildSubHead:          buildSubHead,
  buildKnowledgeRow:     buildKnowledgeRow,
  highlightLore:         highlightLore,

  // Fixtures
  HOLOCRON_DATA_FIXTURE: HOLOCRON_DATA_FIXTURE,
  HOLOCRON_LORE_NOUNS:   HOLOCRON_LORE_NOUNS,

  // Test reach
  _internal: {
    _htmlEl: htmlEl,
    _svgEl:  svgEl,
  },
};

})();
