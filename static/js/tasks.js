/**
 * MyAgentWatch — Task lifecycle board.
 */
window.TaskBoard = {
  _initialized: false,
  _boundClick: false,
  _tasks: [],
  _columns: [
    { key: 'queued', title: '队列', icon: 'fa-list-check', statuses: ['queued', 'dispatched'] },
    { key: 'running', title: '进行中', icon: 'fa-spinner', statuses: ['running'] },
    { key: 'completed', title: '完成', icon: 'fa-circle-check', statuses: ['completed'] },
    { key: 'failed', title: '失败', icon: 'fa-triangle-exclamation', statuses: ['failed', 'cancelled'] },
  ],

  init() {
    this._initialized = true;
    this._bindActions();
    this.load();
  },

  teardown() {
    this._initialized = false;
  },

  load() {
    fetch(API + '/tasks?limit=200')
      .then(r => r.json())
      .then(d => {
        this._tasks = d.tasks || [];
        this.render();
      })
      .catch(e => {
        console.warn('Task load failed:', e);
        const board = document.getElementById('task-board');
        if (board) board.innerHTML = '<div class="task-empty">任务加载失败</div>';
      });
  },

  _bindActions() {
    if (this._boundClick) return;
    const board = document.getElementById('task-board');
    if (!board) return;
    board.addEventListener('click', (event) => {
      const detailBtn = event.target.closest('[data-task-detail]');
      if (detailBtn) {
        event.stopPropagation();
        this.openDetail(Number(detailBtn.dataset.taskId));
        return;
      }
      const btn = event.target.closest('[data-task-status]');
      if (btn) {
        event.stopPropagation();
        this.setStatus(Number(btn.dataset.taskId), btn.dataset.taskStatus);
        return;
      }
      const card = event.target.closest('.task-card[data-task-id]');
      if (card) this.openDetail(Number(card.dataset.taskId));
    });
    document.addEventListener('click', (event) => {
      if (event.target.closest('[data-task-detail-close]')) {
        this.closeDetail();
        return;
      }
      const modal = document.getElementById('task-detail-modal');
      if (modal && event.target === modal) this.closeDetail();
    });
    document.addEventListener('keydown', (event) => {
      if (event.key === 'Escape') this.closeDetail();
    });
    this._boundClick = true;
  },

  createTask() {
    const titleEl = document.getElementById('task-title-input');
    const agentEl = document.getElementById('task-agent-input');
    const priorityEl = document.getElementById('task-priority-input');
    const title = (titleEl && titleEl.value || '').trim();
    if (!title) {
      if (typeof showToast === 'function') showToast('请先输入任务标题', 'warn');
      return;
    }
    fetch(API + '/tasks', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        title,
        assigned_agent_id: (agentEl && agentEl.value || '').trim(),
        priority: Number(priorityEl && priorityEl.value || 0),
        actor_id: '天宇',
      }),
    }).then(r => r.json()).then(d => {
      if (d.task) {
        if (titleEl) titleEl.value = '';
        if (typeof showToast === 'function') showToast('任务已创建', 'success');
        this.load();
      } else if (typeof showToast === 'function') {
        showToast(d.error || '任务创建失败', 'error');
      }
    }).catch(e => console.warn('Task create failed:', e));
  },

  setStatus(taskId, status) {
    fetch(API + '/tasks/' + taskId + '/status', {
      method: 'PATCH',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ status, actor_id: '天宇' }),
    }).then(r => r.json()).then(d => {
      if (d.task) {
        if (typeof showToast === 'function') showToast('任务状态已更新', 'success');
        this.load();
      } else if (typeof showToast === 'function') {
        showToast(d.error || '状态更新失败', 'error');
      }
    }).catch(e => console.warn('Task status failed:', e));
  },

  render() {
    const board = document.getElementById('task-board');
    if (!board) return;
    const tasks = this._tasks || [];
    board.innerHTML = this._renderTrackerStrip(tasks) + this._columns.map(col => {
      const items = tasks.filter(t => col.statuses.indexOf(t.status) !== -1);
      return '<section class="task-column task-col-' + col.key + '">' +
        '<div class="task-column-head"><span><i class="fa-solid ' + col.icon + '"></i> ' + col.title + '</span><b>' + items.length + '</b></div>' +
        '<div class="task-column-body">' +
        (items.length ? items.map(t => this._renderTaskCard(t)).join('') : '<div class="task-empty small">暂无任务</div>') +
        '</div></section>';
    }).join('');
  },

  _renderTrackerStrip(tasks) {
    const open = tasks.filter(t => ['queued','dispatched','running'].indexOf(t.status) !== -1).length;
    const autoChanged = tasks.filter(t => t.metadata && t.metadata.last_auto_tracking).length;
    return '<div class="task-auto-strip">' +
      '<span><i class="fa-solid fa-bolt"></i> 自动追踪</span>' +
      '<b>' + open + '</b><em>开放任务</em>' +
      '<b>' + autoChanged + '</b><em>自动流转</em>' +
      '<small>Agent 状态、群聊结果、错误信号驱动；人工按钮仅兜底</small>' +
      '</div>';
  },

  _renderTaskCard(t) {
    const agent = t.assigned_agent_id || '未指派';
    const meta = t.metadata || {};
    const auto = meta.auto_tracking !== false;
    const lastAuto = meta.last_auto_tracking || null;
    const tags = (t.tags || []).map(tag => '<span class="task-tag">' + esc(tag) + '</span>').join('');
    const actions = this._actionsFor(t);
    return '<article class="task-card" data-task-id="' + esc(String(t.id)) + '">' +
      '<div class="task-card-title-row">' +
        '<div class="task-card-title">#' + esc(String(t.id)) + ' ' + esc(t.title) + '</div>' +
        '<span class="task-track-badge ' + (auto ? 'on' : 'off') + '">' + (auto ? '自动' : '手动') + '</span>' +
      '</div>' +
      (t.description ? '<div class="task-card-desc">' + esc(t.description).slice(0, 140) + '</div>' : '') +
      '<div class="task-card-meta"><span><i class="fa-solid fa-robot"></i> ' + esc(agent) + '</span><span>' + formatTimestamp(t.updated_at) + '</span></div>' +
      (lastAuto ? '<div class="task-auto-note"><i class="fa-solid fa-bolt"></i> ' + esc(lastAuto.message || '自动追踪已更新') + '</div>' : '') +
      (tags ? '<div class="task-tags">' + tags + '</div>' : '') +
      '<div class="task-card-actions">' + actions + '</div>' +
      '</article>';
  },

  _actionsFor(t) {
    const detail = '<button data-task-id="' + t.id + '" data-task-detail="true"><i class="fa-solid fa-circle-info"></i> 详情</button>';
    if (t.status === 'queued' || t.status === 'dispatched') {
      return detail +
        '<button data-task-id="' + t.id + '" data-task-status="running">人工开始</button>' +
        '<button data-task-id="' + t.id + '" data-task-status="cancelled">人工取消</button>';
    }
    if (t.status === 'running') {
      return detail +
        '<button data-task-id="' + t.id + '" data-task-status="completed">人工完成</button>' +
        '<button data-task-id="' + t.id + '" data-task-status="failed">人工失败</button>';
    }
    return detail + '<button data-task-id="' + t.id + '" data-task-status="queued">人工重排</button>';
  },

  openDetail(taskId) {
    if (!taskId) return;
    const modal = this._ensureDetailModal();
    modal.classList.add('open');
    modal.querySelector('.task-detail-body').innerHTML = '<div class="task-detail-loading">加载任务详情...</div>';
    fetch(API + '/tasks/' + taskId)
      .then(r => r.json())
      .then(d => {
        if (d.task) {
          modal.querySelector('.task-detail-body').innerHTML = this._renderDetail(d.task, d.timeline || []);
        } else {
          modal.querySelector('.task-detail-body').innerHTML = '<div class="task-detail-empty">任务不存在</div>';
        }
      })
      .catch(e => {
        console.warn('Task detail failed:', e);
        modal.querySelector('.task-detail-body').innerHTML = '<div class="task-detail-empty">详情加载失败</div>';
      });
  },

  closeDetail() {
    const modal = document.getElementById('task-detail-modal');
    if (modal) modal.classList.remove('open');
  },

  _ensureDetailModal() {
    let modal = document.getElementById('task-detail-modal');
    if (modal) return modal;
    modal = document.createElement('div');
    modal.id = 'task-detail-modal';
    modal.className = 'task-detail-modal';
    modal.innerHTML = '<section class="task-detail-panel">' +
      '<div class="task-detail-head">' +
        '<div><h3><i class="fa-solid fa-circle-info"></i> 任务详情</h3><p>自动追踪信号、完整描述和状态时间线</p></div>' +
        '<button data-task-detail-close="true" title="关闭"><i class="fa-solid fa-xmark"></i></button>' +
      '</div>' +
      '<div class="task-detail-body"></div>' +
      '</section>';
    document.body.appendChild(modal);
    return modal;
  },

  _renderDetail(task, timeline) {
    const meta = task.metadata || {};
    const lastAuto = meta.last_auto_tracking || null;
    const tags = (task.tags || []).map(tag => '<span class="task-tag">' + esc(tag) + '</span>').join('');
    const metaText = Object.keys(meta).length ? JSON.stringify(meta, null, 2) : '';
    return '<div class="task-detail-title-row">' +
        '<div>' +
          '<h4>#' + esc(String(task.id)) + ' ' + esc(task.title || '') + '</h4>' +
          '<span class="task-detail-status status-' + esc(task.status || '') + '">' + esc(this._statusText(task.status)) + '</span>' +
        '</div>' +
      '</div>' +
      '<div class="task-detail-grid">' +
        this._detailMetric('指派 Agent', task.assigned_agent_id || '未指派') +
        this._detailMetric('优先级', this._priorityText(task.priority)) +
        this._detailMetric('创建时间', formatTimestamp(task.time_created)) +
        this._detailMetric('更新时间', formatTimestamp(task.updated_at)) +
        this._detailMetric('开始时间', task.time_started ? formatTimestamp(task.time_started) : '--') +
        this._detailMetric('完成时间', task.time_completed ? formatTimestamp(task.time_completed) : '--') +
      '</div>' +
      '<section class="task-detail-section">' +
        '<h5>完整描述</h5>' +
        '<pre>' + esc(task.description || '无描述') + '</pre>' +
      '</section>' +
      (lastAuto ? '<section class="task-detail-section auto">' +
        '<h5><i class="fa-solid fa-bolt"></i> 最近自动追踪</h5>' +
        '<p>' + esc(lastAuto.message || '自动追踪已更新') + '</p>' +
        '<code>' + esc(JSON.stringify(lastAuto.signal || {}, null, 2)) + '</code>' +
      '</section>' : '') +
      (tags ? '<section class="task-detail-section"><h5>标签</h5><div class="task-tags">' + tags + '</div></section>' : '') +
      (metaText ? '<section class="task-detail-section"><h5>Metadata</h5><code>' + esc(metaText) + '</code></section>' : '') +
      '<section class="task-detail-section">' +
        '<h5>状态时间线</h5>' +
        this._renderTimeline(timeline) +
      '</section>';
  },

  _detailMetric(label, value) {
    return '<div class="task-detail-metric"><span>' + esc(label) + '</span><b>' + esc(String(value || '--')) + '</b></div>';
  },

  _renderTimeline(timeline) {
    if (!timeline.length) return '<div class="task-detail-empty">暂无时间线</div>';
    return '<div class="task-timeline">' + timeline.map(item => {
      const meta = item.metadata && Object.keys(item.metadata).length
        ? '<code>' + esc(JSON.stringify(item.metadata, null, 2)) + '</code>' : '';
      return '<div class="task-timeline-item">' +
        '<div class="task-timeline-dot"></div>' +
        '<div class="task-timeline-content">' +
          '<div class="task-timeline-top"><b>' + esc(this._eventText(item.event_type)) + '</b><span>' + esc(formatTimestamp(item.timestamp)) + '</span></div>' +
          '<p>' + esc(item.message || item.status || '') + '</p>' +
          '<small>' + esc(item.actor_id || 'system') + (item.status ? ' · ' + esc(this._statusText(item.status)) : '') + '</small>' +
          meta +
        '</div>' +
      '</div>';
    }).join('') + '</div>';
  },

  _statusText(status) {
    return {
      queued: '队列',
      dispatched: '已派发',
      running: '进行中',
      completed: '完成',
      failed: '失败',
      cancelled: '取消',
    }[status] || status || '--';
  },

  _eventText(eventType) {
    return {
      created: '创建',
      status_changed: '人工流转',
      auto_status_changed: '自动流转',
    }[eventType] || eventType || '事件';
  },

  _priorityText(priority) {
    const n = Number(priority || 0);
    if (n >= 2) return '紧急';
    if (n === 1) return '高优先级';
    return '普通';
  },
};
