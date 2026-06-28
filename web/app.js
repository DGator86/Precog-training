/*
 * Atemporal ESP Trainer — browser edition.
 *
 * Mirrors the CLI protocol in esp_trainer.py:
 *  - A trial is opened with no target.
 *  - You lock a guess.
 *  - Only at reveal is the target generated, using crypto-strength randomness
 *    drawn AFTER the guess was locked. Nothing exists to peek at while open.
 *
 * Three modules share the protocol but differ in their target pool:
 *  - shapes:  10 symbols      (chance 10%)
 *  - numbers: 1..10           (chance 10%)
 *  - updown:  up / down       (chance 50%)
 *
 * State lives entirely in localStorage; there is no server. Each module keeps
 * its own independent history.
 */

"use strict";

/* ---------- module definitions ---------- */
// Each target: { value (stored/compared), glyph (big display), label (caption) }

const MODULES = {
  shapes: {
    id: "shapes",
    tab: "Shapes",
    title: "Shapes",
    storageKey: "esp_trainer.trials.v1",
    targets: [
      { value: "circle",    glyph: "⬤",  label: "circle" },
      { value: "square",    glyph: "◼",  label: "square" },
      { value: "triangle",  glyph: "▲",  label: "triangle" },
      { value: "star",      glyph: "★",  label: "star" },
      { value: "cross",     glyph: "✚",  label: "cross" },
      { value: "spiral",    glyph: "🌀", label: "spiral" },
      { value: "crescent",  glyph: "☾",  label: "crescent" },
      { value: "diamond",   glyph: "◆",  label: "diamond" },
      { value: "hexagon",   glyph: "⬡",  label: "hexagon" },
      { value: "wavy line", glyph: "〰", label: "wavy line" },
    ],
    layout: "grid",
  },
  numbers: {
    id: "numbers",
    tab: "Numbers",
    title: "Numbers 1–10",
    storageKey: "esp_trainer.trials.numbers.v1",
    targets: Array.from({ length: 10 }, (_, i) => ({
      value: String(i + 1),
      glyph: String(i + 1),
      label: "",
    })),
    layout: "grid",
  },
  updown: {
    id: "updown",
    tab: "Up / Down",
    title: "Up or Down",
    storageKey: "esp_trainer.trials.updown.v1",
    targets: [
      { value: "up",   glyph: "▲", label: "Up" },
      { value: "down", glyph: "▼", label: "Down" },
    ],
    layout: "pair",
  },
};

const ACTIVE_KEY = "esp_trainer.activeModule";

let activeId = localStorage.getItem(ACTIVE_KEY);
if (!MODULES[activeId]) activeId = "shapes";

function mod() {
  return MODULES[activeId];
}

function glyphFor(value) {
  const t = mod().targets.find((x) => x.value === value);
  return t ? t.glyph : "?";
}

/* ---------- storage (per module) ---------- */

function loadTrials() {
  try {
    const raw = localStorage.getItem(mod().storageKey);
    return raw ? JSON.parse(raw) : [];
  } catch {
    return [];
  }
}

function saveTrials(t) {
  localStorage.setItem(mod().storageKey, JSON.stringify(t));
}

let trials = loadTrials();

function nextId() {
  return trials.reduce((m, t) => Math.max(m, t.id), 0) + 1;
}

function openTrial() {
  // The single in-progress trial: created, possibly guessed, not yet revealed.
  return trials.find((t) => t.revealed_at == null) || null;
}

/* ---------- randomness ---------- */

// Unbiased pick of one target using the Web Crypto API (rejection sampling).
function secretTarget() {
  const pool = mod().targets;
  const n = pool.length;
  const limit = Math.floor(256 / n) * n; // largest multiple of n <= 256
  const buf = new Uint8Array(1);
  let r;
  do {
    crypto.getRandomValues(buf);
    r = buf[0];
  } while (r >= limit);
  return pool[r % n].value;
}

/* ---------- stats ---------- */

function logFactorial(n) {
  let s = 0;
  for (let i = 2; i <= n; i++) s += Math.log(i);
  return s;
}

function logChoose(n, k) {
  return logFactorial(n) - logFactorial(k) - logFactorial(n - k);
}

// P(X >= k) for X ~ Binomial(n, p), one-sided.
function binomialTail(k, n, p) {
  if (n <= 0) return NaN;
  k = Math.max(k, 0);
  let total = 0;
  for (let i = k; i <= n; i++) {
    total += Math.exp(logChoose(n, i) + i * Math.log(p) + (n - i) * Math.log(1 - p));
  }
  return Math.min(total, 1);
}

/* ---------- elements ---------- */

const tabsEl = document.getElementById("tabs");
const stageEl = document.getElementById("stage");
const statGridEl = document.getElementById("statGrid");
const interpEl = document.getElementById("interp");
const trialListEl = document.getElementById("trialList");

