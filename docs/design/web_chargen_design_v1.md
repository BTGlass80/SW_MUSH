# Web Character Creation — Design Document v1
## SW_MUSH Tier 3 Feature #20

**Date:** April 15, 2026  
**Author:** Claude (Opus)  
**Estimated Effort:** 20-30 hours across 8 drops  
**Priority:** Tier 3 — Primary acquisition channel improvement

---

## 1. Problem Statement

Today, character creation requires a Telnet or WebSocket session. New players must connect, create an account via `create <user> <pass>`, then navigate a text-based wizard — a high-friction path that screens out casual players before they ever experience the game. AresMUSH demonstrated that web-based chargen dramatically increases player acquisition.

**Current flow:** Browser → client.html → WebSocket → login prompt → `create` command → guided wizard (7 steps, text I/O) → enter game.

**Target flow:** Browser → `/chargen` → visual form (species picker, attribute sliders, skill tree, background) → submit → account + character created → redirect to client.html with auto-login token.

---

## 2. Architecture Overview

### 2.1 New Components

```
server/api.py              — REST API endpoints (NEW, ~600 lines)
static/chargen.html        — Single-page chargen app (NEW, ~3,000 lines)
engine/chargen_validator.py — Server-side validation (NEW, ~250 lines)
```

### 2.2 Route Structure

All API routes mounted under `/api/` on the existing aiohttp server (port 8080). No new ports, no new processes.

| Method | Route | Auth | Purpose |
|--------|-------|------|---------|
| `GET` | `/chargen` | None | Serve chargen.html |
| `GET` | `/api/chargen/species` | None | List all species with attribute ranges |
| `GET` | `/api/chargen/species/{name}` | None | Full species detail (abilities, story factors) |
| `GET` | `/api/chargen/skills` | None | All skills grouped by attribute, with descriptions |
| `GET` | `/api/chargen/templates` | None | Template presets with allocations |
| `POST` | `/api/chargen/validate` | None | Validate a build without saving (returns errors) |
| `POST` | `/api/chargen/submit` | None | Create account + character atomically |
| `POST` | `/api/auth/login` | None | Authenticate, return session token |
| `GET` | `/api/auth/check` | Token | Verify token validity |

### 2.3 Authentication for Submit

The submit endpoint creates both an account and a character atomically. No pre-existing session required — this IS the registration flow.

A lightweight session token (signed, expiring) is returned on successful submit. The chargen page stores it and redirects to `client.html?token=<t>`. The WebSocket handler checks for the token on connect, auto-authenticates, and skips the `connect <user> <pass>` prompt.

Token format: `base64(json({"account_id": N, "exp": unix_ts}))` + HMAC-SHA256 signature. Expires after 5 minutes (one-time use for auto-login). No persistent sessions — this is just a bridge from chargen to the game client.

### 2.4 Why Not WebSocket Chargen?

The existing wizard is deeply tied to sequential text I/O (`send_line` → `receive` → `send_line`). Bolting a JSON protocol onto that would require rewriting the wizard anyway. A REST API + static page is simpler, more testable, and more cache-friendly. The chargen page doesn't need real-time updates — it's a form.

---

## 3. Data Contracts

### 3.1 GET /api/chargen/species

```json
{
  "species": [
    {
      "name": "Human",
      "description": "Humans are the galaxy's most numerous...",
      "homeworld": "Various (Coruscant is the political center)",
      "attribute_dice": { "dice": 18, "pips": 0 },
      "skill_dice": { "dice": 7, "pips": 0 },
      "move": 10,
      "attributes": {
        "dexterity":  { "min": { "dice": 2, "pips": 0 }, "max": { "dice": 4, "pips": 0 } },
        "knowledge":  { "min": { "dice": 2, "pips": 0 }, "max": { "dice": 4, "pips": 0 } },
        "mechanical": { "min": { "dice": 2, "pips": 0 }, "max": { "dice": 4, "pips": 0 } },
        "perception": { "min": { "dice": 2, "pips": 0 }, "max": { "dice": 4, "pips": 0 } },
        "strength":   { "min": { "dice": 2, "pips": 0 }, "max": { "dice": 4, "pips": 0 } },
        "technical":  { "min": { "dice": 2, "pips": 0 }, "max": { "dice": 4, "pips": 0 } }
      },
      "special_abilities": [
        { "name": "Berserker Rage", "description": "When a Wookiee becomes enraged..." }
      ],
      "story_factors": ["Wookiees cannot speak Basic..."]
    }
  ]
}
```

