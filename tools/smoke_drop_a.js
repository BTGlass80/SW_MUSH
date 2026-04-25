// Drop A smoke tests — extract just the FK token block from script.js
// and exec it in a fresh context, then assert acceptance criteria.
const fs = require('fs');
const vm = require('vm');

const js = fs.readFileSync('script.js', 'utf8');

// Pull just the Drop A block (FIELD KIT TOKENS & HELPERS through STATE marker)
const m = js.match(/\/\/ ── FIELD KIT TOKENS & HELPERS ──[\s\S]*?\/\/ ── STATE ──/);
if (!m) { console.error('FAIL: Drop A block not found'); process.exit(1); }

// Strip the `window.*` lines for sandbox eval (we'll capture symbols separately)
const block = m[0]
  .replace(/^window\.\w+ = \w+;$/gm, '')
  .replace(/\/\/ ── STATE ──.*$/, '');

const sandbox = { window: {}, isFinite: isFinite, Number: Number, String: String };
vm.createContext(sandbox);
vm.runInContext(block, sandbox);

// Re-expose vars for testing (block's `var x = ...` creates them in sandbox global)
const { FK, WOUND_RUNGS, woundRung, woundColor, stunCap, CONDITION_COLORS, conditionColor } = sandbox;

const tests = [];
function test(name, cond, got, want) {
  tests.push({ name, pass: !!cond, got, want });
}

test('WOUND_RUNGS.length === 7',
  WOUND_RUNGS.length === 7, WOUND_RUNGS.length, 7);

test("woundRung(0).label === 'HEALTHY'",
  woundRung(0).label === 'HEALTHY', woundRung(0).label, 'HEALTHY');

test("woundRung(3).label === 'WOUNDED ×2'",
  woundRung(3).label === 'WOUNDED \u00d72', woundRung(3).label, 'WOUNDED ×2');

test("woundRung(6).label === 'DEAD'",
  woundRung(6).label === 'DEAD', woundRung(6).label, 'DEAD');

test('woundRung(99) falls back to HEALTHY',
  woundRung(99).label === 'HEALTHY', woundRung(99).label, 'HEALTHY');

test('woundColor("warn", "cockpit") === FK.cockAmber',
  woundColor('warn', 'cockpit') === FK.cockAmber, woundColor('warn','cockpit'), FK.cockAmber);

test('woundColor("hurt") === FK.padRed (default theme=pad)',
  woundColor('hurt') === FK.padRed, woundColor('hurt'), FK.padRed);

test('stunCap(4) === 4',
  stunCap(4) === 4, stunCap(4), 4);

test('stunCap(undefined) === 3 (fallback)',
  stunCap(undefined) === 3, stunCap(undefined), 3);

test('stunCap(0) === 3 (fallback for 0)',
  stunCap(0) === 3, stunCap(0), 3);

test('stunCap("5") === 5 (string coercion)',
  stunCap('5') === 5, stunCap('5'), 5);

test("conditionColor('Light Damage') === FK.cockGreen",
  conditionColor('Light Damage') === FK.cockGreen, conditionColor('Light Damage'), FK.cockGreen);

test("conditionColor('Critical Damage') === FK.cockRed",
  conditionColor('Critical Damage') === FK.cockRed, conditionColor('Critical Damage'), FK.cockRed);

test("conditionColor('LIGHT DAMAGE') normalizes to 'Light Damage' → cockGreen",
  conditionColor('LIGHT DAMAGE') === FK.cockGreen, conditionColor('LIGHT DAMAGE'), FK.cockGreen);

test("conditionColor(null) === FK.cockCyan (fallback)",
  conditionColor(null) === FK.cockCyan, conditionColor(null), FK.cockCyan);

test("conditionColor('Whatever') unknown → FK.cockCyan",
  conditionColor('Whatever') === FK.cockCyan, conditionColor('Whatever'), FK.cockCyan);

test("FK.padAmber matches CSS var --pad-amber (#ffc857)",
  FK.padAmber === '#ffc857', FK.padAmber, '#ffc857');

test("FK.cockCyan matches CSS var --cock-cyan (#6ee8ff)",
  FK.cockCyan === '#6ee8ff', FK.cockCyan, '#6ee8ff');

let pass = 0, fail = 0;
for (const t of tests) {
  const mark = t.pass ? '✅' : '❌';
  if (t.pass) pass++; else fail++;
  console.log(`${mark} ${t.name}`);
  if (!t.pass) console.log(`     got=${JSON.stringify(t.got)} want=${JSON.stringify(t.want)}`);
}
console.log(`\n${pass}/${tests.length} passing`);
process.exit(fail ? 1 : 0);
