// hiris-chat-card.js — HA Lovelace custom card for HIRIS chat
// Served at: /local/hiris/hiris-chat-card.js (deployed automatically by add-on)
// Add to Lovelace resources if not auto-detected:
//   url: /local/hiris/hiris-chat-card.js
//   type: module
// Dashboard config:
//   type: custom:hiris-chat-card
//   agent_id: hiris-default
//   title: "Assistente Casa"
//   hiris_slug: hiris

const POLL_MS = 30_000;
const CHAT_TIMEOUT_MS = 30_000;
const HISTORY_MAX = 60;
const HISTORY_KEY_PREFIX = 'hiris.chat.';
const FONT_HREF = 'https://fonts.googleapis.com/css2?family=Geist:wght@300;400;500;600;700&family=Geist+Mono:wght@400;500&family=Inter+Tight:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600&display=swap';

// Inject the Google Fonts <link> at module load time, in the document head,
// so it's loaded once even if the user has multiple HIRIS cards on the same
// dashboard or opens the editor (was duplicated in HirisCard + Editor — L1).
(function injectFontOnce() {
  if (typeof document === 'undefined') return;
  if (document.querySelector('link[data-hiris-font]')) return;
  const l = document.createElement('link');
  l.rel = 'stylesheet';
  l.href = FONT_HREF;
  l.setAttribute('data-hiris-font', '1');
  (document.head || document.documentElement).appendChild(l);
})();

// Mini safe markdown parser (H5). Only handles inline **bold**, *italic*,
// `code`, and preserves newlines as <br>. Input is already HTML-escaped
// upstream so the regex sees < and > as &lt;/&gt; — no XSS surface.
function _renderMarkdown(escaped) {
  return escaped
    .replace(/`([^`\n]+)`/g, '<code class="md-code">$1</code>')
    .replace(/\*\*([^*\n]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
    .replace(/\n/g, '<br>');
}

// localStorage helpers for chat persistence (H1). Keyed by (slug, agent_id)
// so multiple cards/agents on the same dashboard don't collide.
function _historyKey(slug, agentId) {
  return HISTORY_KEY_PREFIX + (slug || 'hiris') + '.' + (agentId || 'default');
}

function _loadHistory(slug, agentId) {
  try {
    const raw = localStorage.getItem(_historyKey(slug, agentId));
    if (!raw) return [];
    const arr = JSON.parse(raw);
    return Array.isArray(arr) ? arr.slice(-HISTORY_MAX) : [];
  } catch { return []; }
}

function _saveHistory(slug, agentId, messages) {
  try {
    // Skip messages still streaming or in error transient state — only persist
    // settled bubbles. Drop any internal flags before writing.
    const clean = messages
      .filter(m => !m.streaming)
      .slice(-HISTORY_MAX)
      .map(m => ({ role: m.role, text: m.text }));
    localStorage.setItem(_historyKey(slug, agentId), JSON.stringify(clean));
  } catch { /* quota / private mode — silent */ }
}

function _clearHistory(slug, agentId) {
  try { localStorage.removeItem(_historyKey(slug, agentId)); } catch {}
}

// HIRIS SVG icon inlined as a data URI to avoid Shadow DOM ID conflicts
const _HIRIS_ICON_DATA = 'data:image/svg+xml,' + encodeURIComponent(
  '<svg xmlns="http://www.w3.org/2000/svg" viewBox="0 0 100 100">' +
  '<defs>' +
  '<radialGradient id="bg" cx="50%" cy="50%" r="50%">' +
  '<stop offset="0%" stop-color="#2a0a4e"/>' +
  '<stop offset="100%" stop-color="#0a0015"/>' +
  '</radialGradient>' +
  '<filter id="glow" x="-25%" y="-25%" width="150%" height="150%">' +
  '<feGaussianBlur in="SourceGraphic" stdDeviation="1.8" result="blur"/>' +
  '<feMerge><feMergeNode in="blur"/><feMergeNode in="SourceGraphic"/></feMerge>' +
  '</filter>' +
  '</defs>' +
  '<circle cx="50" cy="50" r="50" fill="url(#bg)"/>' +
  '<g transform="translate(50,50)" filter="url(#glow)">' +
  '<path d="M0 0 C-4.2 -9 -5.1 -31.2 0 -43 C5.1 -31.2 4.2 -9 0 0 Z" fill="#c084fc"/>' +
  '<path d="M0 0 C-4.2 -9 -5.1 -31.2 0 -43 C5.1 -31.2 4.2 -9 0 0 Z" fill="#818cf8" transform="rotate(60)"/>' +
  '<path d="M0 0 C-4.2 -9 -5.1 -31.2 0 -43 C5.1 -31.2 4.2 -9 0 0 Z" fill="#60a5fa" transform="rotate(120)"/>' +
  '<path d="M0 0 C-4.2 -9 -5.1 -31.2 0 -43 C5.1 -31.2 4.2 -9 0 0 Z" fill="#22d3ee" transform="rotate(180)"/>' +
  '<path d="M0 0 C-4.2 -9 -5.1 -31.2 0 -43 C5.1 -31.2 4.2 -9 0 0 Z" fill="#2dd4bf" transform="rotate(240)"/>' +
  '<path d="M0 0 C-4.2 -9 -5.1 -31.2 0 -43 C5.1 -31.2 4.2 -9 0 0 Z" fill="#e879f9" transform="rotate(300)"/>' +
  '</g>' +
  '<circle cx="50" cy="50" r="4.5" fill="white"/>' +
  '</svg>'
);

// Iris design tokens embedded for Shadow DOM.
// Prefixed --i- to avoid collisions with HA's own CSS variables.
const IRIS_CSS = `
  :host {
    --i-surface:     oklch(1.00 0 0);
    --i-surface-2:   oklch(0.97 0.008 280);
    --i-surface-3:   oklch(0.94 0.012 280);
    --i-hover:       oklch(0.95 0.015 280);
    --i-border:      oklch(0.91 0.012 280);
    --i-border-2:    oklch(0.86 0.018 280);
    --i-text:        oklch(0.22 0.02 280);
    --i-text-2:      oklch(0.45 0.015 280);
    --i-text-3:      oklch(0.62 0.012 280);
    --i-accent:      oklch(0.66 0.20 280);
    --i-accent-ink:  oklch(0.32 0.18 280);
    --i-accent-tint: oklch(0.96 0.04 280);
    --i-accent-tint-2: oklch(0.92 0.07 280);
    --i-on-accent:   oklch(0.99 0 0);
    --i-iris-glow:   oklch(0.78 0.17 280 / 0.18);
    --i-p-violet:    #8b5cf6;
    --i-p-fuchsia:   #c026d3;
    --i-ok:          oklch(0.70 0.16 155);
    --i-ok-tint:     oklch(0.95 0.05 155);
    --i-amber:       oklch(0.78 0.15 75);
    --i-err:         oklch(0.62 0.22 25);
    --i-err-tint:    oklch(0.95 0.05 25);
    --i-shadow-sm:   0 1px 2px oklch(0.20 0.05 280 / 0.06);
    --i-shadow:      0 4px 16px oklch(0.20 0.05 280 / 0.08);
    --i-r-sm:        6px;
    --i-r:           10px;
    --i-r-md:        14px;
    --i-font-sans:   "Geist", "Inter Tight", "Inter", system-ui, -apple-system, sans-serif;
    --i-font-mono:   "Geist Mono", "JetBrains Mono", "SF Mono", ui-monospace, monospace;
    display: block;
  }
  @media (prefers-color-scheme: dark) {
    :host {
      --i-surface:     oklch(0.205 0.022 280);
      --i-surface-2:   oklch(0.235 0.025 280);
      --i-surface-3:   oklch(0.275 0.028 280);
      --i-hover:       oklch(0.255 0.028 280);
      --i-border:      oklch(0.295 0.025 280);
      --i-border-2:    oklch(0.350 0.030 280);
      --i-text:        oklch(0.97 0.006 280);
      --i-text-2:      oklch(0.74 0.014 280);
      --i-text-3:      oklch(0.56 0.018 280);
      --i-accent:      oklch(0.78 0.17 280);
      --i-accent-ink:  oklch(0.86 0.14 280);
      --i-accent-tint: oklch(0.30 0.10 280);
      --i-accent-tint-2: oklch(0.36 0.12 280);
      --i-on-accent:   oklch(0.16 0.04 280);
      --i-iris-glow:   oklch(0.78 0.17 280 / 0.40);
      --i-p-violet:    #c084fc;
      --i-p-fuchsia:   #e879f9;
      --i-ok-tint:     oklch(0.30 0.08 155);
      --i-err-tint:    oklch(0.30 0.09 25);
      --i-shadow-sm:   0 1px 2px oklch(0 0 0 / 0.32);
      --i-shadow:      0 8px 24px oklch(0 0 0 / 0.32);
    }
  }
  *, *::before, *::after { box-sizing: border-box; }
