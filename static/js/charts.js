/**
 * MyAgentWatch - Chart.js visualizations
 */
let tokenChart = null;
let latencyChart = null;
let costChart = null;

function updateCharts(tokensByAgent, latencyData, hourlyTokens) {
  updateTokenBarChart(tokensByAgent);
  updateLatencyChart(latencyData);
  updateCostChart(hourlyTokens || []);
}

async function fetchChartsFromApi() {
  try {
    const resp = await fetch(API + '/stats/charts');
    const data = await resp.json();
    updateTokenBarChart(data.tokens_by_agent || []);
    updateLatencyChart(data.latency || []);
    updateCostChart(data.hourly_tokens || []);
  } catch(e) { console.warn('Charts fetch failed:', e); }
}

function updateTokenBarChart(agents) {
  const canvas = document.getElementById('token-bar-chart');
  if (!canvas || canvas.offsetParent === null) return;
  const ctx = canvas.getContext('2d');

  // 按总 Token 降序排列
  var sorted = agents.slice().sort(function(a, b) {
    var ta = (a.tokens_input || 0) + (a.tokens_output || 0) + (a.tokens_reasoning || 0);
    var tb = (b.tokens_input || 0) + (b.tokens_output || 0) + (b.tokens_reasoning || 0);
    return tb - ta;
  });

  var labels = sorted.map(function(a) {
    var name = a.name || a.agent_id || '?';
    return name.length > 24 ? name.substring(0, 22) + '…' : name;
  });
  var inputs = sorted.map(function(a) { return a.tokens_input || 0; });
  var outputs = sorted.map(function(a) { return a.tokens_output || 0; });
  var reasonings = sorted.map(function(a) { return a.tokens_reasoning || 0; });

  if (tokenChart) tokenChart.destroy();

  // 动态高度：每 agent 至少 24px
  var barHeight = Math.max(24, Math.min(40, sorted.length * 3 + 60));
  canvas.parentElement.style.height = (barHeight * sorted.length + 80) + 'px';

  tokenChart = new Chart(ctx, {
    type: 'bar',
    data: {
      labels: labels,
      datasets: [
        { label: 'Input', data: inputs, backgroundColor: '#0f9fff', borderRadius: 4 },
        { label: 'Output', data: outputs, backgroundColor: '#e94560', borderRadius: 4 },
        { label: 'Reasoning', data: reasonings, backgroundColor: '#ffc107', borderRadius: 4 },
      ],
    },
    options: {
      indexAxis: 'y',
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#a0a0b0', font: { size: 11 } } } },
      scales: {
        x: { stacked: true, ticks: { color: '#666680' }, grid: { color: '#2a2a4a' } },
        y: { stacked: true, ticks: { color: '#a0a0b0', font: { size: 11 } }, grid: { display: false } },
      },
      animation: { duration: 500 },
      layout: { padding: { right: 8 } },
    },
  });
}

function updateLatencyChart(latencyData) {
  const canvas = document.getElementById('latency-line-chart');
  if (!canvas || canvas.offsetParent === null) return;
  const ctx = canvas.getContext('2d');
  const timestamps = latencyData.map(d => new Date(d.timestamp).toLocaleTimeString());
  const durations = latencyData.map(d => d.duration_ms || 0);

  if (latencyChart) latencyChart.destroy();

  // Reset canvas dimensions to prevent drift
  canvas.style.width = '';
  canvas.style.height = '';

  latencyChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: timestamps,
      datasets: [{
        label: '工具调用延迟 (ms)',
        data: durations,
        borderColor: '#e94560',
        backgroundColor: 'rgba(233,69,96,0.1)',
        fill: true,
        tension: 0.3,
        pointRadius: 2,
      }],
    },
    options: {
      responsive: true,
      maintainAspectRatio: false,
      plugins: { legend: { labels: { color: '#a0a0b0', font: { size: 11 } } } },
      scales: {
        x: { ticks: { color: '#666680', maxTicksLimit: 20 }, grid: { display: false } },
        y: { ticks: { color: '#666680' }, grid: { color: '#2a2a4a' } },
      },
      animation: { duration: 400 },
    },
  });
}

function updateCostChart(hourly) {
  var canvas = document.getElementById('cost-line-chart');
  if (!canvas || canvas.offsetParent === null) return;
  var ctx = canvas.getContext('2d');

  hourly = hourly || [];

  var labels = [];
  var costs = [];
  var cum = 0;
  var hasData = false;

  hourly.forEach(function (h) {
    var d = new Date(h.hour_bucket);
    labels.push(d.getHours() + ':00');
    cum += (h.inp || 0) * 0.000003 + (h.outp || 0) * 0.000015 + (h.reas || 0) * 0.000003;
    costs.push(parseFloat(cum.toFixed(4)));
    if (cum > 0) hasData = true;
  });

  // 如果今天没数据，也要渲染占位图，避免趋势概览中间卡片空白。
  if (!hasData && labels.length === 0) {
    var totalTokens = 0;
    var snapshot = window.lastSnapshot;
    if (snapshot) {
      totalTokens = snapshot.total_tokens_today || 0;
    }
    var estCost = totalTokens * 0.00001;
    labels = ['今天'];
    costs = [parseFloat(estCost.toFixed(4))];
  }

  if (costChart) costChart.destroy();
  canvas.style.width = '';
  canvas.style.height = '';

  costChart = new Chart(ctx, {
    type: 'line',
    data: {
      labels: labels,
      datasets: [{
        label: '累计成本 ($)',
        data: costs,
        borderColor: '#ffc107',
        backgroundColor: 'rgba(255,193,7,0.08)',
        fill: true, tension: 0.3, pointRadius: costs.length > 1 ? 2 : 5,
        borderWidth: 2,
      }],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      plugins: {
        legend: { labels: { color: '#a0a0b0', font: { size: 11 } } },
        tooltip: {
          callbacks: {
            label: function(ctx) { return '$' + ctx.raw; }
          }
        }
      },
      scales: {
        x: { ticks: { color: '#666680', maxTicksLimit: 12 }, grid: { display: false } },
        y: {
          ticks: { color: '#666680', callback: function(v) { return '$' + v; } },
          grid: { color: '#2a2a4a' },
        },
      },
      animation: { duration: 400 },
    },
  });
}
