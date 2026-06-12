/* ============================================================================
   m3_inventory.js — Inventory panel (Webify Drop UI-4a)

   Renders the inventory_state push (engine/items.build_inventory_state) into a
   modal: equipped slots (left), carried list (right), and a footer that
   previews the stat DELTA of equipping the selected carried item — compared by
   D6 pips (1D = 3 pips), the engine's own ordering (engine/dice.total_pips).

   Real symbols / real verbs only:
     • equipped slot data comes from read_equipment; name/slot/value/stats from
       the weapon registry; condition/quality/crafter from the ItemInstance.
     • the only staged commands are the ones that EXIST at HEAD —
       weapon: `equip <name>` / `unequip`;  armor: `wear <name>` / `remove armor`;
       any item: `look <name>`.  There is no `drop`/`give` verb, so neither is
       offered.  State-changing actions are STAGED (the host fills the input),
       never auto-sent.
     • no container / carry-weight row (there is no encumbrance model at HEAD).

   Token-only: every colour resolves from client.html :root (--accent / --self
   / --warn / --dim / --text). Vanilla port of design_handoff_webify.
   ============================================================================ */
(function(){
'use strict';

// Module-held selection (carried item key) so the delta footer survives the
// per-open re-render without a stale DOM pointer.
var _selectedKey = null;

function el(tag, attrs, children){
  var n = document.createElement(tag);
  if (attrs){
    Object.keys(attrs).forEach(function(k){
      if (k === 'class') n.className = attrs[k];
      else if (k === 'text') n.textContent = attrs[k];
      else if (k === 'html') n.innerHTML = attrs[k];
      else if (k.slice(0,5) === 'data-') n.setAttribute(k, attrs[k]);
      else n[k] = attrs[k];
    });
  }
  (children || []).forEach(function(c){
    if (c == null) return;
    n.appendChild(typeof c === 'string' ? document.createTextNode(c) : c);
  });
  return n;
}

// ── D6 pips ─────────────────────────────────────────────────────────────────
// "4D" -> 12, "5D+2" -> 17, "1D+1" -> 4, "2" -> 2 (flat). Returns null when the
// value isn't an absolute dice/pip total (e.g. "STR+1D" — a relative base we
// can't compare without the wielder's STR), so the footer shows from→to with
// NO arrow rather than a misleading one.
function pipsOf(dice){
  if (dice == null) return null;
  var s = String(dice).trim().toUpperCase();
  var m = s.match(/^(\d+)D(?:\+(\d+))?$/);
  if (m) return parseInt(m[1],10)*3 + (m[2] ? parseInt(m[2],10) : 0);
  if (/^\d+$/.test(s)) return parseInt(s,10);
  return null;
}

// quality 0-100 → 5-pip gauge (50 ≈ 3 pips, the "average" mark).
function qualityPips(q){
  var n = Math.max(0, Math.min(5, Math.round((q || 0) / 20)));
  var wrap = el('span', { 'class': 'inv-quality', title: 'Quality ' + (q || 0) });
  for (var i = 0; i < 5; i++){
    wrap.appendChild(el('span', { 'class': 'inv-pip' + (i < n ? ' on' : '') }));
  }
  return wrap;
}

// condition 0..max → a 3px bar; green >66% / amber >33% / red.
function conditionBar(cond, max){
  max = max || 100;
  var pct = max > 0 ? Math.max(0, Math.min(100, Math.round(cond / max * 100))) : 0;
  var tier = pct > 66 ? 'ok' : (pct > 33 ? 'warn' : 'low');
  var bar = el('span', { 'class': 'inv-cond ' + tier,
                         title: 'Condition ' + cond + '/' + max });
  bar.appendChild(el('span', { 'class': 'inv-cond-fill', style: 'width:' + pct + '%' }));
  return bar;
}

function statChips(stats){
  var chips = el('span', { 'class': 'inv-statchips' });
  Object.keys(stats || {}).forEach(function(axis){
    chips.appendChild(el('span', { 'class': 'inv-statchip',
      text: STAT_LABEL[axis] ? (STAT_LABEL[axis] + ' ' + stats[axis]) : (axis + ' ' + stats[axis]) }));
  });
  return chips;
}

var STAT_LABEL = { damage: 'DMG', range: 'RNG', energy: 'EN', physical: 'PH',
                   dex_penalty: 'DEX' };

// Verb mapping — by SLOT, using only commands that exist at HEAD.
function equipVerb(slot){ return slot === 'armor' ? 'wear' : (slot === 'weapon' ? 'equip' : null); }
function unequipVerb(slot){ return slot === 'armor' ? 'remove armor' : (slot === 'weapon' ? 'unequip' : null); }

// ── equipped slot card ───────────────────────────────────────────────────────
function slotCard(slot, item, onCommand){
  var card = el('div', { 'class': 'inv-card', 'data-slot': slot });
  var label = slot === 'weapon' ? 'Weapon' : 'Armor';
  if (!item){
    card.classList.add('empty');
    card.appendChild(el('div', { 'class': 'inv-card-slot', text: label }));
    card.appendChild(el('div', { 'class': 'inv-empty-note', text: 'none' }));
    return card;
  }
  var top = el('div', { 'class': 'inv-card-top' }, [
    el('span', { 'class': 'inv-card-slot', text: label }),
    el('span', { 'class': 'inv-card-name', text: item.name })
  ]);
  if (item.experiment_count > 0){
    top.appendChild(el('span', { 'class': 'inv-mod', text: '[Modified \u00d7' + item.experiment_count + ']' }));
  }
  card.appendChild(top);
  card.appendChild(el('div', { 'class': 'inv-card-meta' }, [
    qualityPips(item.quality), conditionBar(item.condition, item.max_condition)
  ]));
  if (item.crafter){
    card.appendChild(el('div', { 'class': 'inv-crafter', text: 'crafted by ' + item.crafter }));
  }
  card.appendChild(statChips(item.stats));
  var uv = unequipVerb(slot);
  if (uv){
    var btn = el('button', { 'class': 'inv-btn ghost', type: 'button',
      text: slot === 'armor' ? 'REMOVE' : 'UNEQUIP' });
    btn.addEventListener('click', function(){ onCommand(uv); });
    card.appendChild(btn);
  }
  return card;
}

// ── carried row ───────────────────────────────────────────────────────────────
function carriedRow(item, onCommand, onSelect){
  var row = el('div', { 'class': 'inv-row' + (item.key === _selectedKey ? ' selected' : ''),
                        'data-key': item.key, 'data-slot': item.slot });
  var qty = item.quantity && item.quantity > 1 ? ' \u00d7' + item.quantity : '';
  var main = el('div', { 'class': 'inv-row-main' }, [
    el('span', { 'class': 'inv-row-name', text: item.name + qty }),
    item.slot && item.slot !== 'misc'
      ? el('span', { 'class': 'inv-slot-tag', text: item.slot }) : null
  ]);
  if (item.experiment_count > 0){
    main.appendChild(el('span', { 'class': 'inv-mod', text: '\u00d7' + item.experiment_count }));
  }
  row.appendChild(main);
  row.appendChild(el('div', { 'class': 'inv-row-meta' }, [
    qualityPips(item.quality), conditionBar(item.condition, item.max_condition)
  ]));
  var actions = el('div', { 'class': 'inv-row-actions' });
  var ev = equipVerb(item.slot);
  if (ev){
    var eb = el('button', { 'class': 'inv-btn', type: 'button',
      text: item.slot === 'armor' ? 'WEAR' : 'EQUIP' });
    eb.addEventListener('click', function(e){ e.stopPropagation(); onCommand(ev + ' ' + item.name); });
    actions.appendChild(eb);
  }
  var lb = el('button', { 'class': 'inv-btn ghost', type: 'button', text: 'LOOK' });
  lb.addEventListener('click', function(e){ e.stopPropagation(); onCommand('look ' + item.name); });
  actions.appendChild(lb);
  row.appendChild(actions);
  row.addEventListener('click', function(){ onSelect(item.key); });
  return row;
}

// ── delta footer ───────────────────────────────────────────────────────────────
function deltaFooter(data){
  var foot = el('div', { 'class': 'inv-delta' });
  var sel = (data.carried || []).filter(function(c){ return c.key === _selectedKey; })[0];
  if (!sel){
    foot.appendChild(el('div', { 'class': 'inv-delta-hint',
      text: 'Select a carried item to preview equipping it.' }));
    return foot;
  }
  var equipped = sel.slot === 'armor' ? (data.equipped && data.equipped.armor)
                                       : (data.equipped && data.equipped.weapon);
  foot.appendChild(el('div', { 'class': 'inv-delta-title',
    text: 'Equipping ' + sel.name + (equipped ? ' (replaces ' + equipped.name + ')' : '') + ':' }));
  if (sel.slot === 'misc'){
    foot.appendChild(el('div', { 'class': 'inv-delta-hint', text: 'Not an equippable item.' }));
    return foot;
  }
  var axes = {};
  Object.keys(sel.stats || {}).forEach(function(a){ axes[a] = 1; });
  if (equipped) Object.keys(equipped.stats || {}).forEach(function(a){ axes[a] = 1; });
  Object.keys(axes).forEach(function(axis){
    var toVal = (sel.stats || {})[axis];
    var fromVal = equipped ? (equipped.stats || {})[axis] : undefined;
    var fp = pipsOf(fromVal), tp = pipsOf(toVal);
    var arrow = '', cls = '';
    if (fp != null && tp != null){
      if (tp > fp){ arrow = '\u25b2'; cls = 'up'; }
      else if (tp < fp){ arrow = '\u25bc'; cls = 'down'; }
      else { arrow = '='; cls = 'eq'; }
    }
    foot.appendChild(el('div', { 'class': 'inv-delta-row ' + cls }, [
      el('span', { 'class': 'inv-delta-axis', text: STAT_LABEL[axis] || axis }),
      el('span', { 'class': 'inv-delta-from', text: fromVal == null ? '\u2014' : String(fromVal) }),
      el('span', { 'class': 'inv-delta-arrow', text: '\u2192' }),
      el('span', { 'class': 'inv-delta-to', text: toVal == null ? '\u2014' : String(toVal) }),
      arrow ? el('span', { 'class': 'inv-delta-mark ' + cls, text: arrow }) : null
    ]));
  });
  return foot;
}

// ── public render ───────────────────────────────────────────────────────────────
// container: DOM node to fill. data: inventory_state payload. onCommand(cmd):
// host callback (stages the command into the input). Returns container.
function render(container, data, onCommand){
  if (!container) return container;
  data = data || {};
  onCommand = onCommand || function(){};
  container.innerHTML = '';

  function rerender(){ render(container, data, onCommand); }
  function onSelect(key){ _selectedKey = (_selectedKey === key ? null : key); rerender(); }

  var eq = data.equipped || {};
  var carried = data.carried || [];

  var cols = el('div', { 'class': 'inv-cols' });

  var left = el('div', { 'class': 'inv-col inv-equipped' }, [
    el('div', { 'class': 'inv-col-h', text: 'Equipped' }),
    slotCard('weapon', eq.weapon, onCommand),
    slotCard('armor', eq.armor, onCommand)
  ]);

  var right = el('div', { 'class': 'inv-col inv-carried' });
  right.appendChild(el('div', { 'class': 'inv-col-h', text: 'Carried (' + carried.length + ')' }));
  if (carried.length === 0){
    right.appendChild(el('div', { 'class': 'inv-empty-note', text: 'Nothing carried.' }));
  } else {
    carried.forEach(function(it){ right.appendChild(carriedRow(it, onCommand, onSelect)); });
  }

  cols.appendChild(left);
  cols.appendChild(right);
  container.appendChild(cols);
  container.appendChild(deltaFooter(data));
  return container;
}

function resetSelection(){ _selectedKey = null; }

window.M3Inventory = { render: render, pipsOf: pipsOf, resetSelection: resetSelection };

})();
