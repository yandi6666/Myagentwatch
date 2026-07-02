/**
 * MyAgentWatch 2.0 — Node Detail Panel
 * Right sidebar showing agent details on topology node click.
 * Requires: util.js (loaded before)
 */

let selectedNodeId = null;

function showNodeDetail(agent) {
  if (!agent) return;
  selectedNodeId = agent.id || agent.name;

  const panel = safeGet('node-detail');
  if (!panel) return;

  const statusIcon = agent.status === 'active' ? 'fa-solid fa-circle-check'
    : agent.status === 'idle' ? 'fa-solid fa-clock'
    : agent.status === 'thinking' ? 'fa-solid fa-brain'
    : agent.status === 'error' ? 'fa-solid fa-circle-xmark'
    : 'fa-solid fa-circle';

  const statusColor = `var(--status-${agent.status || 'offline'})`;

  const latStr = agent.latency_ms
    ? (agent.latency_ms >= 1000 ? (agent.latency_ms / 1000).toFixed(1) + 's' : agent.latency_ms + 'ms')
    : '-';

  const offlineInfo = agent.status === 'offline' && agent.offline_reason
    ? `<div class="nd-stat-row" style="color:var(--status-error);"><span class="nd-label"><i class="fa-solid fa-triangle-exclamation"></i> 离线原因</span><span class="nd-val">${esc(agent.offline_reason)}</span></div>`
    : '';

  panel.innerHTML = `
    <div style="display:flex; align-items:center; gap:8px; margin-bottom:8px;">
      <i class="${statusIcon}" style="color:${statusColor}; font-size:16px;"></i>
      <div class="nd-agent-name">${esc(agent.display_name || agent.name)}</div>
    </div>
    <div class="nd-agent-group"><i class="fa-solid fa-layer-group"></i> ${esc(agent.group_name || agent.group || '未知')}</div>
    <div class="nd-agent-model"><i class="fa-solid fa-microchip"></i> 模型: ${esc(agent.model_id || '(未知)')}</div>

    <div class="nd-section-title">指标</div>
    <div class="nd-stat-row"><span class="nd-label"><i class="fa-solid fa-coins"></i> Token 消耗</span><span class="nd-val">${formatNumber(agent.tokens_total || 0)}</span></div>
    <div class="nd-stat-row"><span class="nd-label"><i class="fa-solid fa-clock"></i> 延迟</span><span class="nd-val">${latStr}</span></div>
    <div class="nd-stat-row"><span class="nd-label"><i class="fa-solid fa-dollar-sign"></i> 成本</span><span class="nd-val">$${(agent.cost || 0).toFixed(4)}</span></div>
    <div class="nd-stat-row"><span class="nd-label"><i class="fa-solid fa-hourglass"></i> 最后活跃</span><span class="nd-val">${formatTimestamp(agent.last_seen_time)}</span></div>
    ${offlineInfo}

    <div class="nd-section-title"><i class="fa-solid fa-list-check"></i> 最近活动</div>
    <div id="nd-recent-activity" style="font-size:11px; color:var(--text-muted);"></div>
  `;

  // Populate recent activity from snapshot
  populateRecentActivity(agent);
}

function populateRecentActivity(agent) {
  const el = safeGet('nd-recent-activity');
  if (!el) return;
  const logs = (window.lastSnapshot && window.lastSnapshot.activity_log) || [];
  const agentLogs = logs.filter(function (e) {
    return e.agent_id && (e.agent_id === agent.id || e.agent_id.indexOf(agent.name) >= 0);
  }).slice(0, 5);

  if (agentLogs.length === 0) {
    el.innerHTML = '<span style="color:var(--text-muted);">暂无最近活动记录</span>';
    return;
  }
  el.innerHTML = agentLogs.map(function (e) {
    var ts = formatTimestamp(e.timestamp);
    var desc = parseEventDesc(e.event_type, e.data);
    var icon = e.severity === 'error' ? '🔴' : e.severity === 'warn' ? '🟡' : '🟢';
    return '<div style="margin-bottom:4px; display:flex; gap:6px; align-items:flex-start;">'
      + '<span>' + icon + '</span>'
      + '<span style="flex:1;"><span style="color:var(--text-muted);">[' + ts + ']</span> ' + esc(desc) + '</span>'
      + '</div>';
  }).join('');
}

function parseEventDesc(eventType, data) {
  var type = (eventType || '').replace('message_', '').replace('part_', '');
  var extra = '';
  try {
    if (data && typeof data === 'string') {
      var d = JSON.parse(data);
      if (d.finish) extra = ' (' + d.finish + ')';
      if (d.type) extra = ' [' + d.type + ']';
    }
  } catch (e) { /* use raw */ }
  var labels = { tool: '🔧 工具调用', text: '💬 文本', reasoning: '🧠 推理', 'step-start': '▶ 步骤开始', 'step-finish': '⏹ 步骤完成', assistant: '🤖 助手回复', user: '👤 用户输入' };
  return (labels[type] || type || '事件') + extra;
}

function clearNodeDetail() {
  selectedNodeId = null;
  const panel = safeGet('node-detail');
  if (!panel) return;
  panel.innerHTML = `
    <div class="nd-empty">
      <i class="fa-solid fa-hand-pointer"></i>
      <div>点击拓扑图中<br>的节点查看详情</div>
    </div>
  `;
}
