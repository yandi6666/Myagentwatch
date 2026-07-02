/**
 * MyAgentWatch — Shared Utilities
 * Must load before all other modules that depend on these functions.
 */

function formatNumber(n) {
  n = Number(n) || 0;
  if (n >= 1000000) return (n / 1000000).toFixed(1) + 'M';
  if (n >= 1000) return (n / 1000).toFixed(1) + 'K';
  return String(Math.round(n));
}

function formatTimestamp(ts) {
  if (!ts) return '-';
  try { return new Date(ts).toLocaleTimeString(); } catch (e) { return '-'; }
}

function esc(s) {
  s = String(s || '');
  return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
}

function safeGet(id) {
  return document.getElementById(id) || null;
}

function safeSet(id, text) {
  const el = safeGet(id);
  if (el) el.textContent = text;
}
