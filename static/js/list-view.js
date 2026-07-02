/**
 * MyAgentWatch 2.0 — List View
 * Agents grouped by group_name, collapsible table with search and source filter.
 * Requires: util.js (loaded before)
 */

let _lastAgents = [];

function updateListView(agents) {
  if (!agents) return;
  _lastAgents = agents;
  _renderListView(agents);
  _populateSourceFilter(agents);
}

function _renderListView(agents) {
  if (!agents || agents.length === 0) return;
  const container = safeGet('list-view-inner');
  if (!container) return;

  // Apply search filter
  const query = (safeGet('list-search')?.value || '').toLowerCase().trim();
  const sourceFilter = safeGet('list-source-filter')?.value || '';

  var filtered = agents;
  if (query) {
    filtered = filtered.filter(function (a) {
      return (a.display_name || a.name || '').toLowerCase().indexOf(query) >= 0
        || (a.group_name || a.group || '').toLowerCase().indexOf(query) >= 0
        || (a.model_id || '').toLowerCase().indexOf(query) >= 0;
    });
  }
  if (sourceFilter) {
    filtered = filtered.filter(function (a) {
      return (a.id || '').indexOf(sourceFilter + ':') === 0;
    });
  }

  if (filtered.length === 0) {
    container.innerHTML = '<div style="text-align:center; padding:40px; color:var(--text-muted);"><i class="fa-solid fa-magnifying-glass"></i><div style="margin-top:8px;">没有匹配的 Agent</div></div>';
    return;
  }

  // Group agents
  const groups = {};
  filtered.forEach(a => {
    const g = a.group_name || a.group || '默认 (未配置)';
    if (!groups[g]) groups[g] = [];
    groups[g].push(a);
  });

  const groupNames = Object.keys(groups).sort((a, b) => {
    if (a.includes('默认')) return 1;
    if (b.includes('默认')) return -1;
    return a.localeCompare(b);
  });

  container.innerHTML = groupNames.map(g => {
    const list = groups[g];
    const gid = 'grp-' + g.replace(/\s+/g, '-');
    const rows = list.map(a => {
      const status = a.status || 'offline';
      const srcLabel = _sourceLabel(a.id);
      return `<tr class="${a.configured === false ? 'unconfigured' : ''}">
        <td><span class="ldot ${status}" title="${status}"></span></td>
        <td><strong>${esc(a.display_name || a.name)}</strong> ${srcLabel}</td>
        <td>${esc(a.model_id || '(未知)')}</td>
        <td style="font-family:var(--font-mono);">${formatNumber(a.tokens_total || 0)}</td>
        <td>${a.latency_ms ? (a.latency_ms >= 1000 ? (a.latency_ms / 1000).toFixed(1) + 's' : a.latency_ms + 'ms') : '-'}</td>
        <td>$${(a.cost || 0).toFixed(2)}</td>
        <td style="color:var(--text-muted);">${formatTimestamp(a.last_seen_time)}</td>
      </tr>`;
    }).join('');

    return `<div class="list-group">
      <div class="list-group-header" onclick="toggleListGroup('${gid}')">
        <i class="fa-solid fa-chevron-down" id="${gid}-icon"></i>
        ${esc(g)}
        <span class="list-group-count">${list.length} Agent</span>
      </div>
      <div class="list-group-body" id="${gid}">
        <table class="list-table">
          <thead><tr>
            <th>状态</th><th>Agent</th><th>模型</th><th>Token</th><th>延迟</th><th>成本</th><th>活跃</th>
          </tr></thead>
          <tbody>${rows}</tbody>
        </table>
      </div>
    </div>`;
  }).join('');
}

function _sourceLabel(agentId) {
  if (!agentId) return '';
  const idx = agentId.indexOf(':');
  if (idx < 0) return '';
  const src = agentId.substring(0, idx);
  const labels = { 'main-opencode': 'OpenCode', 'claude-code': 'Claude', 'system': 'System' };
  const display = labels[src] || src;
  return '<span class="src-tag" data-src="' + esc(display) + '">' + esc(display) + '</span>';
}

function _populateSourceFilter(agents) {
  const sel = safeGet('list-source-filter');
  if (!sel) return;
  const sources = new Set();
  agents.forEach(a => {
    const idx = (a.id || '').indexOf(':');
    if (idx >= 0) sources.add(a.id.substring(0, idx));
  });
  sel.innerHTML = '<option value="">全部来源</option>'
    + [...sources].sort().map(function (s) {
        var label = _sourceLabel(s + ':x');
        return '<option value="' + esc(s) + '">' + esc(label) + '</option>';
      }).join('');
}

// Re-render on search/filter change
document.addEventListener('DOMContentLoaded', function () {
  safeGet('list-search')?.addEventListener('input', function () {
    _renderListView(_lastAgents);
  });
  safeGet('list-source-filter')?.addEventListener('change', function () {
    _renderListView(_lastAgents);
  });
});

function toggleListGroup(gid) {
  const body = document.getElementById(gid);
  const icon = document.getElementById(gid + '-icon');
  const header = body?.previousElementSibling;
  if (!body) return;

  const collapsed = body.style.display === 'none';
  body.style.display = collapsed ? '' : 'none';
  if (icon) {
    icon.style.transform = collapsed ? 'rotate(0deg)' : 'rotate(-90deg)';
  }
  if (header) {
    header.classList.toggle('collapsed', !collapsed);
  }
}