### 3.2 GET /api/chargen/skills

```json
{
  "attributes": {
    "dexterity": {
      "description": "Shooting, dodging, melee combat, reflexes.",
      "gameplay_note": "Dexterity is your combat attribute...",
      "skills": [
        {
          "name": "Blaster",
          "key": "blaster",
          "specializations": ["Heavy Blaster Pistol", "Blaster Rifle", "Hold-Out Blaster"],
          "description": "Covers all blaster-type weapons...",
          "game_use": "Primary ranged combat skill...",
          "tip": "Most common combat skill in the game."
        }
      ]
    }
  }
}
```

### 3.3 GET /api/chargen/templates

```json
{
  "templates": [
    {
      "key": "smuggler",
      "label": "Smuggler",
      "description": "Fast-talking pilots who live on the edge of the law. Balanced combat and piloting with social skills.",
      "species": "Human",
      "attributes": { "dexterity": "3D+1", "knowledge": "2D+1", ... },
      "skills": { "blaster": "1D+1", "dodge": "1D", ... },
      "playstyle": "Piloting, trading, social encounters, light combat"
    }
  ]
}
```

### 3.4 POST /api/chargen/validate

Request:
```json
{
  "species": "Human",
  "attributes": { "dexterity": "3D+1", "knowledge": "2D+1", ... },
  "skills": { "blaster": "1D+1", "dodge": "1D" }
}
```

Response:
```json
{
  "valid": false,
  "errors": [
    "Attribute points not fully spent (3 pips remaining)",
    "dexterity: 5D exceeds maximum 4D for Human"
  ]
}
```

### 3.5 POST /api/chargen/submit

Request:
```json
{
  "username": "kaelin",
  "password": "secretpass123",
  "character": {
    "name": "Kaelin Voss",
    "species": "Human",
    "attributes": { "dexterity": "3D+1", ... },
    "skills": { "blaster": "1D+1", ... },
    "force_sensitive": false,
    "background": "A former Imperial cadet who went AWOL..."
  }
}
```

Response (success):
```json
{
  "success": true,
  "character_id": 42,
  "token": "eyJ...signed...",
  "redirect": "/client.html?token=eyJ..."
}
```

Response (error):
```json
{
  "success": false,
  "errors": {
    "account": ["Username already taken"],
    "character": ["Name 'Han Solo' is already taken"],
    "validation": ["Skill points overspent by 3 pips"]
  }
}
```

---

## 4. Server-Side Validation (`engine/chargen_validator.py`)

The client does real-time validation for UX, but the server is authoritative. `chargen_validator.py` reuses existing `Species.validate_attributes()` and `CreationEngine._validate()` logic but operates on raw dicts rather than stateful objects.

```python
async def validate_chargen_submission(data: dict, species_reg, skill_reg) -> list[str]:
    """
    Validate a complete character creation submission.
    Returns list of error strings (empty = valid).
    
    Checks:
    1. Species exists
    2. Attribute pips sum to species total
    3. Each attribute within species min/max
    4. Skill pips don't exceed species skill_dice
    5. Each skill exists in registry
    6. Each skill bonus ≤ 2D (creation cap per R&E)
    7. Name length 2-30, no forbidden characters
    8. Force sensitive flag is boolean
    """
```

The `2D skill bonus cap` is a WEG R&E rule: at creation, no skill may have more than 2D added above its parent attribute. This is validated server-side even though the client enforces it too.

---

## 5. Web Client Design (`static/chargen.html`)

### 5.1 Page Structure

Single-page app, no framework, vanilla JS + CSS. Same design language as `client.html` (Share Tech Mono, Orbitron, dark sci-fi theme). No build step.

**Layout:** Full-viewport, centered content area (max-width 900px), step indicator at top, navigation buttons at bottom.

### 5.2 Steps (Visual Flow)

