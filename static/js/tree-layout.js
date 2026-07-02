/**
 * MyAgentWatch 3.0 — Deterministic Tree Layout (Buchheim / improved Reingold-Tilford).
 * Produces stable (x,y) positions for a tree. No force simulation, no jitter.
 *
 * Exports: computeTreeLayout(roots, options) → { nodes: [{id,x,y,data}], edges: [...] }
 */
(function () {
  const CFG = {
    nodeWidth: 300,
    nodeHeight: 110,
    siblingGap: 20,
    levelGap: 100,
    direction: 'LR', // LR = left→right, TB = top→bottom
  };

  function configure(opts) {
    if (opts.nodeWidth) CFG.nodeWidth = opts.nodeWidth;
    if (opts.nodeHeight) CFG.nodeHeight = opts.nodeHeight;
    if (opts.siblingGap) CFG.siblingGap = opts.siblingGap;
    if (opts.levelGap) CFG.levelGap = opts.levelGap;
    if (opts.direction) CFG.direction = opts.direction;
  }

  // ── Pass 1: measure subtree widths (bottom-up) ──
  function measureSubtree(node, cache) {
    if (cache.has(node.id)) return cache.get(node.id);
    const children = node.children || [];
    if (children.length === 0) {
      cache.set(node.id, CFG.nodeWidth);
      return CFG.nodeWidth;
    }
    let total = 0;
    for (let i = 0; i < children.length; i++) {
      total += measureSubtree(children[i], cache);
    }
    total += CFG.siblingGap * Math.max(0, children.length - 1);
    const width = Math.max(CFG.nodeWidth, total);
    cache.set(node.id, width);
    return width;
  }

  // ── Pass 2: assign positions (top-down) ──
  function assignPositions(node, left, depth, positions, cache) {
    const subtreeWidth = measureSubtree(node, cache);
    const baseX = left + subtreeWidth / 2 - CFG.nodeWidth / 2;
    const baseY = depth * (CFG.nodeHeight + CFG.levelGap);

    positions.set(node.id, {
      x: CFG.direction === 'TB' ? baseX : baseY,
      y: CFG.direction === 'TB' ? baseY : baseX,
      depth: depth,
    });

    const children = node.children || [];
    let childLeft = left;
    for (let i = 0; i < children.length; i++) {
      const cw = measureSubtree(children[i], cache);
      assignPositions(children[i], childLeft, depth + 1, positions, cache);
      childLeft += cw + CFG.siblingGap;
    }
  }

  // ── Collect edges from tree ──
  function collectEdges(node, positions, result) {
    const children = node.children || [];
    for (let i = 0; i < children.length; i++) {
      const p = positions.get(node.id);
      const c = positions.get(children[i].id);
      if (p && c) {
        if (CFG.direction === 'TB') {
          result.push({
            source: { id: node.id, x: p.x + CFG.nodeWidth / 2, y: p.y + CFG.nodeHeight },
            target: { id: children[i].id, x: c.x + CFG.nodeWidth / 2, y: c.y },
            parent_child: true, call_count: 1,
          });
        } else {
          result.push({
            source: { id: node.id, x: p.x + CFG.nodeWidth, y: p.y + CFG.nodeHeight / 2 },
            target: { id: children[i].id, x: c.x, y: c.y + CFG.nodeHeight / 2 },
            parent_child: true, call_count: 1,
          });
        }
      }
      collectEdges(children[i], positions, result);
    }
  }

  // ── Main entry ──
  function computeTreeLayout(roots, opts) {
    if (opts) configure(opts);
    if (!roots || roots.length === 0) return { nodes: [], edges: [] };

    const cache = new Map();
    const positions = new Map();

    // Measure all roots first to compute their total width
    let totalRootWidth = 0;
    for (let i = 0; i < roots.length; i++) {
      totalRootWidth += measureSubtree(roots[i], cache);
    }
    totalRootWidth += CFG.siblingGap * Math.max(0, roots.length - 1);

    // Place roots centered around x=0, sequentially
    let rootLeft = -totalRootWidth / 2;
    for (let i = 0; i < roots.length; i++) {
      const rw = measureSubtree(roots[i], cache);
      assignPositions(roots[i], rootLeft, 0, positions, cache);
      rootLeft += rw + CFG.siblingGap;
    }

    // Flatten into nodes array
    const nodes = [];
    const walk = function (node) {
      const pos = positions.get(node.id);
      if (pos) {
        nodes.push({
          id: node.id,
          x: pos.x,
          y: pos.y,
          data: node,
        });
      }
      (node.children || []).forEach(walk);
    };
    roots.forEach(walk);

    // Collect edges
    const edges = [];
    roots.forEach(function (r) { collectEdges(r, positions, edges); });

    return { nodes: nodes, edges: edges };
  }

  window.computeTreeLayout = computeTreeLayout;
  window.configureTreeLayout = configure;
})();
