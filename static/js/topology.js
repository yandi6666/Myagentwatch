/**
 * MyAgentWatch 2.0 — Force-Directed Topology Graph
 * D3 forceSimulation loads→stops. No continuous animation.
 * Aggregate mode: group by source, double-click to expand.
 * Node: shape=source, radius=tokens, color=status, glow=thinking.
 * Edge: thickness=call_freq, dashed=parent-child.
 */
(function () {
  const TOPO = {};

  function _radius(d) {
    if (d.is_collapse_handle) return 12;
    if (d.is_aggregate) {
      return Math.min(18 + (d.child_count || 1) * 3, 55);
    }
    return Math.min(Math.max(8 + (d.tokens_total || 0) / 1000, 6), 40);
  }

  const KNOWN_SOURCES = ['main-opencode', 'claude-code', 'system'];

  function _resolveSource(id) {
    // Accept bare source name (e.g. 'claude-code') or agent id (e.g. 'claude-code:agent:model')
    if (!id) return 'other';
    if (KNOWN_SOURCES.indexOf(id) >= 0) return id;
    const idx = id.indexOf(':');
    if (idx < 0) return 'other';
    return id.substring(0, idx);
  }

  function _sourceColor(id) {
    const src = _resolveSource(id);
    const colors = { 'main-opencode': '#4ade80', 'claude-code': '#c084fc', 'system': '#60a5fa' };
    return colors[src] || '#6b7280';
  }

  function _sourceLabel(id) {
    const src = _resolveSource(id);
    const labels = { 'main-opencode': 'OC', 'claude-code': 'CC', 'system': 'SYS' };
    return labels[src] || '';
  }

  function _sourceDisplayName(id) {
    const src = _resolveSource(id);
    const names = { 'main-opencode': 'OpenCode', 'claude-code': 'Claude Code', 'system': 'System' };
    return names[src] || src;
  }

  function _shapePath(r, id) {
    const src = _resolveSource(id);
    switch (src) {
      case 'claude-code':
        return 'M 0,' + (-r) + ' L ' + r + ',0 L 0,' + r + ' L ' + (-r) + ',0 Z';
      case 'system':
        return 'M 0,' + (-r) + ' L ' + r + ',' + (r * 0.75) + ' L ' + (-r) + ',' + (r * 0.75) + ' Z';
      case 'main-opencode': {
        const pts = [];
        for (let i = 0; i < 6; i++) {
          const a = i * Math.PI / 3 - Math.PI / 2;
          pts.push((r * Math.cos(a)).toFixed(1) + ',' + (r * Math.sin(a)).toFixed(1));
        }
        return 'M ' + pts.join(' L ') + ' Z';
      }
      default:
        return 'M 0,' + (-r) + ' A ' + r + ',' + r + ' 0 1,1 0,' + r + ' A ' + r + ',' + r + ' 0 1,1 0,' + (-r) + ' Z';
    }
  }

  // ── Aggregate / Expand logic ──
  function _dominantStatus(children) {
    const counts = {};
    children.forEach(function (c) {
      const s = c.status || 'offline';
      counts[s] = (counts[s] || 0) + 1;
    });
    let best = 'offline', bestN = 0;
    for (var k in counts) { if (counts[k] > bestN) { best = k; bestN = counts[k]; } }
    return best;
  }

  function _buildAggregateTopo(nData, eData) {
    // Group nodes by source
    const groups = {};
    nData.forEach(function (n) {
      const src = _resolveSource(n.id);
      if (!groups[src]) groups[src] = [];
      groups[src].push(n);
    });

    // Build aggregate nodes
    const aggNodes = [];
    const sourceKeys = Object.keys(groups).sort();
    sourceKeys.forEach(function (src) {
      const children = groups[src];
      aggNodes.push({
        id: 'agg:' + src,
        name: _sourceDisplayName(src),
        display_name: _sourceDisplayName(src),
        group_name: '按来源聚合',
        group: '按来源聚合',
        source: src,
        is_aggregate: true,
        children: children,
        child_count: children.length,
        tokens_total: children.reduce(function (s, c) { return s + (c.tokens_total || 0); }, 0),
        cost: children.reduce(function (s, c) { return s + (c.cost || 0); }, 0),
        status: _dominantStatus(children),
        configured: true,
        model_id: children.length + ' Agent',
        last_seen_time: Math.max.apply(null, children.map(function (c) { return c.last_seen_time || 0; })),
      });
    });

    // Aggregate edges: one edge per cross-source connection
    const edgeMap = {};
    eData.forEach(function (e) {
      const srcA = _resolveSource(e.source.id);
      const srcB = _resolveSource(e.target.id);
      if (srcA === srcB) return; // internal edges hidden in aggregate
      const key = srcA < srcB ? srcA + '↔' + srcB : srcB + '↔' + srcA;
      if (!edgeMap[key]) edgeMap[key] = { source: srcA, target: srcB, call_count: 0, parent_child: true };
      edgeMap[key].call_count += e.call_count || 1;
    });

    const aggEdges = [];
    const aggById = {};
    aggNodes.forEach(function (n) { aggById[n.id] = n; });
    for (var k in edgeMap) {
      var em = edgeMap[k];
      var sNode = aggById['agg:' + em.source];
      var tNode = aggById['agg:' + em.target];
      if (sNode && tNode) {
        aggEdges.push({ source: sNode, target: tNode, call_count: em.call_count, parent_child: true });
      }
    }

    return { nodes: aggNodes, edges: aggEdges };
  }

  function _buildExpandedTopo(st) {
    // Start from aggregate, then expand selected sources.
    // Expanded sources keep a small "collapse handle" so users can fold back.
    var agg = _buildAggregateTopo(st.rawNodes, st.rawEdges);
    var nodes = [];
    var edges = [];
    var expandedSrcs = st.expandedSources || new Set();

    agg.nodes.forEach(function (an) {
      if (expandedSrcs.has(an.source)) {
        // Add collapse handle (small ghost of the aggregate node)
        nodes.push({
          id: an.id,
          name: an.name,
          display_name: '收拢 ' + an.display_name,
          group_name: an.group_name,
          group: an.group_name,
          source: an.source,
          is_collapse_handle: true,
          collapse_source: an.source,
          child_count: an.child_count,
          tokens_total: an.tokens_total,
          cost: an.cost,
          status: 'offline',
          configured: true,
          model_id: an.model_id,
          last_seen_time: an.last_seen_time,
        });
        // Add children
        nodes = nodes.concat(an.children.map(function (c) { return Object.assign({}, c); }));
      } else {
        nodes.push(an);
      }
    });

    // Build edge set
    var nodeById = {};
    nodes.forEach(function (n) { nodeById[n.id] = n; });

    // Original edges between expanded children
    st.rawEdges.forEach(function (e) {
      var sid = typeof e.source === 'object' ? e.source.id : e.source;
      var tid = typeof e.target === 'object' ? e.target.id : e.target;
      if (nodeById[sid] && nodeById[tid] && !nodeById[sid].is_collapse_handle && !nodeById[tid].is_collapse_handle) {
        edges.push({
          source: nodeById[sid],
          target: nodeById[tid],
          call_count: e.call_count || 0,
          parent_child: e.parent_child,
        });
      }
    });

    // Aggregate cross-edges for non-expanded + collapse handles
    agg.edges.forEach(function (ae) {
      var sid = typeof ae.source === 'object' ? ae.source.id : ae.source;
      var tid = typeof ae.target === 'object' ? ae.target.id : ae.target;
      if (nodeById[sid] && nodeById[tid]) {
        edges.push({
          source: nodeById[sid],
          target: nodeById[tid],
          call_count: ae.call_count || 0,
          parent_child: ae.parent_child,
        });
      }
    });

    return { nodes: nodes, edges: edges };
  }

  function _computeView(st) {
    if (st.expandedSources && st.expandedSources.size > 0) {
      return _buildExpandedTopo(st);
    }
    return _buildAggregateTopo(st.rawNodes, st.rawEdges);
  }

  // ── Init ──
  function _init(svgId) {
    if (TOPO[svgId]) return TOPO[svgId];
    const svg = d3.select('#' + svgId);
    if (svg.empty()) return null;
    const ct = svg.node().parentElement;
    const W = ct.clientWidth || 800, H = ct.clientHeight || 500;
    svg.attr('viewBox', '0 0 ' + W + ' ' + H);
    const g = svg.append('g');
    svg.call(d3.zoom().scaleExtent([0.3, 3])
      .filter(event => !event.target.closest('.topo-node'))
      .on('zoom', e => g.attr('transform', e.transform)));
    const sim = d3.forceSimulation([]).force('link', d3.forceLink([]).id(d => d.id).distance(140))
      .force('charge', d3.forceManyBody().strength(-400))
      .force('center', d3.forceCenter(W / 2, H / 2))
      .force('collide', d3.forceCollide().radius(d => _radius(d) + 6))
      .force('x', d3.forceX(W / 2).strength(0.05))
      .alphaDecay(0.04).velocityDecay(0.35);
    // Double-click background → collapse all
    svg.on('dblclick', function () {
      if (TOPO[svgId] && TOPO[svgId].expandedSources && TOPO[svgId].expandedSources.size > 0) {
        TOPO[svgId].expandedSources = new Set();
        _redraw(svgId);
      }
    });
    if (svgId === 'topo-svg') {
      svg.on('click', function () { if (typeof clearNodeDetail === 'function') clearNodeDetail(); });
    }
    const st = { svg, g, sim, W, H, tickBound: false, nodeIds: new Set(), tip: null,
      expandedSources: new Set(), rawNodes: [], rawEdges: [], aggregate: true };
    TOPO[svgId] = st;
    st.tip = d3.select('body').append('div')
      .attr('class', 'topo-tooltip')
      .style('position', 'fixed').style('pointer-events', 'none')
      .style('padding', '4px 10px').style('background', 'rgba(0,0,0,0.85)')
      .style('color', '#e8e8f0').style('border-radius', '4px')
      .style('font-size', '12px').style('opacity', 0).style('z-index', 9999)
      .style('transform', 'translate(-50%,-120%)');
    return st;
  }

  // ── Simulation step ──
  function _updateSimulation(st, nData, eData) {
    const { sim, W, H, nodeIds } = st;
    const newIds = new Set(nData.map(function (n) { return n.id; }));
    let changed = newIds.size !== nodeIds.size;
    if (!changed) {
      newIds.forEach(function (id) { if (!nodeIds.has(id)) changed = true; });
      if (!changed) nodeIds.forEach(function (id) { if (!newIds.has(id)) changed = true; });
    }
    st.nodeIds = newIds;

    const posMap = {};
    sim.nodes().forEach(function (sn) { posMap[sn.id] = { x: sn.x, y: sn.y }; });
    nData.forEach(function (n) {
      const old = posMap[n.id];
      n.x = old ? old.x : W / 2 + (Math.random() - 0.5) * 100;
      n.y = old ? old.y : H / 2 + (Math.random() - 0.5) * 100;
      n.vx = 0; n.vy = 0;
    });

    const groupSet = new Set();
    nData.forEach(function (n) { groupSet.add(n.group || n.group_name || '默认'); });
    const groups = [];
    groupSet.forEach(function (g) { groups.push(g); });
    const groupX = {};
    const spacing = W / (groups.length + 1);
    groups.forEach(function (g, i) { groupX[g] = spacing * (i + 1); });
    sim.force('x', d3.forceX(function (d) {
      return groupX[d.group || d.group_name || '默认'] || W / 2;
    }).strength(0.08));

    if (changed || !st.initialized) {
      sim.nodes(nData).force('link').links(eData);
      sim.alpha(0.3).tick(300);
      sim.alpha(0).stop();
    } else {
      sim.nodes(nData);
    }
    if (!st.tickBound) {
      sim.on('tick', function () {
        st.g.selectAll('.topo-link').attr('x1', function (d) { return d.source.x; }).attr('y1', function (d) { return d.source.y; })
          .attr('x2', function (d) { return d.target.x; }).attr('y2', function (d) { return d.target.y; });
        st.g.selectAll('.topo-node').attr('transform', function (d) { return 'translate(' + d.x + ',' + d.y + ')'; });
      });
      st.tickBound = true;
    }
  }

  // ── Edge rendering ──
  function _renderEdges(st, eData) {
    const link = st.g.selectAll('.topo-link').data(eData, function (d) { return d.source.id + '→' + d.target.id; });
    link.exit().remove();
    link.enter().append('line').attr('class', function (d) { return 'topo-link' + (d.parent_child ? ' parent-child' : ''); });
    link.enter().merge(link).attr('stroke', '#60a5fa')
      .attr('stroke-width', function (d) { return Math.min(1 + (d.call_count || 0) / 20, 6); })
      .attr('stroke-opacity', function (d) { return Math.min(0.3 + (d.call_count || 0) / 100, 0.8); })
      .attr('x1', function (d) { return d.source.x; }).attr('y1', function (d) { return d.source.y; })
      .attr('x2', function (d) { return d.target.x; }).attr('y2', function (d) { return d.target.y; });
  }

  // ── Node rendering ──
  function _renderNodes(st, nData, agentLookup) {
    const sel = st.g.selectAll('.topo-node').data(nData, function (d) { return d.id; });
    sel.exit().remove();
    const enter = sel.enter().append('g')
      .attr('class', function (d) {
        var cls = 'topo-node src-' + (d.source || _resolveSource(d.id));
        if (d.is_aggregate) cls += ' aggregate';
        if (d.is_collapse_handle) cls += ' collapse-handle';
        if (d.status === 'thinking') cls += ' thinking';
        return cls;
      })
      .call(d3.drag()
        .on('start', function () { d3.select(this).raise(); })
        .on('drag', function (e, d) {
          if (d.is_collapse_handle) return; // collapse handles are fixed
          d.x = e.x; d.y = e.y;
          d3.select(this).attr('transform', 'translate(' + e.x + ',' + e.y + ')');
          st.g.selectAll('.topo-link').each(function (le) {
            if (le.source.id === d.id || le.target.id === d.id)
              d3.select(this).attr('x1', le.source.x).attr('y1', le.source.y)
                .attr('x2', le.target.x).attr('y2', le.target.y);
          });
        }));
    enter.append('path').attr('opacity', 0.92);
    enter.append('text').attr('class', 'topo-label');

    const all = enter.merge(sel)
      .attr('class', function (d) {
        var cls = 'topo-node src-' + (d.source || _resolveSource(d.id));
        if (d.is_aggregate) cls += ' aggregate';
        if (d.is_collapse_handle) cls += ' collapse-handle';
        if (d.status === 'thinking') cls += ' thinking';
        return cls;
      })
      .attr('transform', function (d) { return 'translate(' + d.x + ',' + d.y + ')'; })
      .on('mouseenter', function (e, d) {
        var r = _radius(d) + 5;
        d3.select(this).select('path').transition().duration(150)
          .attr('d', _shapePath(r, d.source || d.id));
        var tipHtml;
        if (d.is_collapse_handle) {
          tipHtml = '<b>收拢</b><br><span style="color:#888;">' + (d.display_name || d.name) + ' (' + d.child_count + ' Agent)</span>';
        } else if (d.is_aggregate) {
          tipHtml = '<b>' + (d.display_name || d.name) + '</b><br><span style="color:#888;">' + d.child_count + ' Agent · 单击展开</span>';
        } else {
          tipHtml = (d.display_name || d.name) + ' <span style="color:#888;">[' + _sourceDisplayName(d.id) + ']</span>';
        }
        st.tip.style('opacity', 1).html(tipHtml)
          .style('left', (e.pageX + 10) + 'px').style('top', (e.pageY - 10) + 'px');
      })
      .on('mousemove', function (e) {
        st.tip.style('left', (e.pageX + 10) + 'px').style('top', (e.pageY - 10) + 'px');
      })
      .on('mouseleave', function (e, d) {
        var r = _radius(d);
        d3.select(this).select('path').transition().duration(150)
          .attr('d', _shapePath(r, d.source || d.id));
        st.tip.style('opacity', 0);
      });

    all.select('path')
      .attr('d', function (d) {
        if (d.is_collapse_handle) {
          var r = _radius(d);
          return 'M 0,' + (-r) + ' A ' + r + ',' + r + ' 0 1,1 0,' + r + ' A ' + r + ',' + r + ' 0 1,1 0,' + (-r) + ' Z';
        }
        return _shapePath(_radius(d), d.source || d.id);
      })
      .attr('fill', function (d) {
        if (d.is_collapse_handle) return 'rgba(255,255,255,0.06)';
        return STATUS_COLORS[d.status] || STATUS_COLORS.unknown;
      })
      .attr('stroke', function (d) {
        if (d.is_collapse_handle) return _sourceColor(d.source);
        if (d.configured === false) return '#6b7280';
        return _sourceColor(d.source || d.id);
      })
      .attr('stroke-width', function (d) { return d.is_collapse_handle ? 1.5 : (d.is_aggregate ? 3.5 : (d.configured === false ? 2 : 3)); })
      .attr('stroke-dasharray', function (d) {
        if (d.is_collapse_handle) return '3 3';
        if (d.configured === false) return '4 2';
        return null;
      })
      .attr('opacity', function (d) { return d.is_collapse_handle ? 0.5 : 0.92; })
      .on('click', function (e, d) {
        e.stopPropagation();
        if (d.is_collapse_handle) {
          _toggleSource(st, d.collapse_source);
        } else if (d.is_aggregate) {
          _toggleSource(st, d.source);
        } else {
          var dt = agentLookup[d.name] || agentLookup[d.id] || d;
          if (typeof showNodeDetail === 'function') showNodeDetail(dt);
        }
      })
      .on('dblclick', function (e, d) {
        e.stopPropagation();
        if (d.is_aggregate || d.is_collapse_handle) {
          _toggleSource(st, d.collapse_source || d.source);
        }
      });

    all.select('text').attr('dy', function (d) { return _radius(d) + 14; }).text(function (d) {
      if (d.is_collapse_handle) {
        return '− 收拢';
      }
      if (d.is_aggregate) {
        return (d.display_name || d.name) + ' (' + d.child_count + ')';
      }
      var lbl = _sourceLabel(d.id);
      return (d.display_name || d.name || '') + (lbl ? ' [' + lbl + ']' : '');
    });
  }

  function _toggleSource(st, src) {
    if (!st.expandedSources) st.expandedSources = new Set();
    if (st.expandedSources.has(src)) {
      st.expandedSources.delete(src);
    } else {
      st.expandedSources.add(src);
    }
    _redrawFromState(st);
  }

  function _redrawFromState(st) {
    var view = _computeView(st);
    var nData = view.nodes;
    var nodeById = {};
    nData.forEach(function (n) { nodeById[n.id] = n; });
    var eData = view.edges.filter(function (e) {
      var sid = typeof e.source === 'object' ? e.source.id : e.source;
      var tid = typeof e.target === 'object' ? e.target.id : e.target;
      return nodeById[sid] && nodeById[tid];
    }).map(function (e) {
      var sid = typeof e.source === 'object' ? e.source.id : e.source;
      var tid = typeof e.target === 'object' ? e.target.id : e.target;
      return { source: nodeById[sid], target: nodeById[tid], call_count: e.call_count || 0, parent_child: e.parent_child };
    });
    var agentLookup = {};
    (window.lastSnapshot?.agents || []).forEach(function (a) { agentLookup[a.name] = a; agentLookup[a.id] = a; });
    _updateSimulation(st, nData, eData);
    _renderEdges(st, eData);
    _renderNodes(st, nData, agentLookup);
    st.initialized = true;
  }

  function _redraw(svgId) {
    var st = TOPO[svgId];
    if (!st || !st.rawNodes.length) return;
    _redrawFromState(st);
  }

  function _draw(svgId, topo, snapshot) {
    var st = _init(svgId);
    if (!st) return;

    // Always store raw data
    st.rawNodes = (topo.nodes || []).map(function (n) { return Object.assign({}, n); });
    st.rawEdges = (topo.edges || []).map(function (e) { return Object.assign({}, e); });

    // Auto-mode: aggregate if > 8 nodes, unless user has explicitly expanded
    if (st.rawNodes.length <= 8 && st.expandedSources.size === 0) {
      // Small topology: expand all
      var allSrcs = new Set();
      st.rawNodes.forEach(function (n) { allSrcs.add(_resolveSource(n.id)); });
      st.expandedSources = allSrcs;
    }

    var agentLookup = {};
    (snapshot?.agents || []).forEach(function (a) { agentLookup[a.name] = a; agentLookup[a.id] = a; });

    _redrawFromState(st);
    st.initialized = true;
  }

  window.renderTopology = function (s) {
    if (!s?.topology) return;
    _draw('topo-svg', s.topology, s);
  };
  window.renderTopologyFull = function (s) {
    var t = s?.topology || window.lastTopoData;
    if (!t) return;
    _draw('topo-full-svg', t, s || window.lastSnapshot || {});
  };
})();