```
┌─────────────────────────────────────────────────┐
│  ★  STAR WARS D6 MUSH — CHARACTER CREATION      │
│  ─────────────────────────────────────────────── │
│  [1 Path] [2 Species] [3 Attrs] [4 Skills]      │
│  [5 Force] [6 Story] [7 Review] [8 Account]     │
└─────────────────────────────────────────────────┘
```

**Step 1 — Choose Your Path:**
- Template cards (7 templates) with icon, name, playstyle description, and "Choose" button
- "Build from Scratch" option that goes to Species step
- Template choice pre-fills species + attributes + some skills; player can still edit

**Step 2 — Species:**
- Species cards in a grid (9 species), each showing name, homeworld, key attribute range, abilities count
- Clicking a card expands it to show full description, attribute ranges, special abilities, story factors
- "Select" button on each card
- Scratch path only (template path skips this)

**Step 3 — Attributes:**
- Six attribute rows, each with:
  - Attribute name + short description
  - Current value display (e.g., "3D+1")
  - Min/Max range label (from species)
  - Stepper buttons (−pip, +pip) or a slider
  - Visual bar showing position within species range
- Remaining pips counter at top, color-coded (green when 0, amber when >0, red when negative)
- Tooltip explaining D6 dice pool notation on first visit

**Step 4 — Skills:**
- Grouped by parent attribute (6 collapsible sections)
- Each attribute section header shows attribute value for reference
- Skill rows: name, ▼ expand for description, stepper for bonus dice (0 to 2D cap)
- Total pool display: "Blaster: 3D+1 + 1D+1 = 4D+2"
- Remaining skill pips counter at top
- "Explain" expand shows game_use and tip from skill_descriptions.yaml
- Quick-filter search box at top of skills list

**Step 5 — Force Sensitivity:**
- Binary choice: "Yes, I am Force-sensitive" / "No"
- Explanation panel showing consequences:
  - Force-sensitive: start with 2 FP, gain access to Force powers (Control/Sense/Alter), must resist Dark Side temptation
  - Not Force-sensitive: start with 1 FP, can still spend Force Points for dramatic moments
- Flavor text for each option

**Step 6 — Name & Background:**
- Character name input (2-30 chars, live validation)
- Background textarea (optional, min 5 chars if provided)
- Availability check on name (hits server to verify uniqueness)

**Step 7 — Review:**
- Full character sheet rendering (matching the in-game format as closely as possible)
- All sections editable (click pencil icon → jump to that step)
- Final validation errors displayed if any
- "Everything looks good" green checkmark when valid

**Step 8 — Account & Submit:**
- Username input (3-20 chars)
- Password input (6+ chars, with strength indicator)
- Password confirmation
- Terms/rules checkbox (game rules acknowledgment)
- "Create Character & Enter the Galaxy" submit button
- On success: show confirmation, auto-redirect to client.html with token after 3 seconds

### 5.3 Responsive Design

- Desktop (>768px): Step content centered, attribute/skill rows in comfortable width
- Mobile (<768px): Full-width, stacked layout, touch-friendly stepper buttons (min 44px tap target)
- Step indicator becomes scrollable horizontal bar on mobile

### 5.4 Client-Side Validation

All D6 math runs client-side for instant feedback. The pip/dice conversion:
```javascript
function pipsToDice(pips) {
  return { dice: Math.floor(pips / 3), pips: pips % 3 };
}
function diceToPips(dice, pips) {
  return dice * 3 + pips;
}
function formatPool(totalPips) {
  const d = Math.floor(totalPips / 3);
  const p = totalPips % 3;
  return p > 0 ? `${d}D+${p}` : `${d}D`;
}
```

Validation mirrors `engine/chargen_validator.py`:
- Attribute pips must sum to species total (typically 54 for 18D)
- Each attribute within species min/max
- Skill bonus per skill ≤ 2D (6 pips)
- Total skill pips ≤ species skill_dice
- Name 2-30 chars
- One of the 9 registered species selected

### 5.5 Data Loading

On page load, fetch `/api/chargen/species`, `/api/chargen/skills`, `/api/chargen/templates` in parallel. Cache in JS variables. All subsequent interaction is local until submit.

---

## 6. Auto-Login Token Flow

### 6.1 Token Generation (server/api.py)

