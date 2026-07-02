/**
 * MyAgentWatch 日志查看器
 * 三栏布局：Agent树 + 日志流 + 详情面板
 * 分类筛选：思考/工具/交互/输出/系统
 */

(function () {
  'use strict';

  const API = (typeof API_BASE !== 'undefined') ? API_BASE : '/api';
  const PHASE_CATEGORY = {
    thinking: '思考', tool_call: '工具', tool_result: '工具',
    handoff: '交互', handoff_result: '交互',
    response: '输出', instruction: '输出',
    error: '系统', heartbeat: '系统', source_status: '系统'
  };

  let state = {
    selectedAgent: null,
    selectedTurnId: null,
    categories: { 思考: true, 工具: true, 交互: true, 输出: true, 系统: true },
    severity: '',
    timeRange: 'all',
    search: '',
    realtime: true,
    turns: [],
    tree: [],
    pollTimer: null,
    initialized: false
  };

  // ===== 初始化 =====
  function init() {
    if (state.initialized) return;
    state.initialized = true;
    fetchTree();
    fetchTurns();
    startRealtime();
  }

  function teardown() {
    state.initialized = false;
    stopRealtime();
  }

  // ===== Agent 树 =====
  async function fetchTree() {
    try {
      const res = await fetch(API + '/logs/tree');
      const data = await res.json();
      state.tree = data.tree || [];
      renderTree();
    } catch (e) {
      console.warn('日志树加载失败:', e);
    }
  }

  function renderTree() {
    const container = document.getElementById('agent-tree');
    if (!container) return;

    const total = state.tree.reduce((s, g) => s + g.total, 0);
    var selBg = state.selectedAgent ? '' : "var(--accent)";
    var selAlpha = state.selectedAgent ? '0' : '0.15';
    let html = `<div style="font-size:13px; display:flex; flex-direction:column; gap:2px;">`;
    html += `<div class="tree-item" style="padding:4px 8px; cursor:pointer; border-radius:4px; background:rgba(15,159,255,${selAlpha}); font-weight:${state.selectedAgent ? 'normal' : '600'};"
                  onclick="LogViewer.selectAgent(null)">
               <i class="fa-solid fa-folder-open" style="margin-right:6px;"></i>全部Agent
               <span style="float:right; color:var(--text-muted); font-size:11px;">${total}</span></div>`;

    for (const group of state.tree) {
      html += `<div style="margin-left:12px; display:flex; flex-direction:column; gap:1px;">`;
      html += `<div class="tree-group" style="padding:2px 4px; font-weight:600; font-size:12px;"><i class="fa-solid fa-folder" style="color:var(--status-active); margin-right:4px;"></i>${escHtml(group.group)}
               <span style="font-size:11px; color:var(--text-muted);">${group.total}</span></div>`;

      for (const agent of group.agents) {
        var isSel = state.selectedAgent === agent.agent_id;
        var bg = isSel ? 'rgba(15,159,255,0.2)' : 'transparent';
        var dotColor = _statusColorHex(agent.status);
        html += `<div class="tree-item" style="padding:3px 8px; cursor:pointer; border-radius:4px; background:${bg}; margin-left:14px;"
                      onclick="LogViewer.selectAgent('${escAttr(agent.agent_id)}')">
                   <i class="fa-solid fa-circle" style="font-size:8px; margin-right:6px; color:${dotColor};"></i>
                   ${escHtml(agent.display_name)}
                   <span style="float:right; font-size:11px; color:var(--text-muted);">${agent.turn_count}</span></div>`;
      }
      html += `</div>`;
    }
    html += '</div>';
    container.innerHTML = html;
  }

  function _statusColorHex(s) {
    var map = { active: '#22c55e', idle: '#f59e0b', error: '#ef4444', offline: '#6b7280' };
    return map[s] || '#9ca3af';
  }

  // ===== 日志流 =====
  async function fetchTurns() {
    const params = new URLSearchParams();
    params.set('limit', '200');
    if (state.selectedAgent) params.set('agent', state.selectedAgent);
    if (state.search) params.set('q', state.search);
    if (state.severity) params.set('severity', state.severity);

    // 时间范围
    const now = Date.now();
    const ranges = { '15m': 900000, '1h': 3600000, 'today': 86400000 };
    const rangeMs = ranges[state.timeRange] || 3600000;
    if (state.timeRange !== 'all') {
      params.set('since', String(now - rangeMs));
    }

    try {
      const res = await fetch(API + '/logs/turns?' + params.toString());
      const data = await res.json();
      state.turns = data.turns || [];
      renderLogStream();
    } catch (e) {
      console.warn('日志加载失败:', e);
    }
  }

  function renderLogStream() {
    const container = document.getElementById('turn-log-stream');
    const counter = document.getElementById('log-count');
    if (!container) return;

    const filtered = state.turns.filter(function (t) {
      const cat = PHASE_CATEGORY[t.phase] || '系统';
      return state.categories[cat] !== false;
    });

    if (counter) counter.textContent = '共 ' + filtered.length + ' 条日志';

    if (filtered.length === 0) {
      container.innerHTML = '<div style="padding:32px; text-align:center; color:var(--text-muted);">没有匹配的日志记录</div>';
      return;
    }

    var html = '';
    for (var i = 0; i < filtered.length; i++) {
      var t = filtered[i];
      var cat = PHASE_CATEGORY[t.phase] || '系统';
      var icon = _phaseIconClass(t.phase);
      var catColor = _catColorHex(cat);
      var isErr = t.severity === 'error' || t.severity === 'critical';
      var isActive = t.id === state.selectedTurnId;
      var time = fmtTime(t.time_start);
      var agentLabel = shortAgent(t.agent_id);
      var sourceType = t.source_type || '';
      var preview = _formatPreview(t.phase, t.content_preview || '');

      var sevClass = isErr ? ' severity-error' : '';
      var activeClass = isActive ? ' active' : '';

      html += `<div class="log-line${sevClass}${activeClass}" data-turn-id="${t.id}" onclick="LogViewer.selectTurn(${t.id})"
                    style="padding:6px 10px; font-family:var(--font-mono); font-size:13px; line-height:1.6; border-radius:4px; margin-bottom:3px;">
                 <span style="color:#6b7280;">${time}</span>
                 <span style="margin-left:8px; color:${catColor};"><i class="${icon}" style="margin-right:4px;"></i>${escHtml(agentLabel)}</span>
                 <span class="source-tag ${sourceType}">${sourceType}</span>
                 <span style="margin-left:8px; color:#d1d5db;">${escHtml(preview)}</span>
                 ${isErr ? '<span style="color:#ef4444; margin-left:4px;">🔴</span>' : ''}
               </div>`;
    }
    container.innerHTML = html;
  }

  function _phaseIconClass(phase) {
    var map = {
      thinking: 'fa-solid fa-brain', tool_call: 'fa-solid fa-wrench', tool_result: 'fa-solid fa-file-lines',
      handoff: 'fa-solid fa-comment', handoff_result: 'fa-regular fa-comment',
      response: 'fa-solid fa-arrow-up', instruction: 'fa-solid fa-arrow-down',
      error: 'fa-solid fa-triangle-exclamation', heartbeat: 'fa-solid fa-heartbeat'
    };
    return map[phase] || 'fa-solid fa-gear';
  }

  function _formatPreview(phase, content) {
    if (!content) return '';
    if (phase === 'tool_call') {
      // JSON 参数 → key: value 摘要
      try {
        var obj = JSON.parse(content);
        var keys = Object.keys(obj);
        var short = keys.slice(0, 3).map(function(k) {
          var v = obj[k];
          var vs = typeof v === 'string' ? v.substring(0, 40) : JSON.stringify(v).substring(0, 40);
          return k + ': ' + vs;
        }).join(', ');
        if (keys.length > 3) short += '...';
        return short.substring(0, 120);
      } catch (e) { return content.substring(0, 120); }
    }
    if (phase === 'tool_result' || phase === 'response' || phase === 'instruction') {
      // 纯文本：取第一行有意义的内容
      var lines = content.split('\n');
      // 跳过空行和系统标记行
      for (var i = 0; i < lines.length; i++) {
        var line = lines[i].trim();
        if (line && !line.startsWith('<system') && !line.startsWith('---')) {
          return line.substring(0, 120);
        }
      }
      return content.substring(0, 120);
    }
    return content.substring(0, 120);
  }

  function _catColorHex(cat) {
    var map = { '思考': '#60a5fa', '工具': '#fb923c', '交互': '#a78bfa', '输出': '#34d399', '系统': '#9ca3af' };
    return map[cat] || '#9ca3af';
  }

  function fmtTime(ms) {
    if (!ms) return '??-?? ??:??:??';
    var d = new Date(ms);
    var pad = function(n) { return n < 10 ? '0' + n : '' + n; };
    return d.getFullYear() + '-' + pad(d.getMonth() + 1) + '-' + pad(d.getDate()) + ' ' + pad(d.getHours()) + ':' + pad(d.getMinutes()) + ':' + pad(d.getSeconds()) + '.' + String(d.getMilliseconds()).padStart(3, '0');
  }

  function shortAgent(agentId) {
    if (!agentId) return '?';
    const parts = agentId.split('::');
    if (parts.length >= 6) return parts[4];  // agent_name
    return agentId.substring(0, 20);
  }

  // ===== 详情面板 =====
  async function showDetail(turnId) {
    state.selectedTurnId = turnId;
    renderLogStream();  // 更新高亮

    try {
      const res = await fetch(API + '/logs/turn/' + turnId);
      if (!res.ok) throw new Error('Not found');
      const detail = await res.json();
      renderDetail(detail);
    } catch (e) {
      document.getElementById('log-detail-panel').innerHTML =
        '<div style="padding:16px; color:var(--text-muted);">加载详情失败</div>';
    }
  }

  function renderDetail(detail) {
    const panel = document.getElementById('log-detail-panel');
    if (!panel) return;

    const turn = detail.turn || {};
    const blocks = detail.blocks || [];
    const handoff = detail.handoff;

    var blocksHtml = '';
    for (var bi = 0; bi < blocks.length; bi++) {
      var b = blocks[bi];
      var blockContent = '';
      var blockLabel = '';

      if (b.block_type === 'tool_input') {
        blockLabel = '<div style="color:#fb923c; font-size:11px; margin-bottom:4px;">🔧 ' + escHtml(b.tool_name || '工具') + ' — 输入参数</div>';
        blockContent = _formatContent(b.content, 'json');
      } else if (b.block_type === 'tool_output') {
        blockLabel = '<div style="color:#34d399; font-size:11px; margin-bottom:4px;">📋 执行结果</div>';
        blockContent = _formatContent(b.content, 'text');
      } else if (b.block_type === 'thinking') {
        blockLabel = '<div style="color:#60a5fa; font-size:11px; margin-bottom:4px;">💭 思考过程</div>';
        blockContent = _formatContent(b.content, 'text');
      } else if (b.block_type === 'response_text') {
        blockLabel = '<div style="color:#a78bfa; font-size:11px; margin-bottom:4px;">💬 回复内容</div>';
        blockContent = _formatContent(b.content, 'text');
      } else if (b.block_type === 'user_text') {
        blockLabel = '<div style="color:#d1d5db; font-size:11px; margin-bottom:4px;">👤 用户输入</div>';
        blockContent = _formatContent(b.content, 'text');
      } else {
        blockContent = _formatContent(b.content, 'text');
      }

      blocksHtml += `<div style="background:#0f172a; border-radius:4px; padding:10px; margin-bottom:6px;">
        ${blockLabel}
        ${blockContent}
      </div>`;
    }
    if (!blocksHtml) {
      blocksHtml = '<div style="color:var(--text-muted); font-size:12px;">无详细内容</div>';
    }

    var handoffHtml = '';
    if (handoff) {
      handoffHtml = `
        <hr style="border-color:var(--border); margin:10px 0;">
        <div style="color:var(--text-muted); font-size:11px; margin-bottom:2px;">Agent 交接</div>
        <div style="font-size:13px;"><span style="color:#a78bfa;">→</span> ${escHtml(handoff.to_agent_id || '?')}</div>
        <div style="font-size:11px; color:var(--text-muted); margin-top:2px;">类型: ${escHtml(handoff.subagent_type || '')}</div>
        <div style="font-size:11px; color:var(--text-muted);">状态: ${escHtml(handoff.status || '')}</div>`;
    }

    var cat = PHASE_CATEGORY[turn.phase] || '系统';
    var catColor = _catColorHex(cat);
    var sevColor = turn.severity === 'error' ? '#ef4444' : '#3b82f6';

    panel.innerHTML = `
      <div style="margin-bottom:10px;">
        <div style="color:var(--text-muted); font-size:11px; margin-bottom:1px;">日志ID</div>
        <div style="font-family:var(--font-mono); font-size:13px;">#${turn.id}</div>
      </div>
      <div style="margin-bottom:10px;">
        <div style="color:var(--text-muted); font-size:11px; margin-bottom:1px;">Agent</div>
        <div style="font-size:13px;">${escHtml(shortAgent(turn.agent_id))}
          <span class="source-tag ${turn.source_type || ''}">${turn.source_type || ''}</span></div>
      </div>
      <div style="margin-bottom:10px;">
        <div style="color:var(--text-muted); font-size:11px; margin-bottom:1px;">时间</div>
        <div style="font-size:13px;">${fmtTime(turn.time_start)}</div>
      </div>
      <div style="margin-bottom:10px;">
        <div style="color:var(--text-muted); font-size:11px; margin-bottom:1px;">会话ID</div>
        <div style="font-family:var(--font-mono); font-size:11px; cursor:pointer; color:var(--accent);"
             onclick="LogViewer.filterTrace('${escAttr(turn.trace_id || '')}')">${escHtml((turn.session_id || '').substring(0, 20))}...</div>
      </div>
      <div style="margin-bottom:10px;">
        <div style="color:var(--text-muted); font-size:11px; margin-bottom:1px;">级别 / 类别</div>
        <div style="font-size:13px;">
          <span style="color:${sevColor};">${turn.severity || 'info'}</span>
          / <span style="color:${catColor};">${cat}</span>
        </div>
      </div>
      ${turn.trace_id ? `
      <div style="margin-bottom:10px;">
        <div style="color:var(--text-muted); font-size:11px; margin-bottom:1px;">追踪ID</div>
        <div style="font-family:var(--font-mono); font-size:11px; cursor:pointer; color:var(--accent);"
             onclick="LogViewer.filterTrace('${escAttr(turn.trace_id)}')">${escHtml(turn.trace_id.substring(0, 24))}...</div>
      </div>` : ''}
      <hr style="border-color:var(--border);">
      <div style="color:var(--text-muted); font-size:11px; margin-bottom:6px; margin-top:10px;">完整内容</div>
      ${blocksHtml}
      ${handoffHtml}
      <hr style="border-color:var(--border); margin-top:10px;">
      <div style="display:flex; gap:8px; margin-top:10px;">
        <button style="flex:1; padding:8px; background:var(--bg-card); border:1px solid var(--border); border-radius:4px; color:var(--text-primary); cursor:pointer; font-size:12px;"
                onclick="LogViewer.copyDetail()">
          <i class="fa-solid fa-copy" style="margin-right:4px;"></i> 复制
        </button>
      </div>`;
  }

  // ===== 筛选 =====
  function selectAgent(agentId) {
    state.selectedAgent = agentId;
    state.selectedTurnId = null;
    renderTree();
    fetchTurns();
  }

  function selectTurn(turnId) {
    showDetail(turnId);
  }

  function toggleCategory(cat) {
    state.categories[cat] = !state.categories[cat];
    const cb = document.getElementById('cat-' + cat);
    if (cb) cb.checked = state.categories[cat];
    renderLogStream();
  }

  function setSeverity(s) {
    state.severity = s;
    fetchTurns();
  }

  function setTimeRange(r) {
    state.timeRange = r;
    fetchTurns();
  }

  function doSearch() {
    const input = document.getElementById('log-search-input');
    state.search = input ? input.value : '';
    fetchTurns();
  }

  function filterTrace(traceId) {
    if (!traceId) return;
    state.search = '';
    const input = document.getElementById('log-search-input');
    if (input) input.value = '';
    // 通过 trace_id 加载
    loadTrace(traceId);
  }

  async function loadTrace(traceId) {
    try {
      const res = await fetch(API + '/logs/trace/' + encodeURIComponent(traceId));
      const data = await res.json();
      state.turns = data.turns || [];
      state.selectedTurnId = null;
      renderLogStream();
      document.getElementById('turn-log-stream').insertAdjacentHTML(
        'afterbegin',
        '<div style="padding:6px 10px; background:rgba(59,130,246,0.1); color:#3b82f6; font-size:12px; margin-bottom:6px;">🔗 追踪链: 共 ' + data.turns.length + ' 条日志</div>'
      );
    } catch (e) {
      console.warn('Trace 加载失败:', e);
    }
  }

  function toggleRealtime() {
    state.realtime = !state.realtime;
    const btn = document.getElementById('btn-realtime');
    if (btn) {
      btn.innerHTML = state.realtime
        ? '<i class="fa-solid fa-pause"></i> 暂停'
        : '<i class="fa-solid fa-play"></i> 实时';
    }
    if (state.realtime) {
      startRealtime();
    } else {
      stopRealtime();
    }
  }

  function startRealtime() {
    stopRealtime();
    if (state.realtime) {
      state.pollTimer = setInterval(fetchTurns, 5000);
    }
  }

  function stopRealtime() {
    if (state.pollTimer) {
      clearInterval(state.pollTimer);
      state.pollTimer = null;
    }
  }

  function clearView() {
    state.turns = [];
    state.selectedTurnId = null;
    renderLogStream();
    document.getElementById('log-detail-panel').innerHTML =
      '<div style="padding:16px; color:var(--text-muted); text-align:center;">选择一条日志查看详情</div>';
  }

  function exportLogs() {
    const fmt = 'markdown';
    const params = new URLSearchParams();
    params.set('format', fmt);
    if (state.selectedAgent) params.set('agent', state.selectedAgent);
    window.open(API + '/logs/export?' + params.toString(), '_blank');
  }

  function copyDetail() {
    const panel = document.getElementById('log-detail-panel');
    if (!panel) return;
    const text = panel.innerText;
    navigator.clipboard.writeText(text).then(function () {
      if (typeof showToast === 'function') showToast('已复制到剪贴板', 'success', 2000);
    }).catch(function () {});
  }

  // ===== 工具 =====
  var _fullContentCache = {};
  function _formatContent(content, fmt) {
    if (!content) return '<span style="color:var(--text-muted);">(空)</span>';
    if (fmt === 'json') {
      try {
        var parsed = JSON.parse(content);
        return '<pre style="font-family:var(--font-mono); font-size:12px; white-space:pre-wrap; word-break:break-word; line-height:1.5; margin:0;">' + escHtml(JSON.stringify(parsed, null, 2)) + '</pre>';
      } catch (e) {
        return '<pre style="font-family:var(--font-mono); font-size:12px; white-space:pre-wrap; word-break:break-word; line-height:1.5; margin:0;">' + escHtml(content) + '</pre>';
      }
    }
    var MAX = 2000;
    var formatted = _formatCodeOutput(content);
    if (formatted.length <= MAX) {
      return '<pre style="font-family:var(--font-mono); font-size:12px; white-space:pre; line-height:1.6; margin:0; max-height:350px; overflow:auto; background:#0a0f1a; padding:8px; border-radius:3px;">' + formatted + '</pre>';
    }
    var cid = 'ce_' + (new Date().getTime());
    _fullContentCache[cid] = formatted;
    return '<pre id="' + cid + '" style="font-family:var(--font-mono); font-size:12px; white-space:pre; line-height:1.6; margin:0; max-height:250px; overflow:auto; background:#0a0f1a; padding:8px; border-radius:3px;">'
      + formatted.substring(0, MAX)
      + '\n\n... (' + (content.length - MAX) + ' 字已截断)</pre>'
      + '<span style="color:var(--accent); cursor:pointer; font-size:11px;" onclick="LogViewer._toggleContent(\'' + cid + '\')">[展开全部 ' + content.length + ' 字]</span>';
  }

  function _formatCodeOutput(content) {
    // 检测行号前缀（数字+冒号/制表符），行号灰显、内容亮显
    var lines = content.split('\n');
    if (lines.length < 2) return escHtml(content);
    var numbered = 0;
    for (var i = 0; i < Math.min(lines.length, 5); i++) {
      if (/^\s*\d+[:\t]/.test(lines[i])) numbered++;
    }
    if (numbered >= 3) {
      return lines.map(function(line) {
        var m = line.match(/^(\s*\d+)([:\t])(.*)/);
        if (m) return '<span style="color:#6b7280;">' + m[1] + m[2] + '</span><span style="color:#e2e8f0;">' + escHtml(m[3]) + '</span>';
        return '<span style="color:#e2e8f0;">' + escHtml(line) + '</span>';
      }).join('\n');
    }
    return escHtml(content);
  }

  function _toggleContent(cid) {
    var el = document.getElementById(cid);
    var full = _fullContentCache[cid];
    if (!el || !full) return;
    if (el.style.maxHeight === 'none') {
      el.style.maxHeight = '250px';
      el.innerHTML = escHtml(full.substring(0, 2000)) + '\n\n... (' + (full.length - 2000) + ' 字已截断)';
      el.nextElementSibling && (el.nextElementSibling.textContent = '[展开全部 ' + full.length + ' 字]');
    } else {
      el.style.maxHeight = 'none';
      el.innerHTML = escHtml(full);
      el.nextElementSibling && (el.nextElementSibling.textContent = '[收起]');
    }
  }

  function escHtml(s) {
    if (!s) return '';
    return String(s).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
  }

  function escAttr(s) {
    if (!s) return '';
    return String(s).replace(/'/g, "\\'").replace(/"/g, '&quot;');
  }

  // ===== 导出 API =====
  window.LogViewer = {
    init: init,
    teardown: teardown,
    selectAgent: selectAgent,
    selectTurn: selectTurn,
    toggleCategory: toggleCategory,
    setSeverity: setSeverity,
    setTimeRange: setTimeRange,
    doSearch: doSearch,
    toggleRealtime: toggleRealtime,
    clearView: clearView,
    exportLogs: exportLogs,
    copyDetail: copyDetail,
    filterTrace: filterTrace,
    _toggleContent: _toggleContent,
    fetchTurns: fetchTurns,
    fetchTree: fetchTree
  };

})();
