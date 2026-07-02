/**
 * MyAgentWatch 2.0 — Toast Notification System
 * Slide-in notifications for connection status, alerts, errors.
 */

function showToast(msg, type = 'info', duration = 5000) {
  const container = document.getElementById('toast-container');
  if (!container) return;

  const colors = {
    info: 'var(--accent)',
    warn: 'var(--accent-yellow)',
    error: 'var(--accent-red)',
    success: 'var(--accent-green)',
  };

  const toast = document.createElement('div');
  toast.className = 'toast';
  toast.style.cssText = `
    padding: 10px 16px; margin-bottom: 8px;
    background: var(--bg-glass); backdrop-filter: blur(10px);
    border: 1px solid ${colors[type] || colors.info};
    border-radius: var(--radius-sm); color: var(--text-primary);
    font-size: 13px; display: flex; align-items: center; gap: 8px;
    animation: toast-in 0.3s ease; max-width: 360px;
  `;
  const icons = { info: 'fa-circle-info', warn: 'fa-triangle-exclamation', error: 'fa-circle-xmark', success: 'fa-circle-check' };
  toast.innerHTML = `<i class="fa-solid ${icons[type] || icons.info}" style="color:${colors[type] || colors.info}"></i><span>${esc(msg)}</span>`;
  container.appendChild(toast);

  setTimeout(() => {
    toast.style.animation = 'toast-out 0.3s ease forwards';
    setTimeout(() => toast.remove(), 300);
  }, duration);
}