```python
import hashlib, hmac, json, time, base64, os

# Generated once on server startup, lives in memory
_TOKEN_SECRET = os.urandom(32)

def create_login_token(account_id: int, ttl: int = 300) -> str:
    payload = json.dumps({"aid": account_id, "exp": int(time.time()) + ttl})
    payload_b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    sig = hmac.new(_TOKEN_SECRET, payload_b64.encode(), hashlib.sha256).hexdigest()[:16]
    return f"{payload_b64}.{sig}"

def verify_login_token(token: str) -> Optional[int]:
    try:
        payload_b64, sig = token.rsplit(".", 1)
        expected = hmac.new(_TOKEN_SECRET, payload_b64.encode(), hashlib.sha256).hexdigest()[:16]
        if not hmac.compare_digest(sig, expected):
            return None
        payload = json.loads(base64.urlsafe_b64decode(payload_b64))
        if time.time() > payload["exp"]:
            return None
        return payload["aid"]
    except Exception:
        return None
```

### 6.2 WebSocket Auto-Login (server/web_client.py)

When `client.html?token=XXX` opens, the client sends `{"type": "token_auth", "token": "XXX"}` as its first WebSocket message. The server verifies the token, loads the account, and skips the login prompt — going straight to character select (which will find the just-created character and enter the game).

### 6.3 client.html Changes

Minimal: on load, check `URLSearchParams` for `token`. If present, send token_auth message on WSocket open instead of waiting for user to type `connect`. Remove token from URL bar via `history.replaceState`.

---

## 7. Security Considerations

| Concern | Mitigation |
|---------|-----------|
| Rate limiting | Submit endpoint: 3 requests/minute per IP (in-memory counter) |
| Password storage | bcrypt (existing `db.create_account()`) |
| SQL injection | Parameterized queries only (existing pattern) |
| XSS | No user content rendered without escaping; chargen page is static |
| Token replay | 5-minute expiry, HMAC-signed, server-secret rotates on restart |
| Name squatting | Unique constraint in DB (existing); submit is atomic |
| Brute-force accounts | Same lockout logic as Telnet login (5 failures → 5 min lockout) |
| Automated registration | Basic: require min password entropy; Future: CAPTCHA integration point |

---

## 8. Drop Plan

### Drop 1 — REST API Foundation (3-4 hrs)
- `server/api.py`: Route registration on existing aiohttp app
- Read-only endpoints: `/api/chargen/species`, `/api/chargen/skills`, `/api/chargen/templates`
- JSON serialization of SpeciesRegistry, SkillRegistry, TEMPLATES
- Unit test for each endpoint
- Wire into `server/web_client.py` startup

### Drop 2 — Server-Side Validation + Submit (3-4 hrs)
- `engine/chargen_validator.py`: Full validation function
- `POST /api/chargen/validate` endpoint
- `POST /api/chargen/submit` endpoint (create account + character atomically)
- Token generation and `/api/auth/login` + `/api/auth/check`
- Error response formatting
- Rate limiting middleware

### Drop 3 — Chargen Page: Shell + Steps 1-2 (3-4 hrs)
- `static/chargen.html`: Page shell, CSS, step navigation
- Step 1: Template/scratch path choice with template cards
- Step 2: Species selection grid with expand/detail
- Data loading from API + client-side state management
- Responsive layout foundation

### Drop 4 — Chargen Page: Steps 3-4 (4-5 hrs)
- Step 3: Attribute allocation with stepper controls and pip tracking
- Step 4: Skill selection with grouped lists, descriptions, bonus steppers
- Client-side D6 math (pip/dice conversion, range validation)
- Remaining pips counters with color coding
- Skill search/filter

### Drop 5 — Chargen Page: Steps 5-7 (3-4 hrs)
- Step 5: Force sensitivity choice
- Step 6: Name + background input with live validation
- Step 7: Review sheet rendering
- Name availability check (async fetch to server)
- Edit-from-review navigation (click → jump to step)

### Drop 6 — Chargen Page: Step 8 + Submit (3-4 hrs)
- Step 8: Account creation form
- Submit flow: client validation → server submit → success/error handling
- Token-based auto-redirect to client.html
- Error state UI (duplicate name, duplicate username, validation failures)
- Loading states and submit button disable during request