`;

// Card stylesheet — module-level so it's parsed once and reused across all
// HIRIS card instances on the dashboard (L2: previously re-built on every
// _render via inline <style> blocks).
const CARD_CSS = `
  .card {
    background: var(--i-surface);
    border: 1px solid var(--i-border);
    border-radius: var(--i-r-md);
    overflow: hidden;
    box-shadow: var(--ha-card-box-shadow, var(--i-shadow-sm));
    font-family: var(--i-font-sans);
    font-size: 14px;
    color: var(--i-text);
    -webkit-font-smoothing: antialiased;
  }
  /* ── Header ── */
  .header {
    display: flex; align-items: center; justify-content: space-between;
    padding: 14px 16px;
    border-bottom: 1px solid var(--i-border);
    position: relative;
  }
  .header::before {
    content: ''; position: absolute; inset: 0;
    background: radial-gradient(ellipse 80% 100% at 0% 0%, var(--i-iris-glow), transparent 60%);
    pointer-events: none;
    border-radius: var(--i-r-md) var(--i-r-md) 0 0;
  }
  .header > * { position: relative; z-index: 1; }
  .header-left { display: flex; align-items: center; gap: 10px; min-width: 0; }
  .header-left img {
    filter: drop-shadow(0 0 10px var(--i-iris-glow));
    animation: iris-breathe 6s ease-in-out infinite;
  }
  @keyframes iris-breathe {
    0%, 100% { transform: scale(1); }
    50%      { transform: scale(1.04); }
  }
  @media (prefers-reduced-motion: reduce) {
    .header-left img,
    .typing-dot,
    .send.loading::after,
    .cursor { animation: none !important; }
  }
  .title {
    font-size: 14.5px; font-weight: 600; letter-spacing: -0.012em;
    color: var(--i-text); white-space: nowrap; overflow: hidden; text-overflow: ellipsis;
  }
  .header-right { display: flex; align-items: center; gap: 8px; flex-shrink: 0; }
  .status-pill {
    display: inline-flex; align-items: center; gap: 5px;
    padding: 3px 9px; border-radius: 999px;
    font-size: 10.5px; font-weight: 500;
    font-family: var(--i-font-mono);
    background: var(--i-ok-tint); color: var(--i-ok);
  }
  .status-pill::before {
    content: ""; width: 5px; height: 5px; border-radius: 50%; background: currentColor;
  }
  .status-pill.running  { background: var(--i-accent-tint); color: var(--i-accent-ink); }
  .status-pill.error,
  .status-pill.offline  { background: var(--i-err-tint); color: var(--i-err); }
  /* (H3) Toggle as proper switch — slider with track + thumb */
  .switch {
    --w: 36px; --h: 20px;
    width: var(--w); height: var(--h);
    border-radius: var(--h);
    background: var(--i-surface-3);
    border: 1px solid var(--i-border-2);
    padding: 0; cursor: pointer; position: relative;
    transition: background 0.18s, border-color 0.18s;
    flex-shrink: 0;
  }
  .switch:focus-visible {
    outline: 2px solid var(--i-accent);
    outline-offset: 2px;
  }
  .switch::after {
    content: ""; position: absolute;
    top: 1px; left: 1px;
    width: calc(var(--h) - 4px); height: calc(var(--h) - 4px);
    border-radius: 50%;
    background: var(--i-surface);
    box-shadow: 0 1px 3px rgba(0,0,0,0.18);
    transition: transform 0.18s;
  }
  .switch.on {
    background: var(--i-accent);
    border-color: var(--i-accent);
  }
  .switch.on::after { transform: translateX(calc(var(--w) - var(--h))); }
  /* ── Budget ── */
  .budget-wrap { padding: 6px 16px 2px; }
  .budget-bar {
    height: 3px; background: var(--i-surface-3);
    border-radius: 2px; overflow: hidden;
  }
  .budget-fill {
    height: 100%; background: var(--i-accent);
    border-radius: 2px; transition: width .4s, background-color .25s;
  }
  /* (H4) Threshold-aware budget colors */
  .budget-fill.ok   { background: var(--i-accent); }
  .budget-fill.mid  { background: var(--i-accent); }
  .budget-fill.warn { background: var(--i-amber, oklch(0.78 0.15 75)); }
  .budget-fill.crit { background: var(--i-err); }
  .budget-text {
    font-size: 10.5px; font-family: var(--i-font-mono);
    color: var(--i-text-3); margin-top: 4px;
    font-variant-numeric: tabular-nums;
    display: flex; justify-content: space-between; gap: 8px;
  }
  .budget-text .b-pct.warn { color: var(--i-amber, oklch(0.78 0.15 75)); }
  .budget-text .b-pct.crit { color: var(--i-err); font-weight: 600; }
  /* ── Error / disabled banner ── */
  .banner {
    padding: 6px 16px;
    font-size: 11.5px; font-family: var(--i-font-mono);
    border-bottom: 1px solid var(--i-border);
    text-align: center;
  }
  .banner.error { color: var(--i-err); background: var(--i-err-tint); }
  .banner.disabled { color: var(--i-text-3); background: var(--i-surface-2); }
  /* ── Messages ── */
  .messages {
    max-height: var(--hiris-h, 60vh);
    min-height: 180px;
    overflow-y: auto;
    padding: 12px 16px;
    display: flex; flex-direction: column; gap: 10px;
    background: var(--i-surface);
  }
  .messages::-webkit-scrollbar { width: 4px; }
  .messages::-webkit-scrollbar-track { background: transparent; }
  .messages::-webkit-scrollbar-thumb { background: var(--i-border); border-radius: 2px; }
  .empty {
    flex: 1; display: flex; flex-direction: column; align-items: center; justify-content: center;
    color: var(--i-text-3); font-size: 13px; text-align: center; padding: 20px 0; gap: 12px;
  }
  .empty-title { color: var(--i-text-2); font-size: 13.5px; }
  .suggestions { display: flex; flex-wrap: wrap; gap: 6px; justify-content: center; max-width: 90%; }
  .suggestion {
    border: 1px solid var(--i-border-2);
    background: var(--i-surface);
    color: var(--i-text-2);
    border-radius: 999px;
    font-size: 12px; padding: 4px 12px;
    cursor: pointer; font-family: var(--i-font-sans);
    transition: background 0.15s, border-color 0.15s, color 0.15s;
  }
  .suggestion:hover {
    background: var(--i-accent-tint);
    border-color: var(--i-accent);
    color: var(--i-accent-ink);
  }
  /* ── Bubbles ── */
  .msg-row { display: flex; gap: 8px; align-items: flex-start; }
  .msg-row.user { justify-content: flex-end; }
  .avatar { width: 26px; height: 26px; border-radius: 50%; flex-shrink: 0; overflow: hidden; }
  .avatar.invisible { visibility: hidden; }
  .msg-col { display: flex; flex-direction: column; max-width: 80%; }
  .msg-row.user .msg-col { align-items: flex-end; }
  .bubble {
    padding: 8px 12px;
    border-radius: var(--i-r-md);
    font-size: 13.5px; line-height: 1.5; word-break: break-word;
  }
  .msg-row.assistant .bubble {
    background: var(--i-surface);
    border: 1px solid var(--i-border);
    border-top-left-radius: 4px;
    color: var(--i-text);
  }
  .msg-row.assistant.grouped .bubble { border-top-left-radius: var(--i-r-md); }
  .msg-row.assistant.error .bubble {
    background: var(--i-err-tint); border-color: var(--i-err); color: var(--i-err);
  }
  .msg-row.user .bubble {
    background: var(--i-accent-tint);
    color: var(--i-text);
    border: 1px solid var(--i-accent-tint-2);
    border-top-right-radius: 4px;
  }
  .msg-row .bubble code.md-code {
    background: var(--i-surface-3); border-radius: 4px;
    padding: 1px 5px; font-family: var(--i-font-mono);
    font-size: 12.5px;
  }
  /* (M6) Hover actions on assistant bubbles */
  .msg-actions {
    display: flex; gap: 4px; margin-top: 4px;
    opacity: 0; transition: opacity 0.15s;
  }
  .msg-row.assistant:hover .msg-actions,
  .msg-row.assistant:focus-within .msg-actions { opacity: 1; }
  .msg-action {
    background: none; border: 1px solid transparent;
    padding: 2px 7px; border-radius: 999px;
    font-size: 11px; color: var(--i-text-3);
    cursor: pointer; font-family: var(--i-font-sans);
    transition: background 0.15s, color 0.15s, border-color 0.15s;
  }
  .msg-action:hover {
    background: var(--i-hover);
    color: var(--i-text);
    border-color: var(--i-border);
  }
  .msg-action.is-copied { color: var(--i-ok); border-color: var(--i-ok); }
  /* ── Typing indicator ── */
  .typing-row { display: flex; gap: 8px; align-items: flex-start; }
  .typing-bubble {
    display: inline-flex; gap: 4px; align-items: center;
    padding: 10px 14px;
    background: var(--i-surface);
    border: 1px solid var(--i-border);
    border-radius: var(--i-r-md); border-top-left-radius: 4px;
  }
  .typing-dot {
    width: 5px; height: 5px; border-radius: 50%;
    background: var(--i-text-3);
    animation: bounce 1.2s ease-in-out infinite;
  }
  .typing-dot:nth-child(2) { animation-delay: 0.15s; }
  .typing-dot:nth-child(3) { animation-delay: 0.30s; }
  @keyframes bounce {
    0%,60%,100% { transform: translateY(0); opacity: 0.4; }
    30%         { transform: translateY(-5px); opacity: 1; }
  }
  .cursor { animation: blink 1s step-start infinite; }
  @keyframes blink { 50% { opacity: 0; } }
  /* ── Composer ── */
  .input-row {
    padding: 8px 12px 12px;
    border-top: 1px solid var(--i-border);
    background: var(--i-surface);
  }
  .composer-tools {
    display: flex; justify-content: space-between; align-items: center;
    margin-bottom: 6px; gap: 8px; min-height: 18px;
  }
  .clear-btn {
    background: none; border: none; padding: 0;
    color: var(--i-text-3); font-size: 11px;
    cursor: pointer; font-family: var(--i-font-sans);
  }
  .clear-btn:hover { color: var(--i-text); text-decoration: underline; }
  .clear-btn[hidden] { display: none; }
  .input-inner {
    display: flex; align-items: flex-end; gap: 6px;
    background: var(--i-surface);
    border: 1px solid var(--i-border);
    border-radius: var(--i-r-md);
    padding: 5px 5px 5px 12px;
    transition: border-color 0.15s, box-shadow 0.15s;
  }
  .input-inner:focus-within {
    border-color: var(--i-accent);
    box-shadow: 0 0 0 3px var(--i-accent-tint);
  }
  /* (M1) Auto-grow textarea */
  .input {
    flex: 1; border: 0; background: transparent; outline: none;
    padding: 6px 0; font-size: 13.5px; line-height: 1.5;
    font-family: var(--i-font-sans); color: var(--i-text);
    resize: none; min-height: 22px; max-height: 132px;
    overflow-y: auto;
  }
  .input::placeholder { color: var(--i-text-3); }
  .input:disabled { opacity: 0.5; cursor: not-allowed; }
  .send {
    width: 32px; height: 32px; flex-shrink: 0;
    border-radius: 50%;
    background: linear-gradient(135deg, var(--i-p-violet), var(--i-p-fuchsia));
    color: white;
    border: none; cursor: pointer;
    display: grid; place-items: center;
    transition: transform 0.15s, box-shadow 0.15s;
    box-shadow: 0 4px 12px var(--i-iris-glow);
    align-self: flex-end; margin-bottom: 0;
  }
  .send:hover:not(:disabled) { transform: translateY(-1px); box-shadow: 0 6px 16px var(--i-iris-glow); }
  .send:active:not(:disabled) { transform: scale(0.92); }
  .send:disabled { background: var(--i-surface-3); color: var(--i-text-3); cursor: not-allowed; box-shadow: none; }
  .send.loading { background: var(--i-surface-3); cursor: default; box-shadow: none; }
  .send.loading svg { display: none; }
  .send.loading::after {
    content: ''; width: 12px; height: 12px;
    border: 2px solid var(--i-text-3); border-top-color: var(--i-accent);
    border-radius: 50%; animation: spin 0.7s linear infinite; display: block;
  }
  @keyframes spin { to { transform: rotate(360deg); } }
  /* ── Snackbar (M5 toggle undo) ── */
  .snack {
    position: absolute; left: 16px; right: 16px; bottom: 16px;
    display: none; align-items: center; justify-content: space-between;
    background: var(--i-text); color: var(--i-surface);
    padding: 8px 14px; border-radius: var(--i-r-sm);
    font-size: 12.5px; box-shadow: var(--i-shadow);
    transform: translateY(20px); opacity: 0;
    transition: opacity 0.18s, transform 0.18s;
    pointer-events: none;
    z-index: 10;
  }
  .snack.is-visible { display: flex; opacity: 1; transform: translateY(0); pointer-events: auto; }
  .snack-action {
    background: none; border: none; color: inherit;
    font-weight: 600; cursor: pointer;
    text-decoration: underline; padding: 0; margin-left: 12px;
    font-family: var(--i-font-sans); font-size: 12.5px;
  }
  /* ── Unconfigured state ── */
  .unconfigured {
    padding: 36px 20px;
    display: flex; flex-direction: column; align-items: center; gap: 10px;
    text-align: center;
  }
  .unc-title { font-size: 13px; font-weight: 600; color: var(--i-text); }
  .unc-sub { font-size: 12px; color: var(--i-text-3); line-height: 1.5; }
  /* ── Mobile portrait ── */
  @media (max-width: 360px) {
    .title { display: none; }
    .header { padding: 12px; }
    .input-row { padding: 8px; }
  }
