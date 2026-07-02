/**
 * MyAgentWatch — Event Stream Tab
 * Real-time SSE feed with grouped Agent filter, category checkboxes,
 * star system, error-only mode, and animated status dots.
 */
const EventStream = {
  _source: null,
  _events: [],
  _paused: false,
  _errorsOnly: false,
  _starredOnly: false,
  _selectedAgents: null,   // Set
  _starredAgents: null,    // Set
  _agentGroups: null,      // Map<groupName, agentId[]>
  _maxEvents: 500,

  // Agent color map (matches the mockup)
  _agentColors: {
    'Claude Code': '#3b82f6',
    'Claude Code Explore': '#8b5cf6',
    'Claude Code Plan': '#10b981',
    'Claude Code general-purpose': '#f59e0b',
  },

  init() {
    if (this._source && this._source.readyState === EventSource.OPEN) return;
    this._events = [];
    this._paused = false;
    this._errorsOnly = false;
    this._starredOnly = false;
    this._starredAgents = new Set(['Claude Code', 'Claude Code Explore']);
    this._selectedAgents = null; // lazy init
    this._agentGroups = null;
    this._connect();
    this._buildAgentDropdown();
    document.getElementById('ev-pause-btn') && (document.getElementById('ev-pause-btn').textContent = '⏸');
    document.getElementById('ev-count') && (document.getElementById('ev-count').textContent = '0');
    document.getElementById('ev-errors-btn') && (document.getElementById('ev-errors-btn').className = 'ev-btn');
    document.getElementById('ev-starred-btn') && (document.getElementById('ev-starred-btn').className = 'ev-btn');
  },

  teardown() {
    if (this._source) { this._source.close(); this._source = null; }
  },

  _connect() {
    if (this._source) this._source.close();
    this._source = new EventSource(API + '/events/stream');
    this._source.onopen = () => {};
    this._source.onerror = () => { this._source && this._source.close(); };
    this._source.addEventListener('activity', (e) => {
      try {
        var d = JSON.parse(e.data);
        if (d && d.data) this._addEvent(d.data);
      } catch(ex) {}
    });
  },

  _buildAgentDropdown() {
    var list = document.getElementById('ev-agent-list');
    if (!list) return;

    // Group agents from last known snapshot
    var groups = {};
    var snapshot = window.lastSnapshot;
    if (snapshot && snapshot.agents) {
      snapshot.agents.forEach(function(a) {
        var g = a.group_name || a.group || '默认';
        if (!groups[g]) groups[g] = [];
        if (groups[g].indexOf(a.name) === -1) groups[g].push(a.name);
      });
    }
    this._agentGroups = groups;
    if (this._selectedAgents === null) {
      this._selectedAgents = new Set();
      Object.values(groups).forEach(function(names) { names.forEach(function(n) { this._selectedAgents.add(n); }.bind(this)); }.bind(this));
    }

    var html = '<label class="ev-ag-item"><input type="checkbox" checked onchange="EventStream._toggleAllAgents(this.checked)"> 全部 Agent</label>';
    var groupIcons = {'Claude Code': '📁 AI编程助手', '默认': '📁 默认'};
    Object.keys(groups).forEach(function(g) {
      var gName = groupIcons[g] || ('📁 ' + g);
      html += '<div class="ev-ag-group">' + gName + '</div>';
      groups[g].forEach(function(name) {
        var color = EventStream._agentColors[name] || '#94a3b8';
        var starred = EventStream._starredAgents.has(name);
        html += '<label class="ev-ag-item" style="padding-left:20px;">' +
          '<input type="checkbox" class="ev-ag-cb" data-agent="' + esc(name) + '" ' + (EventStream._selectedAgents.has(name) ? 'checked' : '') + ' onchange="EventStream._toggleAgent(\'' + esc(name) + '\', this.checked)">' +
          '<span style="display:inline-block;width:8px;height:8px;border-radius:50%;background:' + color + ';margin-right:4px;"></span>' +
          esc(name) +
          '<i class="fa-solid ' + (starred ? 'fa-star' : 'fa-star-o') + '" style="margin-left:auto;color:' + (starred ? '#f59e0b' : '#64748b') + ';cursor:pointer;" onclick="event.stopPropagation();EventStream._toggleStar(\'' + esc(name) + '\')"></i>' +
          '</label>';
      });
    });
    list.innerHTML = html;
  },

  _toggleAllAgents(checked) {
    if (checked) {
      Object.values(this._agentGroups || {}).forEach(function(ns) { ns.forEach(function(n) { this._selectedAgents.add(n); }.bind(this)); }.bind(this));
    } else {
      this._selectedAgents.clear();
    }
    document.querySelectorAll('.ev-ag-cb').forEach(function(cb) { cb.checked = checked; });
    this._render();
  },

  _toggleAgent(name, checked) {
    if (checked) this._selectedAgents.add(name);
    else this._selectedAgents.delete(name);
    var allCbs = document.querySelectorAll('.ev-ag-cb');
    var allChecked = true;
    allCbs.forEach(function(cb) { if (!cb.checked) allChecked = false; });
    var allEl = document.querySelector('#ev-agent-list input[type=checkbox]');
    if (allEl) allEl.checked = allChecked;
    this._render();
  },

  _toggleStar(name) {
    if (this._starredAgents.has(name)) this._starredAgents.delete(name);
    else this._starredAgents.add(name);
    this._buildAgentDropdown();
    this._render();
  },

  _searchAgents() {
    var q = (document.getElementById('ev-agent-search')?.value || '').toLowerCase();
    document.querySelectorAll('.ev-ag-item').forEach(function(el) {
      var text = el.textContent.toLowerCase();
      el.style.display = !q || text.indexOf(q) !== -1 ? '' : 'none';
    });
    document.querySelectorAll('.ev-ag-group').forEach(function(el) {
      el.style.display = !q ? '' : 'none';
    });
  },

  _toggleAgentDropdown() {
    var dd = document.getElementById('ev-agent-dropdown');
    if (dd) dd.style.display = dd.style.display === 'none' ? '' : 'none';
  },

  _toggleErrorsOnly() {
    this._errorsOnly = !this._errorsOnly;
    var btn = document.getElementById('ev-errors-btn');
    if (btn) btn.style.background = this._errorsOnly ? '#dc2626' : '';
    this._render();
  },

  _toggleStarredOnly() {
    this._starredOnly = !this._starredOnly;
    var btn = document.getElementById('ev-starred-btn');
    if (btn) btn.style.background = this._starredOnly ? '#ca8a04' : '';
    this._render();
  },

  _onFilterChange() { this._render(); },

  _togglePause() {
    this._paused = !this._paused;
    var btn = document.getElementById('ev-pause-btn');
    if (btn) btn.textContent = this._paused ? '▶' : '⏸';
  },

  _addEvent(data) {
    if (this._paused) return;
    var et = data.event_type || '';
    if (et === 'tool_call' || data.tool_name) {
      data._category = 'tool';
    } else if (et === 'thinking' || et === 'step') {
      data._category = 'thinking';
    } else if (et === 'response' || et === 'text' || et.indexOf('message_') === 0) {
      data._category = 'response';
    } else if (et.indexOf('handoff') !== -1 || et.indexOf('handoff') !== -1) {
      data._category = 'handoff';
    } else {
      data._category = 'system';
    }
    this._events.unshift(data);
    if (this._events.length > this._maxEvents) this._events.length = this._maxEvents;
    this._render();
  },

  _selectedEventId: null,

  _render() {
    var inner = document.getElementById('ev-stream-inner');
    var countEl = document.getElementById('ev-count');
    if (!inner) return;

    var filtered = this._events;
    var cats = ['thinking','tool','handoff','response','system'];
    var enabled = {};
    cats.forEach(function(c) { enabled[c] = document.getElementById('ev-cat-' + c)?.checked !== false; });
    filtered = filtered.filter(function(ev) { return enabled[ev._category || 'system']; });
    if (this._errorsOnly) filtered = filtered.filter(function(ev) { return ev.severity === 'error' || ev.severity === 'critical'; });
    if (this._starredOnly) filtered = filtered.filter(function(ev) { return ev.agent && this._starredAgents.has(ev.agent); }.bind(this));
    if (this._selectedAgents && this._selectedAgents.size > 0) {
      filtered = filtered.filter(function(ev) { return !ev.agent || this._selectedAgents.has(ev.agent); }.bind(this));
    }

    if (countEl) countEl.textContent = this._events.length + (filtered.length !== this._events.length ? ' / ' + filtered.length : '');

    if (filtered.length === 0) {
      inner.innerHTML = '<div class="ev-empty">' + (this._events.length === 0 ? '等待事件...' : '无匹配事件') + '</div>';
      return;
    }

    var self = this;
    inner.innerHTML = filtered.slice(0, 300).map(function(ev, i) {
      var row = EventStream._renderEventRow(ev, i);
      // If this event is currently expanded, append the detail panel
      if (ev.id && ev.id === self._selectedEventId) {
        row += EventStream._renderDetail(ev);
      }
      return row;
    }).join('');

    // Re-bind click after innerHTML
    inner.querySelectorAll('.ev-entry').forEach(function(el) {
      el.onclick = function() {
        var evId = el.getAttribute('data-ev-id');
        self._selectedEventId = self._selectedEventId === evId ? null : evId;
        self._render();
      };
    });
  },

  _renderEventRow(ev, index) {
    var ts = formatTimestamp(ev.timestamp);
    var agent = ev.agent || '?';
    var agentColor = this._agentColors[agent] || '#94a3b8';
    var starred = this._starredAgents.has(agent);
    var evType = ev.event_type || '';
    var toolName = ev.tool_name || '';
    var sev = ev.severity || 'info';
    var textSnippet = ev.text_snippet || ev.text_full || '';
    var duration = ev.tool_duration_ms;
    var finish = ev.finish || '';
    var evId = ev.id || ('ev_' + index);

    var type = ev._category || 'system';
    if (evType === 'thinking' || evType === 'step') type = 'thinking';
    else if (evType === 'tool_call') type = 'tool';
    else if (evType === 'response') type = 'response';
    else if (evType && evType.indexOf('message_') === 0) type = 'response';

    var content = '';
    if (type === 'tool') {
      var desc = ev.description || '';
      content = '<span class="ev-action">调用:</span> ' + esc(toolName);
      if (desc) content += ' <span class="ev-args">' + esc(desc.length > 80 ? desc.slice(0,78) + '…' : desc) + '</span>';
      if (ev.tool_status === 'success' || ev.tool_status === 'completed') {
        content += ' <span class="ev-tool-st" style="color:#22c55e;">✓ ' + (duration ? (duration + 'ms') : '') + '</span>';
      } else if (ev.tool_status === 'error' || ev.tool_status === 'failed') {
        content += ' <span class="ev-tool-st" style="color:#ef4444;">✗ ' + (ev.tool_exit_code ? 'exit:' + ev.tool_exit_code : '') + '</span>';
      } else {
        content += ' <span class="ev-tool-st ev-status-running">...</span>';
      }
    } else if (type === 'thinking') {
      if (textSnippet) {
        content = esc(textSnippet.length > 120 ? textSnippet.slice(0,118) + '…' : textSnippet);
      } else {
        content = '分析中...';
      }
    } else if (type === 'response') {
      if (textSnippet) {
        content = esc(textSnippet.length > 150 ? textSnippet.slice(0,148) + '…' : textSnippet);
      } else if (finish) {
        content = '回复完成 · ' + esc(finish);
      } else {
        content = '回复';
      }
    } else {
      content = evType || '系统事件';
    }

    var catLabel, catCls;
    if (type === 'thinking') { catLabel = '思考'; catCls = 'ev-cat-think'; }
    else if (type === 'tool') { catLabel = '工具'; catCls = 'ev-cat-tool'; }
    else if (type === 'response') { catLabel = '输出'; catCls = 'ev-cat-resp'; }
    else { catLabel = '系统'; catCls = 'ev-cat-sys'; }

    var statusDot = '<span class="ev-status-dot" style="background:' + ({thinking:'#3b82f6',tool:'#f97316',response:'#22c55e'}[type]||'#94a3b8') + '"></span>';
    if (type === 'tool' && !ev.tool_status) statusDot = '<span class="ev-status-dot ev-status-running"></span>';

    var cls = 'ev-entry';
    if (sev === 'error' || ev.tool_status === 'error') cls += ' ev-row-err';
    if (starred) cls += ' ev-row-starred';
    if (evId === this._selectedEventId) cls += ' ev-row-selected';

    return '<div class="' + cls + '" data-ev-id="' + evId + '">'
      + statusDot
      + '<span class="ev-ts">' + ts + '</span>'
      + '<span class="ev-agent" style="color:' + agentColor + '">' + esc(agent.length > 24 ? agent.slice(0,22) + '…' : agent) + '</span>'
      + '<span class="ev-cat-tag ' + catCls + '">' + catLabel + '</span>'
      + '<span class="ev-content">' + content + '</span>'
      + (ev.tokens_input || ev.tokens_output ? '<span class="ev-tokens">in:' + (ev.tokens_input||0) + ' out:' + (ev.tokens_output||0) + '</span>' : '')
      + '</div>';
  },

  _renderDetail(ev) {
    var type = ev._category || 'system';
    var textFull = ev.text_full || ev.text_snippet || '';
    var descFull = ev.description || '';
    var finish = ev.finish || '';
    var html = '<div class="ev-detail">';

    if (type === 'tool') {
      html += '<div class="ev-detail-section"><b>工具:</b> ' + esc(ev.tool_name || '?') + '</div>';
      if (descFull) html += '<div class="ev-detail-section"><b>参数:</b><pre class="ev-detail-pre">' + esc(descFull) + '</pre></div>';
      html += '<div class="ev-detail-section"><b>状态:</b> ' + esc(ev.tool_status || '?') + (ev.tool_duration_ms ? ' · ' + ev.tool_duration_ms + 'ms' : '') + (ev.tool_exit_code ? ' · exit=' + ev.tool_exit_code : '') + '</div>';
    } else if (type === 'thinking' || type === 'response') {
      if (textFull) html += '<div class="ev-detail-section"><b>内容:</b><pre class="ev-detail-pre">' + esc(textFull) + '</pre></div>';
      if (finish) html += '<div class="ev-detail-section"><b>结束原因:</b> ' + esc(finish) + '</div>';
    } else {
      if (textFull) html += '<div class="ev-detail-section"><pre class="ev-detail-pre">' + esc(textFull) + '</pre></div>';
      if (finish) html += '<div class="ev-detail-section"><b>结束原因:</b> ' + esc(finish) + '</div>';
    }

    html += '<div class="ev-detail-meta">'
      + (ev.session_id ? '会话: ' + esc(String(ev.session_id).substring(0,16)) + ' · ' : '')
      + (ev.model_id ? '模型: ' + esc(ev.model_id) + ' · ' : '')
      + (ev.event_type ? '类型: ' + esc(ev.event_type) : '')
      + '</div>';
    html += '</div>';
    return html;
  },

};

// Close dropdown on outside click
document.addEventListener('click', function(e) {
  var dd = document.getElementById('ev-agent-dropdown');
  var btn = document.getElementById('ev-agent-dropdown-btn');
  if (dd && btn && dd.style.display !== 'none' && !dd.contains(e.target) && !btn.contains(e.target)) {
    dd.style.display = 'none';
  }
});
