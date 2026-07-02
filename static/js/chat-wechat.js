/**
 * MyAgentWatch — WeChat-style Chat Module
 * Three-column: conversation list | message stream | agent detail
 */
const WeChat = {
  state: {
    conversations: [],
    messages: [],
    contacts: [],
    activeConvId: null,
    focusMessageId: null,
    initialized: false,
    _lastMsgTs: {},
  },

  agentColors: {
    'Claude Code': '#3b82f6',
    'Claude Code Explore': '#8b5cf6',
    'Claude Code Plan': '#10b981',
    'Claude Code general-purpose': '#f59e0b',
  },

  init() {
    if (this.state.initialized) return;
    this.state.initialized = true;
    this.state.activeConvId = 1;
    // Set default detail card immediately
    document.getElementById('chat-detail-name').textContent = '群聊广播';
    document.getElementById('chat-detail-status').innerHTML = '<span class="chat-online">群聊</span>';
    document.getElementById('chat-detail-avatar').style.background = '#8b5cf6';
    document.getElementById('chat-detail-avatar').innerHTML = '<i class="fa-solid fa-users"></i>';
    this.fetchConversations();
    this.fetchContacts();
    this.fetchMessages();
  },

  teardown() {
    this.state.initialized = false;
    this.state.messages = [];
  },

  // ===== API calls =====
  async fetchConversations() {
    try {
      var r = await fetch(API + '/chat/conversations?participant_type=human&participant_id=tianyu');
      var d = await r.json();
      this.state.conversations = d.conversations || [];
      this.renderConversations();
    } catch(e) { console.warn('conv fetch', e); }
  },

  async fetchContacts() {
    try {
      var r = await fetch(API + '/chat/contacts');
      var d = await r.json();
      this.state.contacts = d.contacts || [];
      this.renderContacts();
    } catch(e) {}
  },

  async fetchMessages() {
    try {
      var r = await fetch(API + '/chat/messages/' + this.state.activeConvId + '?limit=100');
      var d = await r.json();
      this.state.messages = d.messages || [];
      this.renderMessages();
    } catch(e) {}
  },

  selectConversation(convId) {
    this.state.activeConvId = convId;
    var conv = this.state.conversations.find(function(c){ return c.id === convId; });
    if (conv) {
      document.getElementById('chat-header-name').textContent = conv.title || '聊天';
      this._updateDetailCard(conv);
    }
    this.markConversationRead(convId);
    this.fetchMessages();
    this.renderConversations();
  },

  async markConversationRead(convId) {
    try {
      await fetch(API + '/chat/read/' + convId, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ participant_type: 'human', participant_id: 'tianyu' })
      });
      this.fetchConversations();
    } catch(e) {}
  },

  _updateDetailCard(conv) {
    document.getElementById('chat-detail-name').textContent = conv.title || '聊天';
    if (conv.type === 'group') {
      document.getElementById('chat-detail-status').innerHTML = '<span class="chat-online">群聊</span>';
      document.getElementById('chat-detail-model').textContent = this.state.contacts.length + ' 个分组';
      document.getElementById('chat-detail-source').textContent = '广播消息';
      document.getElementById('chat-detail-avatar').style.background = '#8b5cf6';
      document.getElementById('chat-detail-avatar').innerHTML = '<i class="fa-solid fa-users"></i>';
    } else {
      // Private chat: find agent info from contacts
      var agentId = conv.agent_id || '';
      var found = null;
      this.state.contacts.forEach(function(g) {
        g.agents.forEach(function(a) {
          if (a.agent_id === agentId) found = a;
        });
      });
      if (found) {
        document.getElementById('chat-detail-status').innerHTML = '<span class="chat-online">在线</span>';
        document.getElementById('chat-detail-model').textContent = found.model_id || '--';
        document.getElementById('chat-detail-source').textContent = found.agent_type || '--';
        document.getElementById('chat-detail-avatar').style.background = this.agentColors[found.display_name] || this._nameColor(found.display_name);
        document.getElementById('chat-detail-avatar').innerHTML = (found.display_name || '?').substring(0,2).toUpperCase();
      }
    }
    // Fetch today's stats
    fetch(API + '/tokens/dashboard?days=1').then(function(r){ return r.json(); }).then(function(d) {
      var msgs = 0, cost = 0;
      (d.by_model || []).forEach(function(m) { msgs += 1; cost += (m.cost || 0); });
      document.getElementById('chat-detail-msgs').textContent = msgs + ' 个模型';
      document.getElementById('chat-detail-cost').textContent = '$' + cost.toFixed(2);
    }).catch(function(){});
  },

  searchContacts(q) {
    var items = document.querySelectorAll('.chat-conv-item');
    items.forEach(function(el) {
      var name = (el.querySelector('.chat-conv-name')?.textContent || '').toLowerCase();
      el.style.display = !q || name.indexOf(q.toLowerCase()) !== -1 ? '' : 'none';
    });
  },

  // ===== Send =====
  async sendMessage() {
    var input = document.getElementById('chat-input-area');
    if (!input) return;
    var content = input.value.trim();
    if (!content) return;
    input.value = '';
    try {
      await fetch(API + '/chat/messages/' + this.state.activeConvId, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ message: content, sender_type: 'human', sender_name: '天宇' })
      });
      // WS will deliver the message — fetchConversations for last_message update
      this.fetchConversations();
    } catch(e) { console.warn('send', e); }
  },

  // ===== Render =====
  renderConversations() {
    var list = document.getElementById('chat-conv-list');
    if (!list) return;
    var self = this;
    var convs = this.state.conversations;
    if (!convs.length) {
      list.innerHTML = '<div style="padding:30px;text-align:center;color:var(--text-muted);font-size:13px;">暂无会话</div>';
      return;
    }
    list.innerHTML = convs.map(function(c) {
      var activeCls = c.id === self.state.activeConvId ? ' active' : '';
      var avatar = (c.title || '?').substring(0,2).toUpperCase();
      var color = self._nameColor(c.title);
      var lastMsg = c.last_message || '';
      var time = self._fmtTime(c.last_time);
      var unread = c.unread_count > 0 ? '<span class="chat-conv-badge">' + (c.unread_count > 99 ? '99+' : c.unread_count) + '</span>' : '';
      var mention = c.mention_count > 0 ? '<span class="chat-conv-mini mention">@' + (c.mention_count > 99 ? '99+' : c.mention_count) + '</span>' : '';
      var tasks = (c.pending_task_count || c.task_count || 0) > 0 ? '<span class="chat-conv-mini task">T' + (c.pending_task_count || c.task_count) + '</span>' : '';
      var online = c.type === 'group' ? '' : '<span class="online-dot on"></span>';
      return '<div class="chat-conv-item' + activeCls + '" onclick="WeChat.selectConversation(' + c.id + ')">'
        + '<div class="chat-conv-avatar" style="background:' + color + '">' + avatar + online + '</div>'
        + '<div class="chat-conv-info"><div class="chat-conv-name">' + esc(c.title || '?') + '</div>'
        + '<div class="chat-conv-last">' + (lastMsg ? esc(lastMsg.substring(0,40)) : '') + '</div></div>'
        + '<div class="chat-conv-meta"><div class="chat-conv-time">' + time + '</div>' + unread + mention + tasks + '</div>'
        + '</div>';
    }).join('');
  },

  renderMessages() {
    var container = document.getElementById('chat-messages');
    if (!container) return;
    var msgs = this.state.messages;
    if (!msgs.length) {
      container.innerHTML = '<div style="padding:40px;text-align:center;color:var(--text-muted);font-size:14px;">开始聊天吧</div>';
      return;
    }
    var self = this;
    var lastDate = '';
    container.innerHTML = msgs.map(function(m) {
      var dateStr = self._fmtDate(m.timestamp);
      var divider = '';
      if (dateStr !== lastDate) {
        lastDate = dateStr;
        divider = '<div class="chat-time-divider"><span>' + dateStr + '</span></div>';
      }
      return divider + self._renderMsgBubble(m);
    }).join('');
    container.scrollTop = container.scrollHeight;
    if (this.state.focusMessageId) this._focusRenderedMessage(this.state.focusMessageId);
  },

  _renderMsgBubble(m) {
    var isMe = m.sender_type === 'human';
    var sender = m.sender_name || '?';
    var timeStr = this._fmtTime(m.timestamp);
    var isAgentInit = m.is_agent_initiated;

    if (m.msg_type === 'system') {
      return '<div class="chat-system">' + esc(m.content) + '</div>';
    }

    if (isMe) {
      return '<div class="chat-msg-row right" data-msg-id="' + esc(m.id || '') + '"><div class="chat-bubble">'
        + esc(m.content) + this._renderAttachments(m) + this._renderThreadHint(m) + this._renderTaskCards(m)
        + '<div class="msg-time">' + timeStr + '</div></div></div>';
    }

    // Agent message
    var color = this.agentColors[sender] || this._nameColor(sender);
    var avatar = sender.substring(0,2).toUpperCase();
    var badge = isAgentInit ? '<span class="agent-badge-mini">Agent</span>' : '';
    var content;

    if (m.msg_type === 'tool_call') {
      content = '<div class="chat-tool"><div class="chat-tool-name">🔧 ' + esc(m.tool_name || '工具调用') + '</div>'
        + '<div class="chat-tool-code">' + esc(m.content) + '</div>'
        + (m.tool_status === 'success' ? '<div class="chat-tool-result">✅ 完成</div>' : '')
        + '</div>';
    } else if (m.msg_type === 'handoff') {
      content = '<div class="chat-handoff"><div class="chat-handoff-arrow">🔀 Agent 交接</div>'
        + esc(m.content) + '</div>';
    } else if (m.share_type === 'result') {
      content = '<div class="chat-bubble left">'
        + '<div style="color:#22c55e;font-weight:600;margin-bottom:4px;">📤 ' + esc(m.task_context || '任务完成') + '</div>'
        + esc(m.content) + this._renderAttachments(m) + this._renderThreadHint(m) + this._renderTaskCards(m)
        + '<div class="msg-time">' + timeStr + '</div></div>';
    } else {
      content = '<div class="chat-bubble left">' + esc(m.content) + this._renderAttachments(m) + this._renderThreadHint(m)
        + this._renderTaskCards(m) + '<div class="msg-time">' + timeStr + '</div></div>';
    }

    return '<div class="chat-msg-row left" data-msg-id="' + esc(m.id || '') + '">'
      + '<div class="chat-msg-avatar" style="background:' + color + '">' + avatar + '</div>'
      + '<div class="chat-msg-body">'
      + '<div class="chat-msg-sender">' + badge + esc(sender) + '</div>'
      + content + '</div></div>';
  },

  focusMessage(messageId) {
    this.state.focusMessageId = messageId;
    this.fetchMessages();
  },

  _focusRenderedMessage(messageId) {
    setTimeout(function() {
      var el = document.querySelector('.chat-msg-row[data-msg-id="' + messageId + '"]');
      if (!el) return;
      el.scrollIntoView({ block: 'center', behavior: 'smooth' });
      el.classList.add('chat-msg-focused');
      setTimeout(function(){ el.classList.remove('chat-msg-focused'); }, 2200);
      WeChat.state.focusMessageId = null;
    }, 120);
  },

  _renderThreadHint(m) {
    if (!m.reply_to && !m.root_id) return '';
    var root = m.root_id || m.reply_to;
    return '<div class="chat-thread-hint">thread #' + esc(root) + '</div>';
  },

  _renderAttachments(m) {
    var attachments = m.attachments || [];
    if (!attachments.length) return '';
    var self = this;
    return '<div class="chat-attachments">' + attachments.map(function(a) {
      var type = a.type || a.attachment_type || 'file';
      var title = a.title || a.url || type;
      var url = a.url || '';
      var icon = type === 'image' ? 'image' : (type === 'video' ? 'video' : (type === 'audio' ? 'volume-high' : 'link'));
      var href = url ? ' href="' + self._attr(url) + '" target="_blank" rel="noopener noreferrer"' : '';
      return '<a class="chat-attachment" ' + href + '>'
        + '<i class="fa-solid fa-' + esc(icon) + '"></i>'
        + '<span>' + esc(title) + '</span>'
        + '</a>';
    }).join('') + '</div>';
  },

  _renderTaskCards(m) {
    var tasks = m.tasks || [];
    if (!tasks.length) return '';
    var self = this;
    return '<div class="chat-task-cards">' + tasks.map(function(t) {
      var status = t.status || 'queued';
      var title = t.title || t.task_type || 'agent task';
      var agent = t.agent_name || t.agent_id || 'Agent';
      var attempt = (t.attempt_count || 0) + '/' + (t.max_attempts || 3);
      var lease = t.lease_expires_at ? self._fmtTime(t.lease_expires_at) : '-';
      var lastError = t.last_error || t.error_text || '';
      var approval = t.approval_status || 'not_required';
      var events = (t.events || []).slice(-3).map(function(ev) {
        return '<div class="chat-task-event"><span>' + esc(self._fmtTime(ev.created_at)) + '</span> '
          + esc(ev.event_type || 'event') + '</div>';
      }).join('');
      return '<div class="chat-task-card status-' + esc(status) + '">'
        + '<div class="chat-task-top"><span>#' + esc(t.id) + '</span><span>' + esc(status) + '</span></div>'
        + '<div class="chat-task-title">' + esc(title) + '</div>'
        + '<div class="chat-task-agent">' + esc(agent) + ' · ' + esc(t.task_type || 'task') + '</div>'
        + '<div class="chat-task-approval approval-' + esc(approval) + '">approval ' + esc(approval) + '</div>'
        + '<div class="chat-task-runner">attempt ' + esc(attempt) + ' · lease ' + esc(lease) + '</div>'
        + (lastError ? '<div class="chat-task-error">' + esc(lastError.substring(0, 160)) + '</div>' : '')
        + (events ? '<div class="chat-task-events">' + events + '</div>' : '')
        + self._renderTaskActionButtons(t)
        + '</div>';
    }).join('') + '</div>';
  },

  _renderTaskActionButtons(t) {
    var status = t.status || 'queued';
    var approval = t.approval_status || 'not_required';
    var buttons = [
      '<button type="button" onclick="WeChat.openTaskContext(' + Number(t.id || 0) + ')">查看</button>'
    ];
    if (approval === 'pending' || approval === 'rejected') {
      buttons.push('<button type="button" class="primary" onclick="WeChat.taskAction(' + Number(t.id || 0) + ', \'approve\')">批准</button>');
    }
    if (approval === 'pending') {
      buttons.push('<button type="button" class="danger" onclick="WeChat.taskAction(' + Number(t.id || 0) + ', \'reject\')">拒绝</button>');
    }
    if (status === 'failed' || status === 'cancelled' || approval === 'rejected') {
      buttons.push('<button type="button" onclick="WeChat.taskAction(' + Number(t.id || 0) + ', \'retry\')">重试</button>');
    }
    if (status === 'queued' || status === 'claimed' || status === 'running') {
      buttons.push('<button type="button" class="danger" onclick="WeChat.taskAction(' + Number(t.id || 0) + ', \'cancel\')">取消</button>');
    }
    return '<div class="chat-task-actions">' + buttons.join('') + '</div>';
  },

  async openTaskContext(taskId) {
    try {
      var r = await fetch(API + '/agent/tasks/' + Number(taskId) + '/context');
      var d = await r.json();
      if (!r.ok || d.error) {
        alert('打开 task context 失败: ' + (d.error || r.status));
        return;
      }
      this._renderTaskContext(d);
    } catch(e) {
      alert('打开 task context 失败');
    }
  },

  async taskAction(taskId, action) {
    var path = { approve: 'approve', reject: 'reject', retry: 'retry', cancel: 'cancel' }[action];
    if (!path) return;
    var body = { actor_id: 'tianyu', actor_name: '天宇' };
    if (action === 'reject') {
      var reason = prompt('拒绝原因（可选）', '');
      if (reason === null) return;
      body.reason = reason;
    }
    if (action === 'cancel' && !confirm('确定取消这个 task？')) return;
    try {
      var r = await fetch(API + '/agent/tasks/' + Number(taskId) + '/' + path, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(body)
      });
      var d = await r.json();
      if (!r.ok || d.error) {
        alert('task 操作失败: ' + (d.error || r.status));
        return;
      }
      await this.fetchMessages();
      await this.fetchConversations();
      await this.openTaskContext(taskId);
    } catch(e) {
      alert('task 操作失败');
    }
  },

  _renderTaskContext(data) {
    var task = data.task || {};
    var ctx = data.message_context || {};
    var msg = ctx.message || {};
    var conv = ctx.conversation || {};
    var thread = ctx.thread || {};
    var threadReplies = thread.replies || thread.messages || [];
    var events = data.events || task.events || [];
    var inbox = ctx.inbox || [];
    var status = task.status || 'queued';
    var approval = task.approval_status || 'not_required';
    var source = task.source_conversation_id && task.source_message_id
      ? 'chat:' + task.source_conversation_id + ':msg:' + task.source_message_id
      : '-';

    document.getElementById('chat-detail-name').textContent = 'Task #' + (task.id || '');
    document.getElementById('chat-detail-status').innerHTML = '<span class="chat-task-status-inline status-' + esc(status) + '">' + esc(status) + '</span>';
    document.getElementById('chat-detail-model').textContent = task.task_type || '-';
    document.getElementById('chat-detail-source').textContent = source;
    document.getElementById('chat-detail-msgs').textContent = approval;
    document.getElementById('chat-detail-cost').textContent = (task.attempt_count || 0) + '/' + (task.max_attempts || 3);
    document.getElementById('chat-detail-avatar').style.background = '#2563eb';
    document.getElementById('chat-detail-avatar').innerHTML = '<i class="fa-solid fa-clipboard-check"></i>';

    var title = document.getElementById('chat-contacts-title');
    var panel = document.getElementById('chat-contacts');
    if (!panel) return;
    if (title) title.textContent = 'Task Context';
    var actions = this._renderTaskActionButtons(task);
    var sourceButton = task.source_message_id
      ? '<button type="button" onclick="WeChat.focusMessage(' + Number(task.source_message_id) + ')">跳到原消息</button>'
      : '';
    var eventHtml = events.length ? events.map(function(ev) {
      var message = ev.message ? '<div class="chat-context-event-msg">' + esc(ev.message) + '</div>' : '';
      return '<div class="chat-context-event"><div><b>' + esc(ev.event_type || 'event') + '</b> <span>' + esc(WeChat._fmtTime(ev.created_at)) + '</span></div>'
        + '<div class="chat-context-meta">by ' + esc(ev.actor_id || 'system') + '</div>' + message + '</div>';
    }).join('') : '<div class="chat-context-empty">暂无事件</div>';
    var inboxHtml = inbox.length ? inbox.map(function(item) {
      return '<div class="chat-context-meta">#' + esc(item.id) + ' ' + esc(item.delivery_type || item.sender_type || 'inbox') + '</div>';
    }).join('') : '<div class="chat-context-meta">无 inbox 记录</div>';

    panel.innerHTML =
      '<div class="chat-context-panel">'
      + '<div class="chat-context-section">'
      + '<div class="chat-context-title">' + esc(task.title || task.task_type || 'agent task') + '</div>'
      + '<div class="chat-context-meta">' + esc(task.agent_name || task.agent_id || '-') + ' · ' + esc(task.requester_name || task.requester_id || '-') + '</div>'
      + '<div class="chat-task-approval approval-' + esc(approval) + '">approval ' + esc(approval) + (task.approval_required ? ' · required' : '') + '</div>'
      + actions + '</div>'
      + '<div class="chat-context-section"><div class="chat-context-title">来源</div>'
      + '<div class="chat-context-meta">' + esc(conv.title || '-') + ' · ' + esc(source) + '</div>'
      + '<div class="chat-context-message">' + esc(msg.content || task.body || '-') + '</div>'
      + '<div class="chat-task-actions">' + sourceButton + '</div></div>'
      + '<div class="chat-context-section"><div class="chat-context-title">线程</div>'
      + '<div class="chat-context-meta">' + esc((thread.reply_count || threadReplies.length || 0)) + ' replies</div></div>'
      + '<div class="chat-context-section"><div class="chat-context-title">Inbox</div>' + inboxHtml + '</div>'
      + '<div class="chat-context-section"><div class="chat-context-title">Runner</div>'
      + '<div class="chat-context-meta">lease ' + esc(this._fmtTime(task.lease_expires_at) || '-') + ' · attempts ' + esc((task.attempt_count || 0) + '/' + (task.max_attempts || 3)) + '</div>'
      + (task.last_error || task.error_text ? '<div class="chat-task-error">' + esc((task.last_error || task.error_text).substring(0, 240)) + '</div>' : '')
      + '</div>'
      + '<div class="chat-context-section"><div class="chat-context-title">Events</div><div class="chat-context-events">' + eventHtml + '</div></div>'
      + '<div class="chat-context-section"><button type="button" class="chat-context-secondary" onclick="WeChat.renderContacts()">返回 Agent 列表</button></div>'
      + '</div>';
  },

  renderContacts() {
    var el = document.getElementById('chat-contacts');
    if (!el) return;
    var title = document.getElementById('chat-contacts-title');
    if (title) title.textContent = 'Agent 列表';
    var contacts = this.state.contacts;
    if (!contacts.length) {
      el.innerHTML = '<div style="padding:20px;text-align:center;color:var(--text-muted);font-size:13px;">暂无 Agent</div>';
      return;
    }
    var self = this;
    var html = '';
    contacts.forEach(function(g) {
      html += '<div style="padding:4px 16px;font-size:11px;color:var(--text-muted);font-weight:600;">' + esc(g.group || '默认') + ' (' + g.online + '/' + g.agents.length + ')</div>';
      g.agents.forEach(function(a) {
        var color = self.agentColors[a.display_name] || '#94a3b8';
        var dotColor = a.status === 'active' || a.status === 'idle' || a.status === 'working' ? '#22c55e' : '#6b7280';
        html += '<div class="chat-contact-item" onclick="WeChat._startPrivateChat(\'' + esc(a.agent_id) + '\',\'' + esc(a.display_name) + '\')">'
          + '<span class="chat-contact-dot" style="background:' + dotColor + '"></span>'
          + '<span>' + esc(a.display_name) + '</span>'
          + '<span style="margin-left:auto;font-size:11px;color:var(--text-muted);">' + esc(a.model_id || '') + '</span>'
          + '</div>';
      });
    });
    el.innerHTML = html;
  },

  _startPrivateChat(agentId, name) {
    // Create or find a private conversation with this agent
    fetch(API + '/chat/conversations', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ type: 'private', agent_id: agentId, title: name })
    }).then(function(r) { return r.json(); }).then(function(d) {
      if (d.conversation) WeChat.selectConversation(d.conversation.id);
    }).catch(function(e) { console.warn(e); });
  },

  clearChat() {
    if (!confirm('确定清空当前会话？')) return;
    this.state.messages = [];
    this.renderMessages();
  },

  // WebSocket receive
  onSocketMessage(data) {
    if (!this.state.initialized) return;
    var convId = data.conversation_id;
    if (!convId) return;
    var msg = data.message || {};
    var content = typeof msg.content === 'string' ? msg.content : (typeof data.message === 'string' ? data.message : '');
    var exists = this.state.messages.some(function(m) {
      return m.timestamp === (msg.timestamp || data.timestamp) && String(m.content) === String(content);
    });
    if (!exists) {
      this.state.messages.push({
        sender_type: msg.sender_type || 'agent',
        sender_name: msg.sender_name || data.sender_name || 'Agent',
        content: content,
        id: msg.id,
        reply_to: msg.reply_to,
        root_id: msg.root_id,
        msg_type: msg.msg_type || 'text',
        is_agent_initiated: msg.is_agent_initiated,
        share_type: msg.share_type,
        task_context: msg.task_context,
        tasks: msg.tasks || [],
        task_count: msg.task_count || 0,
        attachments: msg.attachments || [],
        metadata: msg.metadata || {},
        tool_name: msg.tool_name,
        tool_status: msg.tool_status,
        timestamp: msg.timestamp || data.timestamp || Date.now()
      });
    }
    if (convId === this.state.activeConvId) this.renderMessages();
    this.fetchConversations();
  },

  // ===== Helpers =====
  _nameColor(name) {
    var colors = ['#3b82f6','#8b5cf6','#10b981','#f59e0b','#ef4444','#ec4899','#06b6d4','#f97316','#84cc16'];
    var hash = 0; for (var i=0;i<(name||'').length;i++) hash = name.charCodeAt(i) + ((hash<<5)-hash);
    return colors[Math.abs(hash) % colors.length];
  },

  _attr(value) {
    return String(value || '').replace(/&/g, '&amp;').replace(/"/g, '&quot;').replace(/</g, '&lt;');
  },

  _fmtTime(ts) {
    if (!ts) return '';
    var d = new Date(ts);
    var now = new Date();
    var pad = function(n){return n<10?'0'+n:''+n;};
    if (d.toDateString() === now.toDateString()) return pad(d.getHours())+':'+pad(d.getMinutes());
    return pad(d.getMonth()+1)+'-'+pad(d.getDate());
  },

  _fmtDate(ts) {
    if (!ts) return '';
    var d = new Date(ts);
    var now = new Date();
    if (d.toDateString() === now.toDateString()) return '今天';
    var yesterday = new Date(now); yesterday.setDate(now.getDate()-1);
    if (d.toDateString() === yesterday.toDateString()) return '昨天';
    return (d.getMonth()+1)+'月'+d.getDate()+'日';
  },
};
