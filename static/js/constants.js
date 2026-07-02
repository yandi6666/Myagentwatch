/**
 * MyAgentWatch — Shared Constants
 * Single source of truth for all configuration values.
 */

const STATUS_COLORS = {
  active: '#22c55e', online: '#22c55e', working: '#3b82f6', idle: '#f59e0b',
  waiting: '#f59e0b', thinking: '#3b82f6', spawning: '#06b6d4',
  error: '#ef4444', failed: '#ef4444', blocked: '#f97316',
  offline: '#6b7280', unknown: '#6b7280',
};

const SEVERITY_ICONS = {
  info: 'fa-circle',
  warn: 'fa-triangle-exclamation',
  error: 'fa-circle-xmark',
  debug: 'fa-circle-dot',
  success: 'fa-circle-check',
};

const API_BASE = '/api';
const POLL_INTERVAL_MS = 2000;
const MAX_EVENTS = 100;
const MAX_LOG_LINES = 200;