let countdownTimer = null;
function clearCountdown() {
  if (countdownTimer) {
    clearInterval(countdownTimer);
    countdownTimer = null;
  }
}

/* ---------- rendering ---------- */

function renderTabs() {
  tabsEl.innerHTML = Object.values(MODULES)
    .map(
      (m) =>
        `<button class="tab${m.id === activeId ? " active" : ""}" data-mod="${m.id}" type="button">${m.tab}</button>`
    )
    .join("");
  tabsEl.querySelectorAll(".tab").forEach((b) => {
    b.onclick = () => switchModule(b.dataset.mod);
  });
}

function pickerMarkup() {
  const cls = mod().layout === "pair" ? "symbol-grid pair" : "symbol-grid";
  const buttons = mod()
    .targets.map(
      (t) => `
      <button class="symbol" data-value="${t.value}" type="button">
        <span class="glyph">${t.glyph}</span>
        ${t.label ? `<span>${t.label}</span>` : ""}
      </button>`
    )
    .join("");
  return `<div class="${cls}" id="symGrid">${buttons}</div>`;
}

function renderStage() {
  clearCountdown();
  const trial = openTrial();

  if (!trial) {
    stageEl.innerHTML = `
      <h2>Ready for a trial</h2>
      <p class="sub">Start a new blinded trial. No target is chosen yet — it only comes into being when you reveal.</p>
      <div class="actions">
        <button class="btn primary" id="newBtn" type="button">Start new trial</button>
      </div>`;
    document.getElementById("newBtn").onclick = startTrial;
    return;
  }

  if (trial.guess == null) {
    stageEl.innerHTML = `
      <h2>Trial #${trial.id} — lock your perception</h2>
      <p class="sub">Pick the ${mod().layout === "pair" ? "direction" : "option"} you sense. Once locked it cannot be changed.</p>
      ${pickerMarkup()}
      <div class="actions">
        <button class="btn primary" id="lockBtn" type="button" disabled>Lock guess</button>
        <button class="btn ghost" id="discardBtn" type="button">Discard</button>
      </div>`;

    let picked = null;
    const grid = document.getElementById("symGrid");
    const lockBtn = document.getElementById("lockBtn");
    grid.querySelectorAll(".symbol").forEach((b) => {
      b.onclick = () => {
        picked = b.dataset.value;
        grid.querySelectorAll(".symbol").forEach((x) => x.classList.remove("selected"));
        b.classList.add("selected");
        lockBtn.disabled = false;
      };
    });
    lockBtn.onclick = () => picked != null && lockGuess(picked);
    document.getElementById("discardBtn").onclick = discardTrial;
    return;
  }

  // Guess locked — show reveal gate.
  const now = Date.now();
  const ready = now >= trial.reveal_after;
  stageEl.innerHTML = `
    <h2>Trial #${trial.id} — guess locked</h2>
    <p class="sub">Your perception is sealed. Reveal generates the target with fresh randomness.</p>
    <div class="locked-note">
      <span class="glyph" style="font-size:1.4rem">${glyphFor(trial.guess)}</span>
      <span>Locked guess: <strong>${trial.guess}</strong></span>
    </div>
    <div class="actions">
      <button class="btn primary" id="revealBtn" type="button" ${ready ? "" : "disabled"}>
        ${ready ? "Reveal target" : 'Reveal at <span class="countdown" id="cd"></span>'}
      </button>
      <button class="btn ghost" id="discardBtn" type="button">Discard</button>
    </div>`;

  document.getElementById("discardBtn").onclick = discardTrial;
  const revealBtn = document.getElementById("revealBtn");

  if (ready) {
    revealBtn.onclick = () => revealTrial(trial.id);
  } else {
    const cd = document.getElementById("cd");
    const tick = () => {
      const rem = trial.reveal_after - Date.now();
      if (rem <= 0) {
        renderStage();
        return;
      }
      cd.textContent = formatRemaining(rem);
    };
    tick();
    countdownTimer = setInterval(tick, 1000);
  }
}

function formatRemaining(ms) {
  const s = Math.ceil(ms / 1000);
  const h = Math.floor(s / 3600);
  const m = Math.floor((s % 3600) / 60);
  const sec = s % 60;
  const pad = (n) => String(n).padStart(2, "0");
  return h > 0 ? `${h}:${pad(m)}:${pad(sec)}` : `${m}:${pad(sec)}`;
}

