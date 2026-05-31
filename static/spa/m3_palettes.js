/* ============================================================================
   m3_palettes.js — per-planet visual identity for the SPA map.

   Drop 4.1a · Tier 1 #4 · ported from map_v3/palettes.jsx (May 26 2026).

   Each palette is a flat dict the composition engine substitutes as the
   active color scheme for an area. Derived from
   web_client_vision_and_protocol_v1_3.md §4.6 (palette + security duality).

   The prototype JSX shipped three palettes (tatooine, coruscant_under,
   nar_shaddaa). Ported here unchanged. Future planets/areas append new
   entries to PALETTES without touching consumer code.
   ============================================================================ */
(function(){
'use strict';

var PALETTES = {
  tatooine: {
    id: 'tatooine',
    label: 'TATOOINE',
    sub: 'Sand-bleached · twin-suns glare',
    // Substrate (the ground/sky)
    sky:        '#1d1308',
    skyDeep:    '#0c0703',
    ground:     '#b3853a',   // sun-bleached duracrete/sand
    groundDeep: '#6c4a1c',
    groundShadow: '#3c290e',
    // Cartography (the drawn lines and labels)
    ink:        '#ffd07a',   // primary "amber ink" used for outlines
    inkBright:  '#ffe9b8',
    inkDim:     '#a87a32',
    inkFaint:   '#6a4a1c',
    paper:      '#ffe9b8',   // light wash for building fills
    paperDark:  '#a06a2a',
    // Accents
    cyan:       '#8de7ff',   // player/PC accent
    red:        '#ff5a4a',   // hostile/red alert
    green:      '#7ce068',   // safe/secured
    amber:      '#ffa640',   // friendly/highlight
    gold:       '#ffd56e',   // legendary
    // Per-style fills (used by style primitives)
    fillDock:        '#b46a3a',
    fillCantina:     '#c98a48',
    fillCivic:       '#a07840',
    fillHousing:     '#c79a5a',
    fillVendor:      '#d4a060',
    fillIndustrial:  '#8a6630',
    fillHutt:        '#7a4a2a',
    fillLandmark:    '#e8b86a',
    // Atmosphere
    sunCount:   2,            // twin suns!
    shadowAngle: [110, 250],  // two shadow directions
    shadowOpacity: 0.32,
    ambient:    'radial-gradient(ellipse at 50% 30%, rgba(255,180,80,0.10), transparent 70%)',
    hazeColor:  'rgba(255,200,120,0.06)',
    grainColor: 'rgba(0,0,0,0.18)'
  },

  coruscant_under: {
    id: 'coruscant_under',
    label: 'CORUSCANT · UNDERWORLD',
    sub: 'Perpetual twilight · neon haze',
    sky:        '#150806',
    skyDeep:    '#080302',
    ground:     '#3a2018',
    groundDeep: '#1a0d0a',
    groundShadow: '#080403',
    ink:        '#ff8e5a',
    inkBright:  '#ffb893',
    inkDim:     '#a85a32',
    inkFaint:   '#5a2a1a',
    paper:      '#7a4030',
    paperDark:  '#3a1f15',
    cyan:       '#7ad9ff',
    red:        '#ff5a4a',
    green:      '#7ce068',
    amber:      '#ffa640',
    gold:       '#ffd56e',
    fillDock:        '#3a2820',
    fillCantina:     '#5a2a3a',     // neon-soaked cantina
    fillCivic:       '#2a3040',
    fillHousing:     '#3a2620',
    fillVendor:      '#5a3a20',
    fillIndustrial:  '#1a1612',
    fillHutt:        '#4a2030',
    fillLandmark:    '#6a3030',
    sunCount:   0,
    shadowAngle: [],
    shadowOpacity: 0,
    ambient:    'radial-gradient(ellipse at 60% 20%, rgba(255,120,60,0.10), transparent 55%), radial-gradient(ellipse at 20% 90%, rgba(180,40,80,0.10), transparent 55%)',
    hazeColor:  'rgba(255,80,120,0.04)',
    grainColor: 'rgba(0,0,0,0.25)'
  },

  nar_shaddaa: {
    id: 'nar_shaddaa',
    label: 'NAR SHADDAA',
    sub: 'Wet neon · magenta-cyan',
    sky:        '#0a0a18',
    skyDeep:    '#03030a',
    ground:     '#1a1828',
    groundDeep: '#0c0a18',
    groundShadow: '#030210',
    ink:        '#ff5cd0',
    inkBright:  '#ff9be0',
    inkDim:     '#a83880',
    inkFaint:   '#5a1840',
    paper:      '#3a1830',
    paperDark:  '#1a0818',
    cyan:       '#5ce0ff',
    red:        '#ff5a4a',
    green:      '#7ce068',
    amber:      '#ffc440',
    gold:       '#ffd56e',
    fillDock:        '#2a2840',
    fillCantina:     '#4a1840',
    fillCivic:       '#1a1840',
    fillHousing:     '#2a1838',
    fillVendor:      '#4a2848',
    fillIndustrial:  '#180a28',
    fillHutt:        '#3a1028',
    fillLandmark:    '#5a2050',
    sunCount:   0,
    shadowAngle: [],
    shadowOpacity: 0,
    ambient:    'radial-gradient(ellipse at 40% 30%, rgba(255,80,200,0.10), transparent 55%), radial-gradient(ellipse at 80% 70%, rgba(80,200,255,0.10), transparent 55%)',
    hazeColor:  'rgba(255,80,200,0.04)',
    grainColor: 'rgba(0,0,0,0.30)'
  }
};

// Lookup helper. Returns null on unknown planet rather than throwing —
// caller decides whether to fall back or error.
function getPalette(planetId) {
  return PALETTES[planetId] || null;
}

window.M3Palettes = {
  PALETTES: PALETTES,
  getPalette: getPalette
};

})();