`;

// ---------------------------------------------------------------------------
// Module-level ingress URL discovery
// ---------------------------------------------------------------------------
let _cachedIngressBase;

async function _discoverIngressBase(slug) {
  if (_cachedIngressBase !== undefined) return;
  _cachedIngressBase = null;
  try {
    const r = await fetch(`/local/${slug}/hiris-ingress.json`);
    if (r.ok) {
      const d = await r.json();
      const url = d?.ingress_url;
      if (typeof url === 'string' && url) {
        _cachedIngressBase = url.endsWith('/') ? url : url + '/';
      }
    }
  } catch {}
}

// ---------------------------------------------------------------------------
// HirisCard — main card element
// ---------------------------------------------------------------------------

class HirisCard extends HTMLElement {
  constructor() {
    super();
    this._shadow = this.attachShadow({ mode: 'open' });
    // Style block lives once in the shadow root (L2). Re-render only swaps
    // .innerHTML on _container — never re-parses the stylesheet.
    this._styleEl = document.createElement('style');
    this._styleEl.textContent = IRIS_CSS + CARD_CSS;
    this._shadow.appendChild(this._styleEl);
    this._container = document.createElement('div');
    this._shadow.appendChild(this._container);
    // Snackbar host (M5 toggle undo) — sits outside the regular render tree
    // so it's not blown away when _container.innerHTML is rewritten.
    this._snackEl = document.createElement('div');
    this._snackEl.className = 'snack';
    this._snackEl.setAttribute('role', 'status');
    this._snackEl.setAttribute('aria-live', 'polite');
    this._shadow.appendChild(this._snackEl);

    this._agentId = null;
    this._slug = 'hiris';
    this._title = 'HIRIS Chat';
    this._suggestions = null;
    this._heightCss = null;
    this._hass = null;
    this._status = 'idle';
    this._enabled = true;
    this._budgetEur = 0;
    this._budgetLimitEur = 0;
    this._messages = [];
    this._polling = null;
    this._loading = false;
    this._error = null;
    this._visibilityHandler = null;
    this._snackTimer = null;
    this._composerHeight = 0;
  }

  static getConfigElement() { return document.createElement('hiris-chat-card-editor'); }
  static getStubConfig() {
    return {
      agent_id: 'hiris-default',
      title: 'HIRIS Chat',
      hiris_slug: 'hiris',
      suggestions: [
        'Quali luci sono accese?',
        'Riassumi gli eventi di oggi',
        'Imposta scenario notte',
      ],
    };
  }

  setConfig(config) {
    const prevAgent = this._agentId;
    this._agentId = config.agent_id || null;
    this._slug = config.hiris_slug || 'hiris';
    this._title = config.title || 'HIRIS Chat';
    this._suggestions = Array.isArray(config.suggestions) && config.suggestions.length
      ? config.suggestions.slice(0, 6).map(String)
      : null;
    this._heightCss = config.height ? String(config.height) : null;
    // (H1) Hydrate persisted chat for this (slug, agent_id) — only when the
    // pair changes, so editing the title doesn't drop messages.
    if (this._agentId && this._agentId !== prevAgent) {
      this._messages = _loadHistory(this._slug, this._agentId);
    }
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    const statusKey = `sensor.hiris_${this._agentId}_status`;
    if (hass.states[statusKey]) {
      this._status = hass.states[statusKey].state || 'idle';
      const budgetKey = `sensor.hiris_${this._agentId}_budget_eur`;
      this._budgetEur = parseFloat(hass.states[budgetKey]?.state || '0');
      const switchKey = `switch.hiris_${this._agentId}_enabled`;
      this._enabled = hass.states[switchKey]?.state !== 'off';
      this._render();
    } else if (this._agentId && !this._polling) {
      this._startPolling();
    }
  }

  getCardSize() { return 6; }

  connectedCallback() {
    this._render();
    if (this._agentId && !this._polling) this._startPolling();
    // (H2) Pause polling when the dashboard tab is hidden — saves OpenRouter
    // :free quota and avoids waking sleeping HA instances. Resume + immediate
    // refresh on visible.
    if (typeof document !== 'undefined' && !this._visibilityHandler) {
      this._visibilityHandler = () => {
        if (document.hidden) {
          if (this._polling) { clearInterval(this._polling); this._polling = null; }
        } else if (this._agentId && !this._polling) {
          this._startPolling();
        }
      };
      document.addEventListener('visibilitychange', this._visibilityHandler);
    }
  }

  disconnectedCallback() {
    if (this._polling) { clearInterval(this._polling); this._polling = null; }
    if (this._visibilityHandler) {
      document.removeEventListener('visibilitychange', this._visibilityHandler);
      this._visibilityHandler = null;
    }
    if (this._snackTimer) { clearTimeout(this._snackTimer); this._snackTimer = null; }
  }

  _startPolling() {
    if (typeof document !== 'undefined' && document.hidden) return;
    this._fetchStatus();
    this._polling = setInterval(() => this._fetchStatus(), POLL_MS);
  }

  _hirisUrl(path) {
    const base = _cachedIngressBase
      ?? `${this._hass?.connection?.options?.hassUrl || ''}/api/hassio_ingress/${this._slug}/`;
    return `${base}${path}`;
  }

  _authToken() {
    const auth = this._hass?.connection?.options?.auth;
    return auth?.accessToken ?? auth?.data?.access_token ?? '';
  }

  async _fetchStatus() {
    if (!this._hass) return;
    await _discoverIngressBase(this._slug);
    try {
      const resp = await fetch(this._hirisUrl('api/agents'), {
        headers: { 'Authorization': `Bearer ${this._authToken()}` },
      });
      if (!resp.ok) {
        this._error = `⚠ HIRIS non disponibile (${resp.status})`;
      } else {
        const agents = await resp.json();
        const agent = Array.isArray(agents) && agents.find(a => a.id === this._agentId);
        if (agent) {
          this._status = agent.status || 'idle';
          this._enabled = !!agent.enabled;
          this._budgetEur = agent.budget_eur || 0;
          this._budgetLimitEur = agent.budget_limit_eur || 0;
          this._error = null;
        } else {
          this._error = 'Agente non configurato';
        }
      }
    } catch {
      this._error = '⚠ HIRIS non disponibile';
    }
    this._render();
  }

  async _sendMessage(text, opts) {
    opts = opts || {};
    if (!text.trim() || this._loading) return;
    this._loading = true;
    if (!opts.regen) {
      this._messages.push({ role: 'user', text });
    }
    const assistantMsg = { role: 'assistant', text: '', streaming: true };
    this._messages.push(assistantMsg);
    this._render();

    await _discoverIngressBase(this._slug);
    const controller = new AbortController();
    const timeout = setTimeout(() => controller.abort(), CHAT_TIMEOUT_MS);

    try {
      const resp = await fetch(this._hirisUrl('api/chat'), {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'Accept': 'text/event-stream',
          'Authorization': `Bearer ${this._authToken()}`,
          'X-Requested-With': 'fetch',
        },
        body: JSON.stringify({ message: text, agent_id: this._agentId, stream: true }),
        signal: controller.signal,
      });

      if (!resp.ok) {
        let msg = `HTTP ${resp.status}`;
        try { const d = await resp.json(); msg = d.error || msg; } catch {}
        throw new Error(msg);
      }

      const ct = resp.headers.get('Content-Type') || '';
      if (ct.includes('text/event-stream')) {
        const reader = resp.body.getReader();
        const dec = new TextDecoder();
        let buf = '';
        while (true) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += dec.decode(value, { stream: true });
          const lines = buf.split('\n');
          buf = lines.pop();
          for (const line of lines) {
            if (!line.startsWith('data: ')) continue;
            try {
              const evt = JSON.parse(line.slice(6));
              if (evt.type === 'token') { assistantMsg.text += evt.text; this._render(); }
              if (evt.type === 'discard_collected') { assistantMsg.text = ''; this._render(); }
              if (evt.type === 'done') { assistantMsg.streaming = false; }
              if (evt.type === 'error') {
                assistantMsg.text = `Errore: ${evt.message}`;
                assistantMsg.streaming = false;
              }
            } catch {}
          }
        }
        assistantMsg.streaming = false;
      } else {
        const data = await resp.json();
        assistantMsg.text = data.response || 'Nessuna risposta';
        assistantMsg.streaming = false;
      }
    } catch (e) {
      assistantMsg.text = e.name === 'AbortError'
        ? 'Timeout — riprova oppure usa il pulsante 🔄 sulla risposta'
        : `Errore: ${e.message}`;
      assistantMsg.streaming = false;
      assistantMsg.error = true;
    } finally {
      clearTimeout(timeout);
      this._loading = false;
      // Cap history in memory + persist (H1)
      if (this._messages.length > HISTORY_MAX) {
        this._messages.splice(0, this._messages.length - HISTORY_MAX);
      }
      if (this._agentId) _saveHistory(this._slug, this._agentId, this._messages);
      this._render();
      await this._fetchStatus();
    }
  }

  // (M6) Regenerate: drop the last assistant bubble and re-send the matching
  // user prompt. Used by the 🔄 action button on assistant bubbles.
  _regenerateAt(idx) {
    if (this._loading) return;
    // Walk back to find the user prompt that produced this assistant bubble.
    let userText = null;
    for (let i = idx - 1; i >= 0; i--) {
      if (this._messages[i].role === 'user') { userText = this._messages[i].text; break; }
    }
    if (!userText) return;
    // Drop the assistant message at idx (and any trailing bubbles after it).
    this._messages.splice(idx);
    this._sendMessage(userText, { regen: true });
  }

  _clearHistory() {
    this._messages = [];
    if (this._agentId) _clearHistory(this._slug, this._agentId);
    this._render();
  }

  async _toggleAgent(skipUndo) {
    if (!this._hass) return;
    const wasEnabled = this._enabled;
    // Optimistic UI: flip immediately so the switch feels responsive (M5).
    this._enabled = !wasEnabled;
    this._render();
    await _discoverIngressBase(this._slug);
    try {
      const resp = await fetch(this._hirisUrl(`api/agents/${this._agentId}`), {
        method: 'PUT',
        headers: {
          'Content-Type': 'application/json',
          'Authorization': `Bearer ${this._authToken()}`,
          'X-Requested-With': 'fetch',
        },
        body: JSON.stringify({ enabled: !wasEnabled }),
      });
      if (!resp.ok) {
        // Revert on server reject — keep the user from believing the change
        // landed when it didn't.
        this._enabled = wasEnabled;
        this._render();
        return;
      }
      if (!skipUndo) {
        const label = wasEnabled ? 'Agente disabilitato' : 'Agente abilitato';
        this._showSnack(label, 'Annulla', () => this._toggleAgent(true));
      }
      await this._fetchStatus();
    } catch (e) {
      console.error('HIRIS toggle error', e);
      this._enabled = wasEnabled;
      this._render();
    }
  }

  _showSnack(label, actionLabel, onAction) {
    if (!this._snackEl) return;
    if (this._snackTimer) clearTimeout(this._snackTimer);
    this._snackEl.innerHTML = `
      <span class="snack-label">${this._esc(label)}</span>
      ${actionLabel ? `<button class="snack-action" type="button">${this._esc(actionLabel)}</button>` : ''}
    `;
    this._snackEl.classList.add('is-visible');
    const btn = this._snackEl.querySelector('.snack-action');
    if (btn && onAction) {
      btn.onclick = () => {
        this._hideSnack();
        onAction();
      };
    }
    this._snackTimer = setTimeout(() => this._hideSnack(), 5000);
  }

  _hideSnack() {
    if (!this._snackEl) return;
    this._snackEl.classList.remove('is-visible');
    if (this._snackTimer) { clearTimeout(this._snackTimer); this._snackTimer = null; }
  }

  _iconHtml(size) {
    return `<img src="${_HIRIS_ICON_DATA}" width="${size}" height="${size}" style="border-radius:50%;display:block;flex-shrink:0" alt="HIRIS">`;
  }

  _esc(s) {
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  _statusClass() {
    return { idle: 'idle', running: 'running', error: 'error', unavailable: 'offline' }[this._status] ?? 'offline';
  }

  _statusLabel() {
    return { idle: 'pronto', running: 'in esecuzione', error: 'errore', unavailable: 'offline' }[this._status] ?? this._status;
  }

  _budgetClass(pct) {
    if (pct >= 95) return 'crit';
    if (pct >= 80) return 'warn';
    if (pct >= 50) return 'mid';
    return 'ok';
  }

  _render() {
    // Style is mounted once in the shadow root (constructor) — _render only
    // rewrites the body container. (L2)
    if (this._heightCss) {
      this._container.style.setProperty('--hiris-h', this._heightCss);
    }

    // Unconfigured state (L3 copy)
    if (!this._agentId) {
      this._container.innerHTML = `
        <div class="card">
          <div class="header">
            <div class="header-left">
              ${this._iconHtml(22)}
              <span class="title">${this._esc(this._title)}</span>
            </div>
          </div>
          <div class="unconfigured">
            <div style="opacity:.7">${this._iconHtml(38)}</div>
            <div>
              <div class="unc-title">Card non configurata</div>
              <div class="unc-sub">Apri il menu della card (… in alto a destra)<br>e seleziona <strong>Modifica</strong> per scegliere un agente.</div>
            </div>
          </div>
        </div>`;
      return;
    }

    const pct = this._budgetLimitEur > 0
      ? Math.min(100, (this._budgetEur / this._budgetLimitEur) * 100)
      : 0;
    const budgetCls = this._budgetClass(pct);

    const msgs = this._messages.map((m, i) => {
      const escaped = this._esc(m.text);
      const text = m.role === 'assistant' ? _renderMarkdown(escaped) : escaped.replace(/\n/g, '<br>');
      // (M2) Avatar grouping: hide avatar if previous bubble was also assistant
      const prev = this._messages[i - 1];
      const grouped = m.role === 'assistant' && prev && prev.role === 'assistant';
      if (m.role === 'user') {
        return `<div class="msg-row user">
          <div class="msg-col"><div class="bubble">${text}</div></div>
        </div>`;
      }
      if (m.streaming && !m.text) {
        return `<div class="typing-row" aria-label="L'agente sta rispondendo">
          <div class="avatar${grouped ? ' invisible' : ''}">${this._iconHtml(26)}</div>
          <div class="typing-bubble" aria-hidden="true">
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
            <div class="typing-dot"></div>
          </div>
        </div>`;
      }
      const errCls = m.error ? ' error' : '';
      const groupCls = grouped ? ' grouped' : '';
      // (M6) Copy + Regenerate actions on assistant bubbles, only when settled
      const actions = !m.streaming ? `
        <div class="msg-actions">
          <button class="msg-action js-copy" data-idx="${i}" aria-label="Copia risposta">📋 copia</button>
          <button class="msg-action js-regen" data-idx="${i}" aria-label="Rigenera risposta">🔄 rigenera</button>
        </div>` : '';
      return `<div class="msg-row assistant${errCls}${groupCls}">
        <div class="avatar${grouped ? ' invisible' : ''}">${this._iconHtml(26)}</div>
        <div class="msg-col">
          <div class="bubble">${text}${m.streaming ? '<span class="cursor">&#x258C;</span>' : ''}</div>
          ${actions}
        </div>
      </div>`;
    }).join('');

    const _savedInput = this._container.querySelector('#inp')?.value ?? '';
    const hasMessages = this._messages.length > 0;
    const showSuggestions = !hasMessages && this._suggestions && this._suggestions.length > 0;

    const placeholder = !this._enabled
      ? 'Agente disabilitato — riattivalo dallo switch ↑'
      : (this._loading ? 'Elaborazione…' : 'Scrivi un messaggio…');

    const emptyHtml = showSuggestions ? `
      <div class="empty">
        <span class="empty-title">Cosa posso fare per te?</span>
        <div class="suggestions">
          ${this._suggestions.map(s => `<button class="suggestion" type="button" data-sugg="${this._esc(s)}">${this._esc(s)}</button>`).join('')}
        </div>
      </div>
    ` : `<div class="empty">Scrivi un messaggio per iniziare…</div>`;

    this._container.innerHTML = `
      <div class="card">
        <div class="header">
          <div class="header-left">
            ${this._iconHtml(22)}
            <span class="title">${this._esc(this._title)}</span>
          </div>
          <div class="header-right">
            <div class="status-pill ${this._statusClass()}" role="status">${this._statusLabel()}</div>
            <button class="switch ${this._enabled ? 'on' : ''}" id="tog"
              role="switch" aria-checked="${this._enabled ? 'true' : 'false'}"
              aria-label="${this._enabled ? 'Disabilita agente' : 'Abilita agente'}"
              title="${this._enabled ? 'Disabilita agente' : 'Abilita agente'}"></button>
          </div>
        </div>
        ${this._budgetLimitEur > 0 ? `
          <div class="budget-wrap" role="meter"
              aria-valuemin="0" aria-valuemax="${this._budgetLimitEur.toFixed(2)}"
              aria-valuenow="${this._budgetEur.toFixed(2)}"
              aria-label="Budget agente">
            <div class="budget-bar"><div class="budget-fill ${budgetCls}" style="width:${pct.toFixed(1)}%"></div></div>
            <div class="budget-text">
              <span>&#x20AC;${this._budgetEur.toFixed(2)} / &#x20AC;${this._budgetLimitEur.toFixed(2)}</span>
              <span class="b-pct ${budgetCls}">${Math.round(pct)}%</span>
            </div>
          </div>
        ` : ''}
        ${this._error ? `<div class="banner error" role="alert">${this._esc(this._error)}</div>` : ''}
        ${!this._enabled && !this._error ? `<div class="banner disabled">Agente disabilitato. Le richieste sono in pausa.</div>` : ''}
        <div class="messages" id="msgs" role="log" aria-live="polite" aria-label="Cronologia messaggi">
          ${msgs || emptyHtml}
        </div>
        <div class="input-row">
          <div class="composer-tools">
            <button class="clear-btn" id="clr" type="button" ${hasMessages ? '' : 'hidden'}
              aria-label="Cancella conversazione">↺ pulisci conversazione</button>
            <span></span>
          </div>
          <div class="input-inner">
            <textarea class="input" id="inp" rows="1"
              placeholder="${this._esc(placeholder)}"
              aria-label="Messaggio per l'agente"
              ${!this._enabled ? 'disabled' : ''}></textarea>
            <button class="send${this._loading ? ' loading' : ''}" id="snd"
              ${this._loading || !this._enabled ? 'disabled' : ''}
              aria-label="${this._loading ? 'Elaborazione in corso' : 'Invia messaggio'}"
              title="${this._loading ? 'Elaborazione…' : 'Invia (Enter) — Shift+Enter per nuova riga'}">
              <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
                <path fill="currentColor" d="M2.01 21L23 12 2.01 3 2 10l15 2-15 2z"/>
              </svg>
            </button>
          </div>
        </div>
      </div>`;

    const inp = this._container.querySelector('#inp');
    const snd = this._container.querySelector('#snd');
    const tog = this._container.querySelector('#tog');
    const clr = this._container.querySelector('#clr');
    const msgsEl = this._container.querySelector('#msgs');

    if (inp) {
      inp.value = _savedInput;
      // (M1) Auto-grow: shrink to scrollHeight, capped via CSS max-height
      const autosize = () => {
        inp.style.height = 'auto';
        inp.style.height = Math.min(inp.scrollHeight, 132) + 'px';
      };
      inp.addEventListener('input', autosize);
      autosize();
    }
    if (msgsEl) msgsEl.scrollTop = msgsEl.scrollHeight;

    if (snd) snd.onclick = () => {
      const t = inp?.value.trim();
      if (t) { inp.value = ''; if (inp.style) inp.style.height = 'auto'; this._sendMessage(t); }
    };
    if (inp) inp.onkeydown = (e) => {
      // Enter sends; Shift+Enter or modifier inserts a newline (M1)
      if (e.key === 'Enter' && !e.shiftKey && !e.metaKey && !e.ctrlKey && !e.altKey) {
        e.preventDefault();
        snd?.click();
      }
    };
    if (tog) tog.onclick = () => this._toggleAgent();
    if (clr) clr.onclick = () => {
      if (typeof confirm === 'function' && !confirm('Cancellare la cronologia di questa conversazione?')) return;
      this._clearHistory();
    };

    // (M4) Suggestion chips on empty state
    this._container.querySelectorAll('.suggestion').forEach(btn => {
      btn.onclick = () => {
        const text = btn.getAttribute('data-sugg') || btn.textContent;
        this._sendMessage(text);
      };
    });

    // (M6) Copy / Regenerate handlers
    this._container.querySelectorAll('.js-copy').forEach(btn => {
      btn.onclick = () => {
        const idx = parseInt(btn.dataset.idx, 10);
        const m = this._messages[idx];
        if (!m) return;
        const txt = m.text || '';
        const done = () => {
          btn.classList.add('is-copied');
          const orig = btn.textContent;
          btn.textContent = '✓ copiato';
          setTimeout(() => {
            btn.classList.remove('is-copied');
            btn.textContent = orig;
          }, 1200);
        };
        if (navigator.clipboard?.writeText) {
          navigator.clipboard.writeText(txt).then(done, done);
        } else {
          // Fallback for older HA / file:// — selection-based copy
          const ta = document.createElement('textarea');
          ta.value = txt;
          this._shadow.appendChild(ta);
          ta.select();
          try { document.execCommand('copy'); } catch {}
          this._shadow.removeChild(ta);
          done();
        }
      };
    });
    this._container.querySelectorAll('.js-regen').forEach(btn => {
      btn.onclick = () => {
        const idx = parseInt(btn.dataset.idx, 10);
        if (!Number.isNaN(idx)) this._regenerateAt(idx);
      };
    });
  }
}

// ---------------------------------------------------------------------------
// HirisChatCardEditor — visual config editor shown in the HA card picker
// ---------------------------------------------------------------------------

class HirisChatCardEditor extends HTMLElement {
  constructor() {
    super();
    this._shadow = this.attachShadow({ mode: 'open' });
    // Font is injected at module-level (L1) — no per-instance <link>.
    this._container = document.createElement('div');
    this._shadow.appendChild(this._container);

    this._config = {};
    this._hass = null;
    this._agents = null;
  }

  connectedCallback() { this._render(); }

  setConfig(config) {
    this._config = { ...config };
    this._render();
  }

  set hass(hass) {
    this._hass = hass;
    if (this._agents === null) this._loadAgents();
  }

  async _loadAgents() {
    this._agents = 'loading';
    const slug = this._config.hiris_slug || 'hiris';
    await _discoverIngressBase(slug);
    const base = _cachedIngressBase
      ?? `${this._hass?.connection?.options?.hassUrl || ''}/api/hassio_ingress/${slug}/`;
    const auth = this._hass?.connection?.options?.auth;
    const token = auth?.accessToken ?? auth?.data?.access_token ?? '';
    try {
      const resp = await fetch(`${base}api/agents`, {
        headers: { 'Authorization': `Bearer ${token}` },
      });
      if (resp.ok) {
        const result = await resp.json();
        // Only chat-type agents are compatible with this card
        this._agents = Array.isArray(result) ? result.filter(a => a.type === 'chat') : [];
      } else {
        this._agents = 'error';
      }
    } catch {
      this._agents = 'error';
    }
    this._render();
  }

  _fireConfigChanged() {
    this.dispatchEvent(new CustomEvent('config-changed', {
      detail: { config: { ...this._config } },
      bubbles: true,
      composed: true,
    }));
  }

  _esc(s) {
    return String(s || '').replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  _render() {
    const agentId = this._config.agent_id || '';
    const title = this._config.title || 'HIRIS Chat';
    const suggestions = Array.isArray(this._config.suggestions)
      ? this._config.suggestions.join('\n') : '';
    const height = this._config.height || '';

    let agentField;
    if (this._agents === null || this._agents === 'loading') {
      agentField = `<div class="field-loading">Caricamento agenti…</div>`;
    } else if (this._agents === 'error' || this._agents.length === 0) {
      agentField = `<input id="agentInput" class="field-input" type="text"
        value="${this._esc(agentId)}" placeholder="es. hiris-default">`;
    } else {
      const options = this._agents.map(a => {
        const sel = a.id === agentId ? ' selected' : '';
        return `<option value="${this._esc(a.id)}"${sel}>${this._esc(a.name || a.id)} (${this._esc(a.id)})</option>`;
      }).join('');
      agentField = `<div class="select-wrap">
        <select id="agentSelect" class="field-select">
          ${options}
        </select>
        <span class="select-arrow">▾</span>
      </div>`;
    }

    this._container.innerHTML = `
      <style>
        ${IRIS_CSS}
        .editor {
          font-family: var(--i-font-sans);
          font-size: 13px;
          color: var(--i-text);
          -webkit-font-smoothing: antialiased;
        }
        .editor-header {
          display: flex; align-items: center; gap: 10px;
          padding-bottom: 14px;
          border-bottom: 1px solid var(--i-border);
          margin-bottom: 16px;
        }
        .editor-title { font-size: 14px; font-weight: 600; color: var(--i-text); }
        .editor-sub { font-size: 11px; color: var(--i-text-3); font-family: var(--i-font-mono); margin-top: 1px; }
        .field { margin-bottom: 14px; }
        .field-label {
          font-size: 11px; font-weight: 600; font-family: var(--i-font-mono);
          text-transform: uppercase; letter-spacing: 0.06em;
          color: var(--i-text-3); margin-bottom: 6px;
        }
        .field-hint { font-size: 11px; color: var(--i-text-3); margin-top: 4px; }
        .field-loading {
          padding: 9px 12px;
          background: var(--i-surface-2);
          border: 1px solid var(--i-border);
          border-radius: var(--i-r-sm);
          font-size: 12.5px; color: var(--i-text-3);
          font-family: var(--i-font-mono);
        }
        .field-input, .field-select {
          width: 100%;
          padding: 8px 12px;
          background: var(--i-surface);
          border: 1px solid var(--i-border);
          border-radius: var(--i-r-sm);
          font-size: 13px; font-family: var(--i-font-sans);
          color: var(--i-text);
          outline: none;
          transition: border-color 0.15s, box-shadow 0.15s;
          box-sizing: border-box;
          appearance: none;
        }
        .field-input:focus, .field-select:focus {
          border-color: var(--i-accent);
          box-shadow: 0 0 0 3px var(--i-accent-tint);
        }
        .select-wrap { position: relative; }
        .select-arrow {
          position: absolute; right: 10px; top: 50%; transform: translateY(-50%);
          pointer-events: none; color: var(--i-text-3); font-size: 11px;
        }
      </style>
      <div class="editor">
        <div class="editor-header">
          <img src="${_HIRIS_ICON_DATA}" width="30" height="30"
            style="border-radius:50%;flex-shrink:0" alt="HIRIS">
          <div>
            <div class="editor-title">HIRIS Chat</div>
            <div class="editor-sub">configurazione card</div>
          </div>
        </div>

        <div class="field">
          <div class="field-label">Agente</div>
          ${agentField}
          <div class="field-hint">Solo agenti di tipo Chat</div>
        </div>

        <div class="field">
          <div class="field-label">Titolo</div>
          <input id="titleInput" class="field-input" type="text"
            value="${this._esc(title)}" aria-label="Titolo della card">
          <div class="field-hint">Mostrato nell'intestazione della card</div>
        </div>

        <div class="field">
          <div class="field-label">Suggerimenti iniziali</div>
          <textarea id="suggInput" class="field-input" rows="3"
            placeholder="Una proposta per riga, max 6&#10;Es: Spegni le luci&#10;Consumi di oggi&#10;Riassumi gli eventi"
            aria-label="Suggerimenti iniziali, uno per riga">${this._esc(suggestions)}</textarea>
          <div class="field-hint">Chip cliccabili nello stato vuoto. Una proposta per riga, max 6.</div>
        </div>

        <div class="field">
          <div class="field-label">Altezza area chat</div>
          <input id="heightInput" class="field-input" type="text"
            value="${this._esc(height)}" placeholder="es. 320px o 60vh"
            aria-label="Altezza area messaggi">
          <div class="field-hint">Default: 60vh (responsive). Sovrascrivi per layout custom.</div>
        </div>
      </div>`;

    const agentSelect = this._container.querySelector('#agentSelect');
    const agentInput  = this._container.querySelector('#agentInput');
    const titleInput  = this._container.querySelector('#titleInput');
    const suggInput   = this._container.querySelector('#suggInput');
    const heightInput = this._container.querySelector('#heightInput');

    if (agentSelect) {
      agentSelect.onchange = (e) => {
        this._config = { ...this._config, agent_id: e.target.value };
        this._fireConfigChanged();
      };
    }
    if (agentInput) {
      agentInput.oninput = (e) => {
        this._config = { ...this._config, agent_id: e.target.value };
        this._fireConfigChanged();
      };
    }
    if (titleInput) {
      titleInput.oninput = (e) => {
        this._config = { ...this._config, title: e.target.value };
        this._fireConfigChanged();
      };
    }
    if (suggInput) {
      suggInput.oninput = (e) => {
        const lines = String(e.target.value || '')
          .split('\n').map(s => s.trim()).filter(Boolean).slice(0, 6);
        const next = { ...this._config };
        if (lines.length) next.suggestions = lines;
        else delete next.suggestions;
        this._config = next;
        this._fireConfigChanged();
      };
    }
    if (heightInput) {
      heightInput.oninput = (e) => {
        const v = String(e.target.value || '').trim();
        const next = { ...this._config };
        if (v) next.height = v;
        else delete next.height;
        this._config = next;
        this._fireConfigChanged();
      };
    }
  }
}

customElements.define('hiris-chat-card-editor', HirisChatCardEditor);
customElements.define('hiris-chat-card', HirisCard);

window.customCards = window.customCards || [];
window.customCards.push({
  type: 'hiris-chat-card',
  name: 'HIRIS Chat',
  description: 'Chat con il tuo assistente smart home HIRIS',
  preview: false,
});
