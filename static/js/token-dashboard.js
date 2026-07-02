/**
 * MyAgentWatch — Token Dashboard Tab
 * Daily bar chart + model breakdown table + hourly distribution.
 */
const TokenDashboard = {
  _refreshTimer: null,
  _chartInstances: [],

  init() {
    this.load();
    if (typeof fetchChartsFromApi === 'function') fetchChartsFromApi();
    this._refreshTimer = setInterval(() => {
      this.load();
      if (typeof fetchChartsFromApi === 'function') fetchChartsFromApi();
    }, 30000);
  },

  teardown() {
    if (this._refreshTimer) { clearInterval(this._refreshTimer); this._refreshTimer = null; }
    this._destroyCharts();
    // Destroy trend charts (module-level in charts.js — accessed via closure)
    try { if (typeof tokenChart !== 'undefined' && tokenChart) tokenChart.destroy(); } catch(e) {}
    try { if (typeof latencyChart !== 'undefined' && latencyChart) latencyChart.destroy(); } catch(e) {}
    try { if (typeof costChart !== 'undefined' && costChart) costChart.destroy(); } catch(e) {}
  },

  _destroyCharts() {
    this._chartInstances.forEach(c => { try { c.destroy(); } catch(e){} });
    this._chartInstances = [];
  },

  load() {
    const days = document.getElementById('token-days')?.value || 7;
    Promise.all([
      fetch(`${API}/tokens/dashboard?days=${days}`).then(r => r.json()),
      fetch(`${API}/tokens/by-agent?days=${days}`).then(r => r.json()),
      fetch(`${API}/tokens/unmapped`).then(r => r.json()),
    ]).then(([data, agentData, unmappedData]) => {
      this._renderDailyChart(data.by_day || []);
      this._renderModelTable(data.by_model || [], data.days || days);
      this._renderAgentTable(agentData.agents || []);
      this._renderUnmappedWarning(unmappedData.unmapped || []);
    }).catch(e => console.warn('Token dashboard load error:', e));
  },

  _renderDailyChart(rows) {
    const container = document.getElementById('token-chart');
    if (!container) return;
    this._destroyCharts();

    if (typeof Chart === 'undefined') {
      container.innerHTML = '<div class="empty-state">Chart.js 未加载，请检查网络连接</div>';
      // Fallback: simple text table
      this._renderTextTable(rows);
      return;
    }

    if (rows.length === 0) {
      container.innerHTML = '<div class="empty-state">暂无 Token 数据</div>';
      return;
    }

    const canvas = document.createElement('canvas');
    canvas.id = 'token-daily-canvas';
    container.innerHTML = '';
    container.appendChild(canvas);

    const labels = rows.map(r => r.day.slice(5)); // MM-DD
    const inpData = rows.map(r => r.inp);
    const outpData = rows.map(r => r.outp);
    const costData = rows.map(r => Number(r.cost || 0).toFixed(4));

    try {
      const ctx = canvas.getContext('2d');
      const chart = new Chart(ctx, {
        type: 'bar',
        data: {
          labels,
          datasets: [
            { label: 'Input', data: inpData, backgroundColor: '#3b82f6', borderRadius: 4 },
            { label: 'Output', data: outpData, backgroundColor: '#22c55e', borderRadius: 4 },
          ],
        },
        options: {
          responsive: true,
          maintainAspectRatio: false,
          scales: {
            x: { stacked: true, ticks: { color: '#94a3b8', font: { size: 10 } }, grid: { display: false } },
            y: { stacked: true, ticks: { color: '#94a3b8' }, title: { display: true, text: 'Tokens', color: '#94a3b8' } },
          },
          plugins: {
            legend: { labels: { color: '#94a3b8' } },
            tooltip: {
              callbacks: {
                label: ctx => `${ctx.dataset.label}: ${formatNumber(ctx.raw)}`,
                footer: items => `Cost: $${costData[items[0].dataIndex]}`,
              },
            },
          },
        },
      });
      this._chartInstances.push(chart);
    } catch (e) {
      container.innerHTML = '<div class="empty-state">Chart 初始化失败</div>';
    }
  },

  _renderAgentTable(rows) {
    const tbody = document.getElementById('token-agent-tbody');
    if (!tbody) return;
    if (!rows || rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="4" class="empty-state">暂无数据</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(r => {
      var name = (r.agent_id || '?').split(':').pop();
      return '<tr>' +
        '<td>' + esc(name) + '</td>' +
        '<td class="num">' + formatNumber((r.inp || 0) + (r.outp || 0)) + '</td>' +
        '<td class="num">' + (r.task_count || 0) + '</td>' +
        '<td class="num cost-cell">&#36;' + (r.cost || 0).toFixed(4) + '</td>' +
        '</tr>';
    }).join('');
  },

  _renderUnmappedWarning(unmapped) {
    const el = document.getElementById('token-unmapped-alert');
    if (!el) return;
    if (!unmapped || unmapped.length === 0) {
      el.style.display = 'none';
      return;
    }
    el.style.display = '';
    el.innerHTML = '<i class="fa-solid fa-triangle-exclamation"></i> ' +
      unmapped.length + ' 个模型有用量但无定价: ' +
      unmapped.map(function(m) { return m.model_id; }).join(', ') +
      ' — <a href="#" onclick="switchTab(\'config\')" style="color:#f59e0b;">添加定价</a>';
  },

  _renderTextTable(rows) {
    const container = document.getElementById('token-chart');
    if (!container || rows.length === 0) return;
    let html = '<table class="token-table" style="width:100%;border-collapse:collapse;font-size:11px;">';
    html += '<tr style="border-bottom:1px solid var(--border);"><th>日期</th><th class="num">Input</th><th class="num">Output</th></tr>';
    rows.forEach(r => {
      html += '<tr><td>' + r.day + '</td><td class="num">' + formatNumber(r.inp) + '</td><td class="num">' + formatNumber(r.outp) + '</td></tr>';
    });
    html += '</table>';
    container.innerHTML = html;
  },

  _renderModelTable(rows, days) {
    const tbody = document.getElementById('token-model-tbody');
    if (!tbody) return;
    if (rows.length === 0) {
      tbody.innerHTML = '<tr><td colspan="6" class="empty-state">暂无数据</td></tr>';
      return;
    }
    tbody.innerHTML = rows.map(r => {
      const total = (r.inp || 0) + (r.outp || 0);
      return `<tr>
        <td><span class="provider-badge provider-${r.provider || 'unknown'}">${r.provider || '?'}</span></td>
        <td>${esc(r.model || 'unknown')}</td>
        <td class="num">${formatNumber(total)}</td>
        <td class="num">${formatNumber(r.inp || 0)}</td>
        <td class="num">${formatNumber(r.outp || 0)}</td>
        <td class="num cost-cell">$${(r.cost || 0).toFixed(4)}</td>
      </tr>`;
    }).join('');
  },
};