function renderRevealResult(trial) {
  clearCountdown();
  const hit = trial.hit === 1;
  stageEl.innerHTML = `
    <h2>Trial #${trial.id} revealed</h2>
    <div class="reveal">
      <div class="slot">
        <div class="label">Your guess</div>
        <div class="glyph">${glyphFor(trial.guess)}</div>
        <div class="name">${trial.guess}</div>
      </div>
      <div class="slot">
        <div class="label">Target</div>
        <div class="glyph">${glyphFor(trial.target)}</div>
        <div class="name">${trial.target}</div>
      </div>
    </div>
    <div class="verdict ${hit ? "hit" : "miss"}">${hit ? "HIT" : "MISS"}</div>
    <div class="actions">
      <button class="btn primary" id="newBtn" type="button">Start new trial</button>
    </div>`;
  document.getElementById("newBtn").onclick = startTrial;
}

function renderStats() {
  const done = trials.filter((t) => t.revealed_at != null);
  const n = done.length;
  const hits = done.reduce((s, t) => s + (t.hit || 0), 0);
  const chance = 1 / mod().targets.length;
  const rate = n ? hits / n : 0;
  const expected = n * chance;
  const p = n ? binomialTail(hits, n, chance) : NaN;

  const cells = [
    { num: n, cap: "Trials" },
    { num: hits, cap: "Hits" },
    { num: n ? `${(rate * 100).toFixed(0)}%` : "—", cap: "Hit rate" },
    { num: n ? p.toFixed(3) : "—", cap: "p-value" },
  ];
  statGridEl.innerHTML = cells
    .map((c) => `<div class="stat"><div class="num">${c.num}</div><div class="cap">${c.cap}</div></div>`)
    .join("");

  if (!n) {
    interpEl.className = "interp";
    interpEl.textContent = `Chance is ${(chance * 100).toFixed(0)}% (1 of ${mod().targets.length}). No completed trials yet.`;
    return;
  }
  if (p < 0.05 && hits > expected) {
    interpEl.className = "interp above";
    interpEl.textContent = `Above chance at p < 0.05 (expected ~${expected.toFixed(1)} hits). Replicate before taking it seriously.`;
  } else {
    interpEl.className = "interp";
    interpEl.textContent = `Expected ~${expected.toFixed(1)} hits by chance. Not enough evidence of above-chance performance yet.`;
  }
}

function renderHistory() {
  const done = [...trials].filter((t) => t.revealed_at != null).reverse();
  if (!done.length) {
    trialListEl.innerHTML = `<li class="empty">No completed trials yet.</li>`;
    return;
  }
  trialListEl.innerHTML = done
    .map((t) => {
      const hit = t.hit === 1;
      const when = new Date(t.revealed_at).toLocaleString();
      return `
        <li>
          <span class="pill ${hit ? "hit" : "miss"}">${hit ? "HIT" : "MISS"}</span>
          <span>${glyphFor(t.guess)} ${t.guess} → ${glyphFor(t.target)} ${t.target}</span>
          <span class="meta">#${t.id} · ${when}</span>
        </li>`;
    })
    .join("");
}

function renderAll() {
  renderTabs();
  renderStage();
  renderStats();
  renderHistory();
}

/* ---------- actions ---------- */

function switchModule(id) {
  if (!MODULES[id] || id === activeId) return;
  activeId = id;
  localStorage.setItem(ACTIVE_KEY, id);
  trials = loadTrials();
  renderAll();
}

function startTrial() {
  // Default: revealable immediately. The protocol's integrity comes from
  // deferring target generation, not from an artificial wait.
  const now = Date.now();
  trials.push({
    id: nextId(),
    created_at: now,
    reveal_after: now,
    target: null,
    guess: null,
    guess_at: null,
    revealed_at: null,
    hit: null,
  });
  saveTrials(trials);
  renderAll();
}

function lockGuess(value) {
  const trial = openTrial();
  if (!trial || trial.guess != null) return;
  trial.guess = value;
  trial.guess_at = Date.now();
  saveTrials(trials);
  renderAll();
}

function revealTrial(id) {
  const trial = trials.find((t) => t.id === id);
  if (!trial || trial.guess == null || trial.revealed_at != null) return;
  // Target generated now, after the guess was locked.
  trial.target = secretTarget();
  trial.revealed_at = Date.now();
  trial.hit = trial.guess === trial.target ? 1 : 0;
  saveTrials(trials);
  renderRevealResult(trial);
  renderStats();
  renderHistory();
}

function discardTrial() {
  const trial = openTrial();
  if (!trial) return;
  trials = trials.filter((t) => t.id !== trial.id);
  saveTrials(trials);
  renderAll();
}

function exportJson() {
  const payload = { module: activeId, trials };
  const blob = new Blob([JSON.stringify(payload, null, 2)], { type: "application/json" });
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = `esp_trials_${activeId}.json`;
  a.click();
  URL.revokeObjectURL(url);
}

function resetAll() {
  if (!confirm(`Delete all ${mod().tab} trials from this browser? This cannot be undone.`)) return;
  trials = [];
  saveTrials(trials);
  renderAll();
}

document.getElementById("exportBtn").onclick = exportJson;
document.getElementById("resetBtn").onclick = resetAll;

renderAll();