### Drop 7 — Auto-Login Integration (2-3 hrs)
- Token auth in WebSocket handler (`server/web_client.py`)
- `client.html` token detection + auto-auth message
- URL cleanup (remove token from address bar)
- Graceful fallback if token expired (show normal login prompt)
- End-to-end test: chargen → submit → auto-login → in-game

### Drop 8 — Polish & Edge Cases (2-3 hrs)
- Mobile responsive refinement
- Keyboard navigation (tab order, enter to advance)
- Animation/transitions between steps
- Browser back/forward button handling (history state per step)
- Error recovery (network failure during submit)
- Optional: "Save progress" to localStorage
- Link from client.html login screen to /chargen

---

## 9. Dual-Interface Principle

The Telnet creation wizard remains fully functional and unchanged. Web chargen is an alternative path that creates the same DB records. Both paths produce identical `Character.to_db_dict()` output. The server-side validator uses the same rules as `CreationEngine._validate()`.

Players who start on Telnet can still use the text wizard. Players who start on the web get the graphical flow. Both end up in the same game on the same server.

---

## 10. File Inventory (Final State)

| File | Lines (est.) | Status |
|------|-------------|--------|
| `server/api.py` | ~600 | NEW |
| `engine/chargen_validator.py` | ~250 | NEW |
| `static/chargen.html` | ~3,000 | NEW |
| `server/web_client.py` | ~180 (+40) | MODIFIED — API route registration, token auth |
| `static/client.html` | ~6,860 (+25) | MODIFIED — token auto-login |

**Total new code:** ~3,850 lines  
**Total modified:** ~65 lines  
**New DB tables:** None  
**Schema changes:** None  

---

## 11. Testing Plan

### Manual Testing Checklist

1. Load `/chargen` — verify all API data loads (species, skills, templates)
2. Template path: pick Smuggler → verify attributes + skills pre-filled → walk through to submit
3. Scratch path: pick Wookiee → verify attribute ranges adjust → allocate all pips → done
4. Over-allocate attributes → verify error shown, stepper blocked
5. Set 3D skill bonus → verify capped at 2D
6. Enter duplicate name → verify "name taken" error at review
7. Enter duplicate username → verify "username taken" error at submit
8. Submit successfully → verify redirect to client.html → verify auto-login → verify in tutorial Landing Pad
9. Token expired (wait 6 min) → verify graceful fallback to login prompt
10. Mobile: complete full flow on phone-width viewport
11. Telnet: verify existing wizard still works unchanged
12. Rate limit: submit 4 times rapidly → verify 4th is rejected

### Automated Tests (tests/test_chargen_api.py)

- Species list endpoint returns all 9 species
- Skills endpoint groups by 6 attributes
- Templates endpoint returns all 7 templates
- Validate endpoint catches: overspent attributes, invalid species, skill over cap
- Submit endpoint: success case creates account + character
- Submit endpoint: duplicate username returns error
- Submit endpoint: duplicate character name returns error
- Token generation + verification round-trip
- Token expiry check
- Rate limit enforcement

---

## 12. Design Decisions

**Why vanilla JS, no React?** Consistency with `client.html` (6,835 lines of vanilla JS). No build step. Single file. The chargen page is a form, not a real-time app — React would be overkill and introduce a build dependency.

**Why not use the existing CreationEngine on the server?** The engine is designed for sequential text I/O (each `process_input()` expects one command at a time). Web chargen submits the entire build at once. Reusing the validation logic (attribute ranges, pip totals) makes sense; reusing the interactive state machine doesn't.

**Why a separate page instead of a panel in client.html?** Chargen is a pre-authentication flow. The client.html is designed around an active WebSocket session. Mixing the two would complicate both. A clean `/chargen` entry point is more shareable (link it from a website, Discord, etc.).

**Why 8 steps and not fewer?** D6 character creation has real complexity — 6 attributes with species-specific ranges, ~75 skills grouped by attribute, Force sensitivity with gameplay consequences, and the account creation itself. Cramming this into 3 steps would overwhelm new players. 8 steps with clear navigation and back/forward lets players take it at their own pace.

**Why server-side validation when the client already validates?** Never trust the client. The server must be authoritative. A malicious user could POST directly to `/api/chargen/submit` with invalid data.

---

*End of design document.*
*Web chargen — Tier 3 Feature #20.*
*8 drops, ~24 hours estimated.*
