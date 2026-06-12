/* ============================================================================
   m3_shop.js — Shop card (Webify Drop UI-4b)

   Renders the EXISTING shop_state push that parser/shop_commands already emits
   but the web client previously dropped on the floor (the handleShopState stub
   was empty). Two modes, exactly as produced:

     • mode 'browse'    — buyer view of the vendor droids in the room:
                          {focused_id, droids:[{id,name,desc,tier,placed,escrow,
                           item_count, inventory:[{slot,name,price,qty,quality,crafter}]}]}
     • mode 'dashboard' — owner view of their own droids:
                          {owner_name, total_escrow, droids:[{...,escrow,inventory,
                           sales:[{ts,item,qty,net,buyer}]}]}

   No engine change for browse/dashboard — a pure render of an already-public
   message. Real verbs only: the single staged action is BUY → `buy <slot>
   from <shop name>` (parser routes `buy <X> from <Y>` to
   _handle_buy_from_droid). Owner shop management (stock/price/collect escrow)
   stays in the text `+shop` flow, so the dashboard is display-only here.
   Haggling stays text.

   mode:'vendor' (SHIPPED — WEBIFY.commissary_vendor_mode drop 2026-06-12):
   the commissary fold-in. Staged action: `+commissary buy <key>`.
   Sellback is explicitly deferred (no sellback this drop).

   Token-only (reuses the shared .inv-modal chrome + inv-pip gauge); B3-clean.
   ============================================================================ */
