/**
 * MyAgentWatch 2.0 — Main App Entry
 * Tab navigation, WebSocket connection, state management.
 */

const API = API_BASE;
let currentTab = 'dashboard';
let lastSnapshot = null;
let reconnectCount = 0;
let _subscribedAgents = new Set();
let _agentDeltas = {}; // agent_id → latest delta cache

// ===== Tab Switching =====
function switchTab(tabId) {
  // 离开日志 tab 时清理轮询
  if (currentTab === 'logs' && tabId !== 'logs' && typeof LogViewer !== 'undefined') {
    LogViewer.teardown();
  }
  // 离开群聊 tab 时清理轮询
  if (currentTab === 'chat' && tabId !== 'chat' && typeof WeChat !== 'undefined') {
    WeChat.teardown();
  }
  // 事件流 SSE 保持后台运行，切换 tab 不断开
  // 离开 Token tab 时清理图表
  if (currentTab === 'tokens' && tabId !== 'tokens' && typeof TokenDashboard !== 'undefined') {
    TokenDashboard.teardown();
  }
  if (currentTab === 'tasks' && tabId !== 'tasks' && typeof TaskBoard !== 'undefined') {
    TaskBoard.teardown();
  }
  currentTab = tabId;
  document.querySelectorAll('.tab-btn').forEach(b => b.classList.remove('active'));
  document.querySelectorAll('.tab-panel').forEach(p => p.classList.remove('active'));

  const btn = document.querySelector(`[data-tab="${tabId}"]`);
  if (btn) btn.classList.add('active');

  const panel = document.getElementById(`panel-${tabId}`);
  if (panel) panel.classList.add('active');

  const strip = document.getElementById('status-strip');
  if (strip) strip.style.display = tabId === 'dashboard' ? 'flex' : 'none';

  if (tabId === 'dashboard' && typeof window.renderTopology === 'function' && lastSnapshot) {
    setTimeout(function () { window.renderTopology(lastSnapshot); }, 50);
  }
  if (tabId === 'events') {
    // SSE already running since page load, just refresh the view
    setTimeout(function() {
      if (typeof EventStream !== 'undefined') {
        EventStream._buildAgentDropdown();
        EventStream._render();
      }
    }, 50);
  }
  if (tabId === 'logs') {
    setTimeout(function () {
      if (typeof LogViewer !== 'undefined' && LogViewer.init) {
        LogViewer.init();
      }
    }, 100);
  }
  if (tabId === 'chat') {
    setTimeout(function () {
      if (typeof WeChat !== 'undefined' && WeChat.init) {
        WeChat.init();
      }
    }, 100);
  }
  if (tabId === 'tokens') {
    setTimeout(function () {
      if (typeof TokenDashboard !== 'undefined' && TokenDashboard.init) {
        TokenDashboard.init();
      }
    }, 100);
  }
  if (tabId === 'tasks') {
    setTimeout(function () {
      if (typeof TaskBoard !== 'undefined' && TaskBoard.init) {
        TaskBoard.init();
      }
    }, 100);
  }
}

// ===== WebSocket =====
const socket = io({
  reconnection: true,
  reconnectionAttempts: Infinity,
  reconnectionDelay: 1000,
  reconnectionDelayMax: 10000,
});

socket.on('connect', () => {
  if (reconnectCount > 0) {
    console.log(`WebSocket 重连成功 (第 ${reconnectCount} 次)`);
    if (typeof showToast === 'function') showToast('WebSocket 已重新连接', 'success', 3000);
    // Re-subscribe to previously subscribed agents
    _subscribedAgents.forEach(function (aid) {
      socket.emit('subscribe_agent', { agent_id: aid });
    });
  } else {
    console.log('WebSocket connected');
  }
  const dot = safeGet('ws-dot');
  if (dot) dot.classList.remove('disconnected');
  safeSet('ws-text', '已连接');
  if (typeof showToast === 'function' && reconnectCount === 0) showToast('连接已建立', 'success', 2000);
});

socket.on('disconnect', (reason) => {
  reconnectCount++;
  console.warn(`WebSocket 断开: ${reason} (重连计数: ${reconnectCount})`);
  const dot = safeGet('ws-dot');
  if (dot) dot.classList.add('disconnected');
  safeSet('ws-text', `断开 (${reconnectCount})`);
  if (typeof showToast === 'function') showToast(`连接断开: ${reason}`, 'warn', 5000);
});

socket.on('alert_event', (alert) => {
  if (typeof showToast === 'function') showToast(`[${alert.level}] ${alert.message || alert.rule_name}`, 'warn', 8000);
  // Browser notification
  if (Notification && Notification.permission === 'granted') {
    try {
      new Notification('MyAgentWatch 告警', {
        body: `[${alert.level}] ${alert.message || alert.rule_name}`,
        icon: '/favicon.ico',
        tag: alert.rule_name || 'alert',
      });
    } catch (e) { /* ignore */ }
  }
});

