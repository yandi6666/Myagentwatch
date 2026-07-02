/**
 * MyAgentWatch 3.2 — Tree List View
 * Data binding for the 3-column topology layout.
 */
(function () {
  var treeData = null;
  var selectedNode = null;
  var activeFilter = 'all';
  var searchQuery = '';
  var expandedGroups = {};

  // Colors match user's Tailwind config
  var SC = { active: 'success', idle: 'warning', error: 'error', offline: 'offline' };
  var ST = { active: '运行正常', idle: '等待', error: '错误', offline: '离线' };
  function sc(s) { return SC[s] || 'slate-400'; }
  function st(s) { return ST[s] || '未知'; }
  function dot(s) { return '<i class="fa-solid fa-circle text-' + sc(s) + ' mr-2"></i>'; }
  function esc(s) { s = String(s || ''); return s.replace(/&/g,'&amp;').replace(/</g,'&lt;'); }
  var BRANCH = ['#6366f1','#0891b2','#d946ef','#0d9488','#ea580c','#2563eb'];

  function buildTree(snapshot) {
    var agents = snapshot.agents || [];
    var groups = {};
    agents.forEach(function (a) {
      var g = a.group_name || a.group || '默认';
      if (!groups[g]) groups[g] = [];
      groups[g].push(a);
    });
    return { groups: groups, overview: snapshot, agents: agents };
  }

  function countBy(agents, statuses) {
    return agents.filter(function (a) { return statuses.indexOf(a.status) !== -1; }).length;
  }

  function render(snapshot) {
    if (!snapshot || !snapshot.agents) return;
    var data = buildTree(snapshot);
    treeData = data;
    renderStats(data);
    renderLeftSidebar(data);
    renderTreeList(data);
    renderRightSidebar(data);
  }

  // ── Top stats bar (removed; stats are in the global status strip now) ──
  function renderStats(data) {
    // Stats are now shown via the 4 status cards at the top of the dashboard.
    // updateStatusCards() in app.js handles the global strip.
  }

  // ── Left sidebar ──
  function renderLeftSidebar(data) {
    var agents = data.agents;
    var active = countBy(agents, ['active']);
    document.getElementById('topo-count-all').textContent = active + '/' + agents.length;
    document.getElementById('topo-count-idle').textContent = countBy(agents, ['idle','inactive']);
    document.getElementById('topo-count-error').textContent = countBy(agents, ['error']);
    document.getElementById('topo-count-offline').textContent = countBy(agents, ['offline']);

    var gl = document.getElementById('topo-group-list');
    var gnames = Object.keys(data.groups);
    gl.innerHTML = gnames.map(function (gname) {
      var gagents = data.groups[gname];
      var gActive = countBy(gagents, ['active']);
      var totalG = gagents.length;
      var bi = gnames.indexOf(gname) % BRANCH.length;
      var bc = BRANCH[bi];
      return '<div class="p-2 rounded bg-slate-800 cursor-pointer hover:bg-slate-700 mb-2" data-group="' + esc(gname) + '"'
        + ' style="border-left:4px solid ' + bc + ';">'
        + '<div class="flex items-center justify-between">'
        + '<span class="text-sm font-semibold">' + esc(gname) + '</span>'
        + '<span class="text-slate-400 text-xs">' + gActive + '在线 ' + (totalG - gActive > 0 ? (totalG - gActive) + '等待' : '') + '</span>'
        + '</div>'
        + '<div class="text-xs text-slate-400 mt-1">在线: ' + gActive
        + ' | 等待: ' + countBy(gagents, ['idle','inactive'])
        + ' | 错误: ' + countBy(gagents, ['error'])
        + ' | 离线: ' + countBy(gagents, ['offline'])
        + '</div>'
        + '</div>';
    }).join('');
  }

  // ── Tree list ──
  function renderTreeList(data) {
    var container = document.getElementById('topo-tree-container');
    var gnames = Object.keys(data.groups);
    gnames.forEach(function (g) { if (!(g in expandedGroups)) expandedGroups[g] = true; });

    var html = '';
    gnames.forEach(function (gname) {
      var gagents = data.groups[gname];
      var filtered = gagents;
      if (activeFilter === 'active') filtered = gagents.filter(function(a){return a.status==='active';});
      if (activeFilter === 'idle') filtered = gagents.filter(function(a){return a.status==='idle'||a.status==='inactive';});
      if (activeFilter === 'error') filtered = gagents.filter(function(a){return a.status==='error';});
      if (activeFilter === 'offline') filtered = gagents.filter(function(a){return a.status==='offline';});

      var isOpen = expandedGroups[gname];
      var gActive = countBy(gagents, ['active']);
      var bi = gnames.indexOf(gname) % BRANCH.length;
      var bc = BRANCH[bi];

      // Check if any agent matches search query
      var matchSearch = function (a) {
        if (!searchQuery) return true;
        var q = searchQuery.toLowerCase();
        return (a.display_name || a.name || '').toLowerCase().indexOf(q) !== -1
            || (a.model_id || '').toLowerCase().indexOf(q) !== -1
            || (a.group_name || '').toLowerCase().indexOf(q) !== -1;
      };
      var hasMatch = filtered.some(matchSearch);
      if (!hasMatch && searchQuery) return;

      html += '<div class="mb-3">'
        + '<div class="flex items-center p-2 rounded cursor-pointer topo-tree-group-header" data-group="' + esc(gname) + '"'
        + ' style="border-left:4px solid ' + bc + '; background:rgba(255,255,255,0.02);">'
        + '<i class="fa-solid fa-chevron-' + (isOpen ? 'down' : 'right') + ' mr-2 text-slate-400 text-xs"></i>'
        + '<span class="font-semibold text-sm">' + esc(gname) + '</span>'
        + '<span class="ml-auto text-slate-400 text-xs">'
        + gActive + '在线 '
        + (countBy(gagents, ['idle','inactive']) > 0 ? countBy(gagents, ['idle','inactive']) + '等待 ' : '')
        + (countBy(gagents, ['error']) > 0 ? countBy(gagents, ['error']) + '错误 ' : '')
        + (countBy(gagents, ['offline']) > 0 ? countBy(gagents, ['offline']) + '离线' : '')
        + '</span>'
        + '</div>';

      if (isOpen) {
        html += '<div class="ml-8 space-y-1 mt-1">';
        filtered.forEach(function (a) {
          if (!matchSearch(a)) return;
          var selClass = selectedNode && selectedNode.id === a.id ? ' bg-slate-600' : '';
          html += '<div class="flex items-center p-1.5 pl-4 rounded hover:bg-slate-800 cursor-pointer topo-tree-agent' + selClass + '" data-agent-id="' + esc(a.id) + '">'
            + dot(a.status)
            + '<span>' + esc(a.display_name || a.name) + '</span>'
            + '<span class="ml-2 text-slate-400 text-sm">(' + st(a.status) + ')</span>'
            + '</div>';
        });
        html += '</div>';
      }
      html += '</div>';
    });

    container.innerHTML = html || '<div class="text-slate-400 text-sm text-center py-8">没有匹配的节点</div>';

    container.querySelectorAll('.topo-tree-group-header').forEach(function (hdr) {
      hdr.addEventListener('click', function () {
        expandedGroups[this.dataset.group] = !expandedGroups[this.dataset.group];
        renderTreeList(data);
      });
    });
    container.querySelectorAll('.topo-tree-agent').forEach(function (el) {
      el.addEventListener('click', function () {
        var agent = data.agents.filter(function (a) { return a.id === this.dataset.agentId; })[0];
        if (agent) selectNode(agent, data);
      }.bind(el));
    });
  }

  // ── Right sidebar ──
  function renderRightSidebar(data) {
    var overview = data.overview;
    var alertList = document.getElementById('topo-alert-list');
    var logEntries = overview.activity_log || [];
    var alerts = logEntries.filter(function (e) { return e.severity === 'error' || e.severity === 'critical'; }).slice(0, 5);
    if (alerts.length === 0) {
      alertList.innerHTML = '<div class="text-slate-400 text-sm text-center py-4">暂无告警</div>';
    } else {
      alertList.innerHTML = alerts.map(function (a) {
        var cls = a.severity === 'critical' ? 'border-error bg-error/10' : 'border-warning bg-warning/10';
        var t = new Date(a.timestamp).toLocaleTimeString('zh-CN', { hour12: false });
        return '<div class="p-3 border-l-4 rounded ' + cls + ' mb-2">'
          + '<div class="text-xs text-slate-400 mb-1">' + t + '</div>'
          + '<div class="text-sm">' + esc(a.event_type || '告警') + '</div>'
          + '</div>';
      }).join('');
    }
  }

  // ── Select node ──
  function selectNode(agent, data) {
    selectedNode = agent;
    var detail = document.getElementById('topo-detail');
    detail.style.display = 'block';
    document.getElementById('topo-detail-name').textContent = '(已选中: ' + (agent.display_name || agent.name) + ')';

    document.getElementById('topo-detail-body').innerHTML =
      '<div class="grid grid-cols-2 gap-4 mb-4">'
      + '<div><div class="text-slate-400 text-sm mb-1">节点ID</div><div>' + esc(agent.id) + '</div></div>'
      + '<div><div class="text-slate-400 text-sm mb-1">所属主Agent</div><div>' + esc(agent.group_name || agent.group || '-') + '</div></div>'
      + '<div><div class="text-slate-400 text-sm mb-1">当前状态</div><div class="flex items-center">' + dot(agent.status) + ' ' + st(agent.status) + '</div></div>'
      + '<div><div class="text-slate-400 text-sm mb-1">运行时长</div><div>' + (agent.last_seen_time ? '--' : '--') + '</div></div>'
      + '<div><div class="text-slate-400 text-sm mb-1">启动时间</div><div>' + (agent.last_seen_time ? new Date(agent.last_seen_time).toLocaleString('zh-CN') : '-') + '</div></div>'
      + '<div><div class="text-slate-400 text-sm mb-1">最后心跳</div><div>' + (agent.last_seen_time ? new Date(agent.last_seen_time).toLocaleString('zh-CN') : '-') + '</div></div>'
      + '</div>';

    document.getElementById('topo-detail-actions').innerHTML =
      '<button class="px-3 py-1.5 bg-success text-white rounded text-sm hover:bg-success/90"><i class="fa-solid fa-rotate-right mr-1"></i>重启节点</button>'
      + '<button class="px-3 py-1.5 bg-slate-700 rounded text-sm hover:bg-slate-600"><i class="fa-solid fa-file-lines mr-1"></i>查看日志</button>'
      + '<button class="px-3 py-1.5 bg-error text-white rounded text-sm hover:bg-error/90"><i class="fa-solid fa-trash mr-1"></i>删除节点</button>';

    renderTreeList(data);
    detail.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
  }

  // ── Event bindings ──
  function bindEvents() {
    // Search input
    var si = document.getElementById('topo-search');
    if (si && !si._bound) { si._bound = true;
      si.addEventListener('input', function () {
        searchQuery = this.value.trim();
        if (treeData) renderTreeList(treeData);
      });
    }
    document.querySelectorAll('#topo-filter-list [data-filter]').forEach(function (el) {
      if (el._bound) return; el._bound = true;
      el.addEventListener('click', function () {
        document.querySelectorAll('#topo-filter-list [data-filter]').forEach(function (e) { e.classList.remove('active'); });
        this.classList.add('active');
        activeFilter = this.dataset.filter;
        if (treeData) renderTreeList(treeData);
      });
    });
    ['btn-collapse-all','btn-expand-all'].forEach(function (id) {
      var btn = document.getElementById(id);
      if (!btn || btn._bound) return; btn._bound = true;
      btn.addEventListener('click', function () {
        Object.keys(expandedGroups).forEach(function (g) { expandedGroups[g] = id === 'btn-expand-all'; });
        if (treeData) renderTreeList(treeData);
      });
    });
    document.querySelectorAll('.topo-detail-tab').forEach(function (tab) {
      if (tab._bound) return; tab._bound = true;
      tab.addEventListener('click', function () {
        document.querySelectorAll('.topo-detail-tab').forEach(function (t) { t.classList.remove('active','border-b-2','border-success','text-success'); t.classList.add('text-slate-400'); });
        this.classList.add('active','border-b-2','border-success','text-success');
      });
    });
    // Group list → scroll to tree
    var gl = document.getElementById('topo-group-list');
    if (gl && !gl._bound) { gl._bound = true;
      gl.addEventListener('click', function (e) {
        var item = e.target.closest('[data-group]');
        if (!item) return;
        var gname = item.dataset.group;
        expandedGroups[gname] = true;
        if (treeData) renderTreeList(treeData);
        var hdr = document.querySelector('.topo-tree-group-header[data-group="' + CSS.escape(gname) + '"]');
        if (hdr) setTimeout(function(){ hdr.scrollIntoView({behavior:'smooth',block:'start'}); }, 100);
      });
    }
  }

  window.renderTopology = function (snapshot) { if (snapshot) { render(snapshot); bindEvents(); } };
  window.renderTopologyFull = function (snapshot) { if (snapshot) { render(snapshot); bindEvents(); } };
})();