(function(){
'use strict';

var _focusedId = null;   // client-side focus for the browse list (multi-droid)

function el(tag, attrs, children){
  var n = document.createElement(tag);
  if (attrs){
    Object.keys(attrs).forEach(function(k){
      if (k === 'class') n.className = attrs[k];
      else if (k === 'text') n.textContent = attrs[k];
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

// quality 0-100 → 5-pip gauge (50 ≈ 3); 0/absent → no gauge (NPC stock often
// has no quality). Shares the .inv-pip token styling.
function qualityPips(q){
  if (!q) return null;
  var n = Math.max(0, Math.min(5, Math.round(q / 20)));
  var wrap = el('span', { 'class': 'inv-quality', title: 'Quality ' + q });
  for (var i = 0; i < 5; i++){
    wrap.appendChild(el('span', { 'class': 'inv-pip' + (i < n ? ' on' : '') }));
  }
  return wrap;
}

function credits(n){ return (n || 0).toLocaleString() + ' cr'; }

// ── browse mode ───────────────────────────────────────────────────────────────
function itemRow(it, shopName, onCommand){
  var row = el('div', { 'class': 'shop-item' });
  var head = el('div', { 'class': 'shop-item-head' }, [
    el('span', { 'class': 'shop-item-slot', text: '#' + it.slot }),
    el('span', { 'class': 'shop-item-name', text: it.name + (it.qty > 1 ? ' \u00d7' + it.qty : '') }),
    el('span', { 'class': 'shop-item-price', text: credits(it.price) })
  ]);
  row.appendChild(head);
  var meta = el('div', { 'class': 'shop-item-meta' });
  var pips = qualityPips(it.quality);
  if (pips) meta.appendChild(pips);
  if (it.crafter) meta.appendChild(el('span', { 'class': 'inv-crafter', text: 'crafted by ' + it.crafter }));
  if (meta.childNodes.length) row.appendChild(meta);
  // The one real action: stage `buy <slot> from <shop name>`.
  var buy = el('button', { 'class': 'inv-btn', type: 'button', text: 'BUY' });
  buy.addEventListener('click', function(){ onCommand('buy ' + it.slot + ' from ' + shopName); });
  row.appendChild(buy);
  return row;
}

function renderBrowse(container, data, onCommand){
  var droids = data.droids || [];
  if (droids.length === 0){
    container.appendChild(el('div', { 'class': 'inv-empty-note',
      text: 'No vendor droids here. Explore the market districts to find player shops.' }));
    return;
  }
  // resolve focus: client-side pick → server focused_id → sole droid
  var focused = null, i;
  for (i = 0; i < droids.length; i++){
    if (_focusedId != null && droids[i].id === _focusedId) focused = droids[i];
  }
  if (!focused && data.focused_id != null){
    for (i = 0; i < droids.length; i++){ if (droids[i].id === data.focused_id) focused = droids[i]; }
  }
  if (!focused && droids.length === 1) focused = droids[0];

  function rerender(){ render(container, data, onCommand); }

  if (droids.length > 1){
    var list = el('div', { 'class': 'shop-picklist' });
    droids.forEach(function(d){
      var pick = el('button', {
        'class': 'shop-pick' + (focused && d.id === focused.id ? ' on' : ''),
        type: 'button' }, [
        el('span', { 'class': 'shop-pick-name', text: d.name }),
        el('span', { 'class': 'shop-pick-tier', text: d.tier }),
        el('span', { 'class': 'shop-pick-count', text: d.item_count + ' item' + (d.item_count === 1 ? '' : 's') })
      ]);
      pick.addEventListener('click', function(){ _focusedId = d.id; rerender(); });
      list.appendChild(pick);
    });
    container.appendChild(list);
  }

  if (!focused){
    container.appendChild(el('div', { 'class': 'inv-empty-note', text: 'Select a shop to view its stock.' }));
    return;
  }

  var detail = el('div', { 'class': 'shop-detail' });
  detail.appendChild(el('div', { 'class': 'shop-detail-name', text: focused.name }));
  if (focused.desc) detail.appendChild(el('div', { 'class': 'shop-detail-desc', text: focused.desc }));
  var inv = focused.inventory || [];
  if (inv.length === 0){
    detail.appendChild(el('div', { 'class': 'inv-empty-note', text: 'This shop has nothing in stock.' }));
  } else {
    inv.forEach(function(it){ detail.appendChild(itemRow(it, focused.name, onCommand)); });
  }
  container.appendChild(detail);
}

// ── dashboard mode (owner; display-only) ───────────────────────────────────────
function renderDashboard(container, data){
  var droids = data.droids || [];
  container.appendChild(el('div', { 'class': 'shop-dash-head' }, [
    el('span', { 'class': 'shop-dash-title', text: 'Your shops' }),
    el('span', { 'class': 'shop-dash-escrow', text: 'Escrow ' + credits(data.total_escrow) })
  ]));
  if (droids.length === 0){
    container.appendChild(el('div', { 'class': 'inv-empty-note',
      text: 'You own no vendor droids. `shop buy droid <tier>` to acquire one.' }));
    return;
  }
  droids.forEach(function(d){
    var card = el('div', { 'class': 'shop-dash-droid' });
    card.appendChild(el('div', { 'class': 'shop-dash-droid-head' }, [
      el('span', { 'class': 'shop-detail-name', text: d.name }),
      el('span', { 'class': 'shop-pick-tier', text: d.tier }),
      el('span', { 'class': d.placed ? 'shop-tag-placed' : 'shop-tag-unplaced',
                   text: d.placed ? 'placed' : 'unplaced' }),
      el('span', { 'class': 'shop-dash-escrow', text: credits(d.escrow) })
    ]));
    (d.inventory || []).forEach(function(it){
      card.appendChild(el('div', { 'class': 'shop-dash-line' }, [
        el('span', { 'class': 'shop-item-slot', text: '#' + it.slot }),
        el('span', { 'class': 'shop-item-name', text: it.name + (it.qty > 1 ? ' \u00d7' + it.qty : '') }),
        el('span', { 'class': 'shop-item-price', text: credits(it.price) })
      ]));
    });
    var sales = d.sales || [];
    if (sales.length){
      card.appendChild(el('div', { 'class': 'shop-sales-h', text: 'Recent sales' }));
      sales.forEach(function(s){
        card.appendChild(el('div', { 'class': 'shop-sale' }, [
          el('span', { 'class': 'shop-sale-ts', text: s.ts }),
          el('span', { 'class': 'shop-sale-item', text: s.item + (s.qty > 1 ? ' \u00d7' + s.qty : '') }),
          el('span', { 'class': 'shop-sale-net', text: '+' + credits(s.net) }),
          el('span', { 'class': 'shop-sale-buyer', text: s.buyer })
        ]));
      });
    }
    container.appendChild(card);
  });
}

// ── vendor mode (commissary — mode:'vendor', vendor_kind:'commissary') ────────
function vendorItemRow(item, onCommand){
  var row = el('div', { 'class': 'shop-item' });
  var head = el('div', { 'class': 'shop-item-head' }, [
    el('span', { 'class': 'shop-item-slot', text: item.slot }),
    el('span', { 'class': 'shop-item-name', text: item.name }),
    el('span', { 'class': 'shop-item-price', text: credits(item.cost) })
  ]);
  row.appendChild(head);
  if (item.desc){
    row.appendChild(el('div', { 'class': 'shop-item-meta' }, [
      el('span', { 'class': 'inv-crafter', text: item.desc })
    ]));
  }
  if (item.mark === 'buy'){
    // Affordable and rank-cleared: show a BUY button staging +commissary buy <key>.
    var btn = el('button', { 'class': 'inv-btn', type: 'button', text: 'BUY' });
    btn.addEventListener('click', function(){ onCommand('+commissary buy ' + item.key); });
    row.appendChild(btn);
  } else if (item.mark === 'rank'){
    // Rank-locked: greyed out indicator, no action.
    row.appendChild(el('span', { 'class': 'shop-tag-unplaced',
      text: 'rank ' + item.min_rank + ' required' }));
  } else {
    // 'short': can't afford; show disabled state.
    row.appendChild(el('span', { 'class': 'shop-tag-unplaced', text: 'short' }));
  }
  return row;
}

function renderVendor(container, data, onCommand){
  var fc = data.faction_code || 'faction';
  container.appendChild(el('div', { 'class': 'shop-dash-head' }, [
    el('span', { 'class': 'shop-dash-title',
      text: fc.charAt(0).toUpperCase() + fc.slice(1).replace(/_/g, ' ') + ' Commissary' }),
    el('span', { 'class': 'shop-dash-escrow', text: 'Balance ' + credits(data.balance) })
  ]));
  var items = data.items || [];
  if (items.length === 0){
    container.appendChild(el('div', { 'class': 'inv-empty-note',
      text: 'No commissary stock available.' }));
    return;
  }
  var detail = el('div', { 'class': 'shop-detail' });
  items.forEach(function(item){ detail.appendChild(vendorItemRow(item, onCommand)); });
  container.appendChild(detail);
}

// ── public render ───────────────────────────────────────────────────────────────
function render(container, data, onCommand){
  if (!container) return container;
  data = data || {};
  onCommand = onCommand || function(){};
  container.innerHTML = '';
  if (data.mode === 'dashboard') renderDashboard(container, data);
  else if (data.mode === 'vendor') renderVendor(container, data, onCommand);
  else renderBrowse(container, data, onCommand);
  return container;
}

function resetFocus(){ _focusedId = null; }
function titleFor(data){ return (data && data.mode === 'dashboard') ? 'Your Shops' : 'Shop'; }

window.M3Shop = { render: render, resetFocus: resetFocus, titleFor: titleFor };

})();
