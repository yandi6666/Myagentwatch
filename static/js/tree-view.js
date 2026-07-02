/**
 * MyAgentWatch 3.1 — Tree View
 * Three-level tree: Root → 主agent (groups) → 子agent (agents)
 * With node dragging + pen drawing tool.
 */
(function () {
  const TV = {};
  let focusedNodeId = null;
  let penActive = false;
  let penPath = null;
  let penPoints = [];
  let penPaths = [];  // saved drawing paths
  const CARD_W = 280, CARD_H = 88;
  const BRANCH_COLORS = ['#ef6b6b', '#f56c42', '#5dc49b', '#60a5fa', '#c084fc'];

  function resolveSource(id) {
    if (!id) return 'unknown';
    var idx = id.indexOf(':');
    return idx < 0 ? 'unknown' : id.substring(0, idx);
  }

  function dot(s) {
    if (s === 'active')  return '<span class="tv-dot active"></span>';
    if (s === 'idle' || s === 'inactive') return '<span class="tv-dot idle"></span>';
    if (s === 'error')  return '<span class="tv-dot error"></span>';
    if (s === 'offline') return '<span class="tv-dot offline"></span>';
    return '<span class="tv-dot offline"></span>';
  }
  function slabel(s) {
    if (s === 'active')  return '在线';
    if (s === 'idle' || s === 'inactive') return '空闲';
    if (s === 'error')  return '错误';
    if (s === 'offline') return '离线';
    return '离线';
  }
  function esc(s) {
    s = String(s || '');
    return s.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
  }

  // ── Build tree ──
  function buildDesignTree(snapshot) {
    var agents = snapshot.agents || [];
    if (!agents.length) return null;

    var groups = {};
    agents.forEach(function (a) {
      var g = a.group_name || a.group || '默认';
      if (!groups[g]) groups[g] = [];
      groups[g].push(a);
    });

    var ci = 0;
    var root = {
      id: 'root', type: 'root', display_name: 'MyAgentWatch',
      status: 'active', model_id: '', source: 'system', branch_color: '', children: [],
    };

    var gnames = Object.keys(groups);
    for (var i = 0; i < gnames.length; i++) {
      var gname = gnames[i];
      var gagents = groups[gname];
      var branchColor = BRANCH_COLORS[ci % BRANCH_COLORS.length];

      root.children.push({
        id: 'group-' + gname, type: 'group', display_name: '主 agent',
        status: 'active', model_id: '', source: 'system',
        branch_color: branchColor,
        children: gagents.map(function (a) {
          return {
            id: a.id, type: 'agent',
            display_name: a.display_name || a.name,
            group_name: gname,
            agent_type: a.agent_type || '',
            source: resolveSource(a.id),
            model_id: a.model_id || '',
            status: a.status || 'offline',
            tokens_input: a.tokens_input || 0,
            tokens_output: a.tokens_output || 0,
            cache_read: a.cache_read || 0,
            cache_write: a.cache_write || 0,
            cost: a.cost || 0, tokens_total: a.tokens_total || 0,
            latency_ms: a.latency_ms || 0,
            tool_name: a.tool_name || '',
            tool_status: a.tool_status || '',
            current_action: a.current_action || '',
            last_seen_time: a.last_seen_time || 0,
            branch_color: branchColor,
            children: [],
          };
        }),
      });
      ci++;
    }

    root.children.push({
      id: 'ellipsis', type: 'ellipsis', display_name: '.........',
      status: 'active', model_id: '', source: 'system',
      branch_color: '#9ca3af', children: [],
    });

    return { roots: [root] };
  }

  // ── Card HTML ──
  function cardHTML(d) {
    var data = d.data || d;
    var bc = data.branch_color || '#6b7280';
    var isRoot = data.type === 'root';
    var isEllipsis = data.type === 'ellipsis';
    var isGroup = data.type === 'group';

    if (isRoot) {
      return '<div class="tv-card tv-card-root">'
        + '<div class="tv-root-label">' + esc(data.display_name) + '</div>'
        + '</div>';
    }

    if (isEllipsis) {
      return '<div class="tv-card-ellipsis">'
        + '<span>' + esc(data.display_name) + '</span>'
        + '</div>';
    }

    var title = isGroup ? '主 agent' : '子 agent';

    return '<div class="tv-card' + (focusedNodeId && focusedNodeId !== data.id ? ' tv-dimmed' : '') + '"'
      + ' style="border-top:4px solid ' + bc + ';">'
      + '<div class="tv-card-body">'
      + '<div class="tv-card-title">' + title + '</div>'
      + '<div class="tv-card-desc">要求：要显示运行正常，agent状态，等等</div>'
      + '<div class="tv-card-status">'
      + '<span class="tv-status-item">' + dot('active') + '在线</span>'
      + '<span class="tv-status-item">' + dot('idle') + '等待</span>'
      + '<span class="tv-status-item">' + dot('error') + '错误</span>'
      + '<span class="tv-status-item">' + dot('offline') + '离线</span>'
      + '</div>'
      + '</div>'
      + '</div>';
  }

  // ── Init SVG ──
  function init(svgId) {
    if (TV[svgId] && TV[svgId].g) return TV[svgId];
    var svg = d3.select('#' + svgId);
    if (svg.empty()) return null;
    var ct = svg.node().parentElement;
    var W = ct.clientWidth || 1000, H = ct.clientHeight || 600;
    svg.attr('viewBox', '0 0 ' + W + ' ' + H);

    var zoomG = svg.append('g').attr('class', 'tv-zoom-g');
    var contentG = zoomG.append('g').attr('class', 'tv-content-g');
    // Pen drawing layer (on top of content, inside zoom)
    var penG = zoomG.append('g').attr('class', 'tv-pen-g');

    var zoom = d3.zoom().scaleExtent([0.2, 2.5])
      .filter(function (e) {
        if (penActive) return e.type === 'wheel';
        return !e.target.closest('.tv-card');
      })
      .on('zoom', function (e) { zoomG.attr('transform', e.transform); });

    svg.call(zoom);

    // Pen drawing handlers (on SVG directly for coordinate consistency)
    svg.on('mousedown.tvpen', function (e) {
      if (!penActive) return;
      if (e.target.closest('.tv-card')) return;
      var pt = d3.point(e, zoomG.node());
      penPoints = [pt];
      penPath = penG.append('path').attr('class', 'tv-pen-path')
        .attr('stroke', '#ef4444').attr('stroke-width', 2.5)
        .attr('fill', 'none').attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
    });

    svg.on('mousemove.tvpen', function (e) {
      if (!penActive || !penPath) return;
      var pt = d3.point(e, zoomG.node());
      penPoints.push(pt);
      penPath.attr('d', d3.line()(penPoints));
    });

    svg.on('mouseup.tvpen', function (e) {
      if (!penActive || !penPath) return;
      penPaths.push(penPoints);
      penPath = null; penPoints = [];
    });

    svg.on('click', function (e) {
      if (penActive) return;
      if (e.target === svg.node() || String(e.target.tagName).toLowerCase() === 'svg') {
        clearFocus();
      }
    });

    var st = { svg: svg, zoomG: zoomG, g: contentG, penG: penG, W: W, H: H, zoom: zoom };
    TV[svgId] = st;
    return st;
  }

  // ── Bezier path ──
  function bezierPath(sx, sy, tx, ty) {
    var mx = (sx + tx) / 2;
    return 'M ' + sx + ' ' + sy + ' Q ' + mx + ' ' + sy + ' ' + mx + ' ' + ty
      + ' Q ' + mx + ' ' + ty + ' ' + tx + ' ' + ty;
  }

  // ── Draw ──
  function draw(svgId, treeData) {
    var st = init(svgId);
    if (!st) return;

    st.g.selectAll('*').remove();

    if (!treeData || !treeData.roots || treeData.roots.length === 0) {
      st.g.append('text').attr('x', st.W / 2).attr('y', st.H / 2)
        .attr('text-anchor', 'middle').attr('fill', '#9ca3af').attr('font-size', '14px')
        .text('等待 Agent 数据...');
      return;
    }

    var layout = computeTreeLayout(treeData.roots, {
      nodeWidth: CARD_W, nodeHeight: CARD_H,
      siblingGap: 24, levelGap: 80, direction: 'LR',
    });
    if (!layout.nodes.length) return;

    var nodeMap = {};
    layout.nodes.forEach(function (n) { nodeMap[n.id] = n; });

    // Compute bounds
    var minX = Infinity, maxX = -Infinity, minY = Infinity, maxY = -Infinity;
    layout.nodes.forEach(function (n) {
      var w = n.data.type === 'root' ? 200 : (n.data.type === 'ellipsis' ? 80 : CARD_W);
      var h = n.data.type === 'root' ? 60 : (n.data.type === 'ellipsis' ? 30 : CARD_H);
      if (n.x < minX) minX = n.x;
      if (n.x + w > maxX) maxX = n.x + w;
      if (n.y < minY) minY = n.y;
      if (n.y + h > maxY) maxY = n.y + h;
    });
    var midX = (minX + maxX) / 2, midY = (minY + maxY) / 2;
    st.g.attr('transform', 'translate(' + (st.W / 2 - midX) + ',' + (st.H / 2 - midY) + ')');

    // Redraw pen paths
    st.penG.selectAll('*').remove();
    penPaths.forEach(function (pts) {
      if (pts.length > 1) {
        st.penG.append('path').attr('class', 'tv-pen-path')
          .attr('d', d3.line()(pts))
          .attr('stroke', '#ef4444').attr('stroke-width', 2.5)
          .attr('fill', 'none').attr('stroke-linecap', 'round').attr('stroke-linejoin', 'round');
      }
    });

    // ── Edges ──
    var edgeSel = st.g.selectAll('.tv-edge').data(layout.edges, function (d) {
      return d.source.id + '->' + d.target.id;
    });
    edgeSel.exit().remove();
    edgeSel.enter().append('path').attr('class', 'tv-edge');
    edgeSel
      .attr('d', function (d) {
        return bezierPath(d.source.x, d.source.y, d.target.x, d.target.y);
      })
      .attr('stroke', function (d) {
        var src = nodeMap[d.source.id];
        var tgt = nodeMap[d.target.id];
        if (src && src.data.type === 'root') {
          return (tgt && tgt.data.branch_color) ? tgt.data.branch_color : '#d1d5db';
        }
        return '#374151';
      })
      .attr('stroke-width', function (d) {
        var src = nodeMap[d.source.id];
        return (src && src.data.type === 'root') ? 2.5 : 1.2;
      });

    // ── Nodes with drag ──
    var nodeSel = st.g.selectAll('.tv-node').data(layout.nodes, function (d) { return d.id; });
    nodeSel.exit().remove();

    // Drag behavior
    function dragged(e, d) {
      d.x = e.x; d.y = e.y;
      d3.select(this).attr('transform', 'translate(' + d.x + ',' + d.y + ')');
      // Update edges connected to this node
      layout.edges.forEach(function (edge) {
        if (edge.source.id === d.id) {
          edge.source.x = d.x + (d.data.type === 'root' ? 200 : CARD_W);
          edge.source.y = d.y + (d.data.type === 'root' ? 30 : CARD_H / 2);
        }
        if (edge.target.id === d.id) {
          edge.target.x = d.x;
          edge.target.y = d.y + (d.data.type === 'root' ? 30 : CARD_H / 2);
        }
      });
      st.g.selectAll('.tv-edge')
        .attr('d', function (ed) {
          return bezierPath(ed.source.x, ed.source.y, ed.target.x, ed.target.y);
        });
    }

    var drag = d3.drag()
      .filter(function (e) { return !penActive; })
      .on('drag', dragged);

    var enter = nodeSel.enter().append('g')
      .attr('class', 'tv-node')
      .attr('transform', function (d) { return 'translate(' + d.x + ',' + d.y + ')'; })
      .on('click', function (e, d) {
        if (penActive) return;
        e.stopPropagation();
        if (d.data.type !== 'root' && d.data.type !== 'ellipsis') toggleFocus(d.id);
      })
      .call(drag);

    enter.append('foreignObject')
      .attr('width', function (d) {
        if (d.data.type === 'root') return 200;
        if (d.data.type === 'ellipsis') return 80;
        return CARD_W;
      })
      .attr('height', function (d) {
        if (d.data.type === 'root') return 60;
        if (d.data.type === 'ellipsis') return 30;
        return CARD_H;
      })
      .attr('x', 0).attr('y', 0)
      .html(function (d) { return cardHTML(d); });

    nodeSel.attr('transform', function (d) { return 'translate(' + d.x + ',' + d.y + ')'; });
    if (!nodeSel.empty()) {
      nodeSel.select('foreignObject').html(function (d) { return cardHTML(d); });
    }

    st.lastLayout = layout;
    st.lastTreeData = treeData;
  }

  // ── Focus ──
  function toggleFocus(nodeId) {
    if (focusedNodeId === nodeId) { clearFocus(); return; }
    focusedNodeId = nodeId;
    refreshAll();
    updateFocusDetail(nodeId);
  }
  function clearFocus() {
    if (!focusedNodeId) return;
    focusedNodeId = null;
    refreshAll();
    if (typeof clearNodeDetail === 'function') clearNodeDetail();
  }
  function updateFocusDetail(nodeId) {
    var st = TV['topo-svg'];
    if (!st || !st.lastLayout) return;
    var found = null;
    st.lastLayout.nodes.forEach(function (n) { if (n.id === nodeId) found = n; });
    if (found && typeof showNodeDetail === 'function') showNodeDetail(found.data);
  }
  function refreshAll() {
    for (var k in TV) {
      var st = TV[k];
      if (st && st.g && st.lastTreeData) draw(k, st.lastTreeData);
    }
  }

  // ── Pen toolbar ──
  function bindToolbar() {
    var btnPen = document.getElementById('btn-pen');
    var btnClear = document.getElementById('btn-pen-clear');
    if (btnPen && !btnPen._bound) {
      btnPen._bound = true;
      btnPen.addEventListener('click', function () {
        penActive = !penActive;
        btnPen.classList.toggle('active', penActive);
        btnPen.style.background = penActive ? 'var(--accent)' : '';
        btnPen.style.color = penActive ? '#fff' : '';
      });
    }
    if (btnClear && !btnClear._bound) {
      btnClear._bound = true;
      btnClear.addEventListener('click', function () {
        penPaths = [];
        refreshAll();
      });
    }
  }

  // ── Public API ──
  window.renderTreeView = function (treeData) {
    if (!treeData) return;
    draw('topo-svg', treeData);
  };

  window.renderTopology = function (snapshot) {
    if (!snapshot) return;
    var tree = buildDesignTree(snapshot);
    if (tree) {
      window.lastTreeData = tree;
      draw('topo-svg', tree);
      bindToolbar();
    }
  };

  window.renderTopologyFull = function (snapshot) {
    var tree = buildDesignTree(snapshot);
    if (tree) {
      window.lastTreeData = tree;
      draw('topo-full-svg', tree);
      bindToolbar();
    }
  };
})();