socket.on('stat_snapshot', (data) => {
  lastSnapshot = data;
  if (data.topology) window.lastTopoData = data.topology;

  // Always update these first, each wrapped independently
  try { updateStatusCards(data); } catch(e) { console.warn(e); }
  // Chat online list handled by WeChat module

  // Rest wrapped to not block logs
  try {
    if (currentTab === 'dashboard') window.renderTopology(data);
    if (typeof updateListView === 'function') updateListView(data.agents || []);
    if (currentTab === 'tokens' && typeof updateCharts === 'function') updateCharts(data.tokens_by_agent || [], data.latency || [], data.hourly_tokens || []);
  } catch (e) { console.warn('Snapshot handler error:', e); }
});

socket.on('agent_delta', (delta) => {
  if (!delta || !delta.agent_id) return;
  _agentDeltas[delta.agent_id] = delta;
  // Update topology node status in-place if visible
  try {
    const node = document.querySelector(`.topo-node[data-agent-id="${delta.agent_id}"]`);
    if (node) {
      const statusDot = node.querySelector('.status-dot');
      if (statusDot) {
        const color = STATUS_COLORS[delta.status] || STATUS_COLORS.unknown;
        statusDot.style.backgroundColor = color;
      }
    }
  } catch (e) { /* ignore */ }
});

function handleTaskUpdate(event) {
  if (currentTab === 'tasks' && typeof TaskBoard !== 'undefined' && TaskBoard.load) {
    TaskBoard.load();
  }
  if (currentTab === 'chat' && typeof WeChat !== 'undefined') {
    if (WeChat.fetchConversations) WeChat.fetchConversations();
    if (WeChat.fetchMessages) WeChat.fetchMessages();
  }
  if (typeof showToast === 'function' && event && event.task) {
    showToast('任务更新: ' + (event.task.title || ('#' + event.task.id)), 'info', 2400);
  }
}

socket.on('task_update', handleTaskUpdate);
socket.on('agent_task_update', handleTaskUpdate);

// Heartbeat
setInterval(() => {
  if (socket.connected) socket.emit('ping');
}, 30000);

// ===== Status Cards =====
function updateStatusCards(data) {
  safeSet('s-active', data.active_agents ?? 0);
  safeSet('s-tokens', formatNumber(data.total_tokens_today ?? 0));
  safeSet('s-success', (data.success_rate ?? 0) + '%');
  safeSet('s-cost', '$' + (data.cost_today ?? 0).toFixed(2));
}

// ===== Initialization =====
document.addEventListener('DOMContentLoaded', () => {
  document.querySelectorAll('.tab-btn').forEach(btn => {
    btn.addEventListener('click', () => switchTab(btn.dataset.tab));
  });

  // Config tab: fetch config on open
  document.querySelector('[data-tab="config"]')?.addEventListener('click', () => {
    fetch(API + '/status').then(r => r.json()).then(d => {
      const pre = safeGet('config-display');
      if (pre) pre.textContent = JSON.stringify(d, null, 2);
    }).catch(e => console.error('Config status fetch failed:', e));
    // Load template list
    fetch(API + '/config/templates').then(r => r.json()).then(d => {
      const sel = safeGet('template-select');
      if (sel && d.templates) {
        sel.innerHTML = '<option value="default">默认 (通用)</option>' +
          d.templates.map(t => `<option value="${t.name}" ${t.name === d.active ? 'selected' : ''}>${t.name}</option>`).join('');
      }
    }).catch(e => console.error('Template list fetch failed:', e));
  });

  // Template apply
  safeGet('template-apply')?.addEventListener('click', () => {
    const sel = safeGet('template-select');
    if (!sel) return;
    const template = sel.value;
    fetch(API + '/config/template', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ template }),
    }).then(r => r.json()).then(d => {
      if (d.status === 'ok') {
        if (typeof showToast === 'function') showToast(d.message, 'success', 4000);
        // Refresh config display
        fetch(API + '/status').then(r => r.json()).then(d2 => {
          const pre = safeGet('config-display');
          if (pre) pre.textContent = JSON.stringify(d2, null, 2);
        });
      }
    }).catch(e => {
      console.error('Template apply failed:', e);
      if (typeof showToast === 'function') showToast('模板切换失败', 'error');
    });
  });

  // Charts toggle
  const chartBtn = safeGet('toggle-charts');
  const chartSection = safeGet('chart-section');
  if (chartBtn && chartSection) {
    chartBtn.addEventListener('click', () => {
      const visible = chartSection.style.display !== 'none';
      chartSection.style.display = visible ? 'none' : 'flex';
      chartBtn.innerHTML = visible
        ? '<i class="fa-solid fa-chart-bar"></i> 显示图表'
        : '<i class="fa-solid fa-chart-bar"></i> 隐藏图表';
    });
  }

  // Chat tab: enable input + fetch online list
  document.querySelector('[data-tab="chat"]')?.addEventListener('click', () => {
    const input = safeGet('chat-input');
    const btn = safeGet('chat-send');
    if (input) input.disabled = false;
    if (btn) btn.disabled = false;
    // Refresh online list from API
    fetch(API + '/agents')
      .then(function(r){ return r.json(); })
      .then(function(data){
        // Agents loaded, used by chat module
      })
      .catch(function(){});
  });

  // Chat send
  // Chat send — fully handled by WeChat module
  // Chat receive — fully handled by WeChat module

  // Resource monitor: poll /api/health every 5s
  function updateResources() {
    fetch(API + '/health')
      .then(function(r) { return r.json(); })
      .then(function(d) {
        var cpuEl = document.getElementById('res-cpu-val');
        var cpuBar = document.getElementById('res-cpu-bar');
        if (cpuEl) cpuEl.textContent = (d.cpu_pct || 0) + '%';
        if (cpuBar) cpuBar.style.width = (d.cpu_pct || 0) + '%';

        var memEl = document.getElementById('res-mem-val');
        var memBar = document.getElementById('res-mem-bar');
        if (memEl) memEl.textContent = (d.memory_pct || 0) + '%';
        if (memBar) memBar.style.width = (d.memory_pct || 0) + '%';

        var diskEl = document.getElementById('res-disk-val');
        var diskBar = document.getElementById('res-disk-bar');
        if (diskEl) diskEl.textContent = (d.disk_pct || 0) + '%';
        if (diskBar) diskBar.style.width = (d.disk_pct || 0) + '%';
      })
      .catch(function(){});
  }
  updateResources();
  setInterval(updateResources, 5000);

  // Quick actions
  var btnRefresh = document.getElementById('btn-refresh-all');
  if (btnRefresh) btnRefresh.addEventListener('click', function () {
    fetch(API + '/health').then(function(){});
    if (typeof window.renderTopology === 'function' && lastSnapshot) {
      window.renderTopology(lastSnapshot);
    }
    if (typeof showToast === 'function') showToast('状态已刷新', 'info');
  });

  var btnExport = document.getElementById('btn-export-report');
  if (btnExport) btnExport.addEventListener('click', function () {
    if (!lastSnapshot) return;
    var blob = new Blob([JSON.stringify(lastSnapshot, null, 2)], {type:'application/json'});
    var a = document.createElement('a');
    a.href = URL.createObjectURL(blob);
    a.download = 'myagentwatch-report-' + new Date().toISOString().slice(0,10) + '.json';
    a.click();
    if (typeof showToast === 'function') showToast('报告已导出', 'success');
  });

  var btnRestart = document.getElementById('btn-restart-all');
  var btnPause = document.getElementById('btn-pause-all');
  if (btnRestart) btnRestart.addEventListener('click', function () {
    if (typeof showToast === 'function') showToast('该功能需 Agent 支持远程控制', 'warn');
  });
  if (btnPause) btnPause.addEventListener('click', function () {
    if (typeof showToast === 'function') showToast('该功能需 Agent 支持远程控制', 'warn');
  });

  // Topbar settings → switch to config tab
  var settingsBtn = document.querySelector('.topbar-icon-btn');
  if (settingsBtn) {
    settingsBtn.addEventListener('click', function () {
      switchTab('config');
    });
  }

  // Topbar avatar → toast
  var avatarBtn = document.querySelector('.topbar-avatar');
  if (avatarBtn) {
    avatarBtn.addEventListener('click', function () {
      fetch(API + '/users').then(function(r){ return r.json(); }).then(function(d) {
        if (!d.users || !d.users.length) return;
        var humans = d.users.filter(function(u){ return u.type === 'human'; });
        var agents = d.users.filter(function(u){ return u.type === 'agent'; });
        var withToken = agents.filter(function(u){ return u.token_prefix; }).length;
        var msg = humans.map(function(u){ return u.name; }).join(', ') + ' | ';
        msg += agents.length + ' Agent, ' + withToken + ' 有令牌';
        if (typeof showToast === 'function') showToast(msg, 'info');
      }).catch(function(){});
    });
  }

  // Request browser notification permission
  if (window.Notification && Notification.permission === 'default') {
    Notification.requestPermission();
  }

  // ── Scoped Agent Subscriptions ──
  window.subscribeAgent = function (agentId) {
    if (!agentId || _subscribedAgents.has(agentId)) return;
    _subscribedAgents.add(agentId);
    if (socket.connected) socket.emit('subscribe_agent', { agent_id: agentId });
  };

  window.unsubscribeAgent = function (agentId) {
    if (!agentId || !_subscribedAgents.has(agentId)) return;
    _subscribedAgents.delete(agentId);
    if (socket.connected) socket.emit('unsubscribe_agent', { agent_id: agentId });
    delete _agentDeltas[agentId];
  };

  // ── Inbox ──
  socket.on('inbox_update', function () { fetchInboxCount(); });

  window.fetchInboxCount = function () {
    fetch(API + '/inbox?limit=1').then(function(r){ return r.json(); }).then(function(d) {
      var badge = document.getElementById('inbox-badge');
      if (!badge) return;
      var n = d.unread || 0;
      badge.style.display = n > 0 ? '' : 'none';
      badge.textContent = n > 99 ? '99+' : n;
    }).catch(function(){});
  };

  window.toggleInboxPanel = function () {
    var panel = document.getElementById('inbox-panel');
    if (!panel) return;
    if (panel.style.display === 'none') {
      panel.style.display = '';
      fetchInboxItems();
    } else {
      panel.style.display = 'none';
    }
  };

  function fetchInboxItems() {
    fetch(API + '/inbox?limit=50').then(function(r){ return r.json(); }).then(function(d) {
      renderInboxItems(d.items || []);
    }).catch(function(){});
  }

  function renderInboxItems(items) {
    var list = document.getElementById('inbox-list');
    if (!list) return;
    if (!items || items.length === 0) {
      list.innerHTML = '<div class="inbox-empty">暂无通知</div>';
      return;
    }
    list.innerHTML = items.map(function(it) {
      var cls = 'inbox-item' + (it.is_read ? '' : ' unread') + ' sev-' + (it.severity || 'info');
      var icon = ({friend_request:'fa-user-plus',agent_message:'fa-comment',alert:'fa-bell',share_task:'fa-share'}[it.type]) || 'fa-circle';
      var convId = it.source_conversation_id || '';
      var msgId = it.source_message_id || '';
      return '<div class="' + cls + '" onclick="openInboxItem(' + it.id + ',\'' + (it.link||'') + '\',' + (convId || 0) + ',' + (msgId || 0) + ')">' +
        '<div class="inbox-item-title"><i class="fa-solid ' + icon + '"></i> ' + esc(it.title) + '</div>' +
        '<div class="inbox-item-body">' + esc(it.body || '') + '</div>' +
        '<div class="inbox-item-time">' + formatTimestamp(it.created_at) + '</div>' +
        '</div>';
    }).join('');
  }

  window.openInboxItem = function (id, link, sourceConvId, sourceMsgId) {
    fetch(API + '/inbox/read/' + id, { method: 'POST' }).then(function() {
      fetchInboxCount();
      fetchInboxItems();
      var convId = sourceConvId || 0;
      var msgId = sourceMsgId || 0;
      if ((!convId || !msgId) && link) {
        var parts = link.split(':');
        if (parts[0] === 'chat' && parts[1]) convId = Number(parts[1]) || convId;
        if (parts[2] === 'msg' && parts[3]) msgId = Number(parts[3]) || msgId;
      }
      if (convId) {
        switchTab('chat');
        setTimeout(function() {
          if (typeof WeChat === 'undefined') return;
          WeChat.init();
          WeChat.selectConversation(convId);
          if (msgId && WeChat.focusMessage) WeChat.focusMessage(msgId);
        }, 160);
      }
    }).catch(function(){});
  };

  window.markAllInboxRead = function () {
    fetch(API + '/inbox/read-all', { method: 'POST' }).then(function() {
      fetchInboxCount();
      fetchInboxItems();
    }).catch(function(){});
  };

  // Click outside inbox panel to close
  document.addEventListener('click', function(e) {
    var panel = document.getElementById('inbox-panel');
    var bell = document.getElementById('inbox-bell');
    if (panel && bell && panel.style.display !== 'none') {
      if (!panel.contains(e.target) && !bell.contains(e.target)) {
        panel.style.display = 'none';
      }
    }
  });

  // Start event stream immediately — no need to visit the tab first
  if (typeof EventStream !== 'undefined' && EventStream.init) EventStream.init();

  fetchInboxCount();
  setInterval(fetchInboxCount, 15000);

  window.addEventListener('beforeunload', function() {
    if (typeof EventStream !== 'undefined') EventStream.teardown();
    if (typeof TokenDashboard !== 'undefined') TokenDashboard.teardown();
    if (typeof TaskBoard !== 'undefined') TaskBoard.teardown();
  });
});
