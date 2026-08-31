"use strict";

// ============================================================
// State
// ============================================================
const state = {
  nodes: {},           // node_id → {type, position, links}
  nodeMetrics: {},     // node_id → {tput_mbps, ...}
  selectedNode: null,
  simStatus: "stopped",
  nowUs: 0,
  replayMode: false,
};

// ============================================================
// Socket Manager
// ============================================================
const socket = io();

socket.on("connect",    () => console.log("[WS] connected"));
socket.on("disconnect", () => setBadge("stopped"));

socket.on("sim:status", d => {
  state.simStatus = d.status;
  state.nowUs = d.now_us || 0;
  setBadge(d.status);
  updateClock(d.now_us || 0);
});

socket.on("sim:tick", d => {
  updateClock(d.now_us);
});

socket.on("tx:event", d => {
  ThroughputPanel.recordTx(d);
  TopologyPanel.setLinkState(d.node_id, d.link_id, "TRANSMITTING");
});

socket.on("link:state", d => {
  TopologyPanel.setLinkState(d.node_id, d.link_id, d.state);
  if (state.selectedNode === d.node_id) NodeDetailPanel.refresh();
});

socket.on("metrics:sample", d => {
  state.nodeMetrics[d.node_id] = d;
  ThroughputPanel.addSample(d.node_id, d.throughput_mbps || 0, d.time_us || 0);
  if (state.selectedNode === d.node_id) NodeDetailPanel.refresh();
});

socket.on("log:line", d => {
  LogPanel.append(d);
});

socket.on("node:added", d => {
  state.nodes[d.node_id] = d;
  TopologyPanel.redraw();
  refreshNodeDropdowns();
});

socket.on("node:removed", d => {
  delete state.nodes[d.node_id];
  if (state.selectedNode === d.node_id) {
    state.selectedNode = null;
    NodeDetailPanel.clear();
  }
  TopologyPanel.redraw();
  refreshNodeDropdowns();
});

socket.on("session:saved", d => {
  console.log("[Session] saved:", d.path);
});

// ============================================================
// Utilities
// ============================================================
function setBadge(status) {
  const el = document.getElementById("sim-status-badge");
  el.textContent = status.toUpperCase();
  el.className = "badge badge-" + status;
}

function updateClock(now_us) {
  state.nowUs = now_us;
  document.getElementById("sim-clock").textContent = (now_us / 1000).toFixed(3) + " ms";
}

async function api(method, path, body) {
  const opts = { method, headers: { "Content-Type": "application/json" } };
  if (body !== undefined) opts.body = JSON.stringify(body);
  const r = await fetch("/api" + path, opts);
  return r.json();
}

function refreshNodeDropdowns() {
  const ids = Object.keys(state.nodes);
  ["traffic-src", "traffic-dst"].forEach(id => {
    const sel = document.getElementById(id);
    const prev = sel.value;
    sel.innerHTML = ids.map(n => `<option value="${n}">${n}</option>`).join("");
    if (ids.includes(prev)) sel.value = prev;
  });
}

// ============================================================
// Panel Manager
// ============================================================
const PANEL_LABELS = { topology:"Topology", throughput:"Throughput", nodedetail:"Node Detail", log:"Log Stream" };
const panelTypes = ["topology", "throughput", "nodedetail", "log"];

let swapTargetPanel = null;

function initPanel(idx) {
  renderPanelContent(idx, panelTypes[idx], document.getElementById("panel-body-" + idx));
}

function renderPanelContent(idx, type, body) {
  body.innerHTML = "";
  const panel = document.getElementById("panel-" + idx);
  panel.dataset.panelType = type;
  panel.querySelector(".panel-title").textContent = PANEL_LABELS[type];
  if (type === "topology")   TopologyPanel.mount(body);
  if (type === "throughput") ThroughputPanel.mount(body);
  if (type === "nodedetail") NodeDetailPanel.mount(body);
  if (type === "log")        LogPanel.mount(body);
}

document.querySelectorAll(".btn-swap").forEach(btn => {
  btn.addEventListener("click", e => {
    swapTargetPanel = parseInt(btn.dataset.panel);
    const dd = document.getElementById("swap-dropdown");
    dd.classList.remove("hidden");
    const rect = btn.getBoundingClientRect();
    dd.style.top  = (rect.bottom + 4) + "px";
    dd.style.left = rect.left + "px";
    e.stopPropagation();
  });
});

document.getElementById("swap-dropdown").querySelectorAll("button").forEach(btn => {
  btn.addEventListener("click", () => {
    const newType = btn.dataset.type;
    document.getElementById("swap-dropdown").classList.add("hidden");
    if (swapTargetPanel === null) return;
    panelTypes[swapTargetPanel] = newType;
    renderPanelContent(swapTargetPanel, newType,
      document.getElementById("panel-body-" + swapTargetPanel));
    swapTargetPanel = null;
  });
});

document.addEventListener("click", () => {
  document.getElementById("swap-dropdown").classList.add("hidden");
});

document.querySelectorAll(".btn-expand").forEach(btn => {
  btn.addEventListener("click", () => {
    const idx = parseInt(btn.dataset.panel);
    const panel = document.getElementById("panel-" + idx);
    if (panel.classList.contains("fullscreen")) {
      panel.classList.remove("fullscreen");
      btn.textContent = "⧾";
    } else {
      panel.classList.add("fullscreen");
      btn.textContent = "✕";
      renderPanelContent(idx, panelTypes[idx], document.getElementById("panel-body-" + idx));
    }
  });
});

document.addEventListener("keydown", e => {
  if (e.key === "Escape") {
    document.querySelectorAll(".panel.fullscreen").forEach(p => {
      p.classList.remove("fullscreen");
      p.querySelector(".btn-expand").textContent = "⧾";
    });
  }
});

// ============================================================
// Topology Panel
// ============================================================
const TopologyPanel = (() => {
  let canvas = null, ctx = null;
  const linkStates = {};

  const COLORS = {
    IDLE: "#555", CONTENDING: "#f0a500", TXOP_GRANTED: "#00d4ff",
    TRANSMITTING: "#00a86b", WAIT_BA: "#7b2ff7", NPCA: "#e94560",
  };

  function mount(body) {
    canvas = document.createElement("canvas");
    canvas.id = "topology-canvas";
    canvas.style.cssText = "display:block;width:100%;height:100%";
    body.appendChild(canvas);
    resize();
    canvas.addEventListener("click", onClick);
    window.addEventListener("resize", resize);
    redraw();
  }

  function resize() {
    if (!canvas) return;
    canvas.width = canvas.offsetWidth || 400;
    canvas.height = canvas.offsetHeight || 300;
    ctx = canvas.getContext("2d");
    redraw();
  }

  function worldToCanvas(pos) {
    const nodes = Object.values(state.nodes);
    if (!nodes.length) return [canvas.width / 2, canvas.height / 2];
    const xs = nodes.map(n => n.position[0]);
    const ys = nodes.map(n => n.position[1]);
    const minX = Math.min(...xs), maxX = Math.max(...xs);
    const minY = Math.min(...ys), maxY = Math.max(...ys);
    const rangeX = maxX - minX || 1, rangeY = maxY - minY || 1;
    const pad = 50;
    return [
      pad + (pos[0] - minX) / rangeX * (canvas.width  - 2 * pad),
      pad + (pos[1] - minY) / rangeY * (canvas.height - 2 * pad),
    ];
  }

  function redraw() {
    if (!ctx) return;
    ctx.clearRect(0, 0, canvas.width, canvas.height);
    ctx.fillStyle = "#1a1a2e";
    ctx.fillRect(0, 0, canvas.width, canvas.height);

    const nodes = Object.values(state.nodes);
    const ap = nodes.find(n => n.type === "ap");

    // Draw links
    nodes.filter(n => n.type === "sta").forEach(sta => {
      if (!ap) return;
      const [x1, y1] = worldToCanvas(sta.position);
      const [x2, y2] = worldToCanvas(ap.position);
      const stateKey = sta.node_id + "|" + (sta.links?.[0] || "6g");
      ctx.strokeStyle = COLORS[linkStates[stateKey]] || COLORS.IDLE;
      ctx.lineWidth = 2;
      ctx.beginPath(); ctx.moveTo(x1, y1); ctx.lineTo(x2, y2); ctx.stroke();
    });

    // Draw nodes
    nodes.forEach(node => {
      const [cx, cy] = worldToCanvas(node.position);
      const r = 16;
      if (node.type === "ap") {
        ctx.fillStyle = "#e94560";
        ctx.fillRect(cx - r, cy - r, r * 2, r * 2);
        ctx.strokeStyle = "#f00";
        ctx.lineWidth = 2;
        ctx.strokeRect(cx - r, cy - r, r * 2, r * 2);
      } else {
        ctx.beginPath();
        ctx.arc(cx, cy, r, 0, Math.PI * 2);
        ctx.fillStyle = node.node_id === state.selectedNode ? "#00d4ff" : "#1a5276";
        ctx.fill();
        ctx.strokeStyle = "#00d4ff";
        ctx.lineWidth = 2;
        ctx.stroke();
      }
      ctx.fillStyle = "#fff";
      ctx.font = "10px sans-serif";
      ctx.textAlign = "center";
      ctx.fillText(node.node_id, cx, cy + r + 12);
    });
  }

  function setLinkState(nodeId, linkId, s) {
    linkStates[nodeId + "|" + linkId] = s;
    redraw();
  }

  function onClick(e) {
    const rect = canvas.getBoundingClientRect();
    const mx = e.clientX - rect.left, my = e.clientY - rect.top;
    let hit = null;
    Object.values(state.nodes).forEach(node => {
      const [cx, cy] = worldToCanvas(node.position);
      if (Math.hypot(mx - cx, my - cy) < 20) hit = node.node_id;
    });
    state.selectedNode = hit;
    NodeEditorSidebar.setNode(hit);
    NodeDetailPanel.refresh();
    redraw();
  }

  return { mount, redraw, setLinkState };
})();

// ============================================================
// Throughput Panel
// ============================================================
const ThroughputPanel = (() => {
  let chart = null;
  const MAX_POINTS = 100;
  const datasets = {};
  const PALETTE = ["#00d4ff","#00a86b","#e94560","#f0a500","#7b2ff7","#ff6b6b","#4ecdc4"];
  let colorIdx = 0;

  function mount(body) {
    body.innerHTML = '<div class="tput-panel"><canvas id="tput-canvas"></canvas></div>';
    const cvs = body.querySelector("canvas");
    chart = new Chart(cvs, {
      type: "line",
      data: { datasets: [] },
      options: {
        animation: false,
        responsive: true,
        maintainAspectRatio: false,
        scales: {
          x: { type: "linear",
               title: { display: true, text: "Time (ms)", color: "#aaa" },
               ticks: { color: "#aaa" }, grid: { color: "#0f3460" } },
          y: { title: { display: true, text: "Mbps", color: "#aaa" },
               ticks: { color: "#aaa" }, grid: { color: "#0f3460" }, min: 0 },
        },
        plugins: { legend: { labels: { color: "#e0e0e0", font: { size: 11 } } } },
      },
    });
  }

  function _getOrCreate(nodeId) {
    if (!datasets[nodeId]) {
      const ds = {
        label: nodeId,
        data: [],
        borderColor: PALETTE[colorIdx++ % PALETTE.length],
        tension: 0.3,
        pointRadius: 0,
      };
      datasets[nodeId] = ds;
      if (chart) { chart.data.datasets.push(ds); chart.update("none"); }
    }
    return datasets[nodeId];
  }

  function addSample(nodeId, tput, now_us) {
    if (!chart) return;
    const ds = _getOrCreate(nodeId);
    ds.data.push({ x: now_us / 1000, y: tput });
    if (ds.data.length > MAX_POINTS) ds.data.shift();
    chart.update("none");
  }

  function recordTx(_d) { /* aggregated via metrics:sample */ }

  return { mount, addSample, recordTx };
})();

// ============================================================
// Node Detail Panel
// ============================================================
const NodeDetailPanel = (() => {
  let container = null;

  function mount(body) {
    container = document.createElement("div");
    container.className = "node-detail";
    body.appendChild(container);
    refresh();
  }

  function refresh() {
    if (!container) return;
    const nid = state.selectedNode;
    if (!nid) {
      container.innerHTML = '<p class="muted" style="padding:12px">Select a node on the topology</p>';
      return;
    }
    const node = state.nodes[nid] || {};
    const m = state.nodeMetrics[nid] || {};
    container.innerHTML = `
      <table class="detail-table">
        <tr><td>ID</td><td><strong>${nid}</strong></td></tr>
        <tr><td>Type</td><td>${node.type || "—"}</td></tr>
        <tr><td>Links</td><td>${(node.links || []).join(", ")}</td></tr>
        <tr><td>Throughput</td><td>${(m.throughput_mbps || 0).toFixed(2)} Mbps</td></tr>
        <tr><td>MCS</td><td>${m.mcs !== undefined ? m.mcs : "—"}</td></tr>
        <tr><td>SNR</td><td>${m.snr_db || "—"} dB</td></tr>
        <tr><td>NPCA opp.</td><td>${m.npca_opportunities || 0}</td></tr>
        <tr><td>NPCA used</td><td>${m.npca_used || 0}</td></tr>
      </table>`;
  }

  function clear() {
    if (container) container.innerHTML = "";
  }

  return { mount, refresh, clear };
})();

// ============================================================
// Log Panel
// ============================================================
const LogPanel = (() => {
  let container = null;
  const MAX_LINES = 500;
  let lines = [];

  function mount(body) {
    container = document.createElement("div");
    container.className = "log-panel";
    body.appendChild(container);
    lines.forEach(l => _appendLine(l));
  }

  function append(d) {
    lines.push(d);
    if (lines.length > MAX_LINES) lines.shift();
    if (container) {
      _appendLine(d);
      if (container.children.length > MAX_LINES)
        container.removeChild(container.firstChild);
      container.scrollTop = container.scrollHeight;
    }
  }

  function _appendLine(d) {
    if (!container) return;
    const el = document.createElement("div");
    el.className = "log-line " + (d.level || "INFO");
    const ts = d.time_ns !== undefined ? (d.time_ns / 1e6).toFixed(2) : "—";
    el.textContent = `[${ts}ms] [${d.node_id || d.callback || "—"}]`;
    container.appendChild(el);
  }

  return { mount, append };
})();

// ============================================================
// Control Sidebar
// ============================================================
document.getElementById("btn-pause").addEventListener("click",
  () => api("POST", "/sim/pause"));
document.getElementById("btn-resume").addEventListener("click",
  () => api("POST", "/sim/resume"));
document.getElementById("btn-stop").addEventListener("click",
  () => api("POST", "/sim/stop"));
document.getElementById("speed-select").addEventListener("change", e => {
  api("PATCH", "/sim/speed", { multiplier: parseFloat(e.target.value) });
});
document.getElementById("sidebar-toggle").addEventListener("click", () => {
  document.getElementById("sidebar").classList.toggle("collapsed");
});

// Populate MCS dropdown
const mcsSelect = document.getElementById("editor-mcs");
for (let i = 0; i <= 13; i++) {
  const o = document.createElement("option");
  o.value = String(i); o.textContent = String(i);
  mcsSelect.appendChild(o);
}

// ============================================================
// Node Editor Sidebar
// ============================================================
const NodeEditorSidebar = (() => {
  function setNode(nodeId) {
    const noSel  = document.getElementById("no-selection-msg");
    const editor = document.getElementById("node-editor");
    if (!nodeId) {
      noSel.classList.remove("hidden"); editor.classList.add("hidden"); return;
    }
    noSel.classList.add("hidden"); editor.classList.remove("hidden");
    document.getElementById("editor-node-id").textContent = nodeId;
    const node = state.nodes[nodeId] || {};
    document.getElementById("editor-pos-x").value = (node.position || [0, 0])[0];
    document.getElementById("editor-pos-y").value = (node.position || [0, 0])[1];
  }
  return { setNode };
})();

document.getElementById("btn-move-node").addEventListener("click", async () => {
  const nid = state.selectedNode;
  if (!nid) return;
  const x = parseFloat(document.getElementById("editor-pos-x").value);
  const y = parseFloat(document.getElementById("editor-pos-y").value);
  await api("PATCH", "/nodes/" + nid + "/position", { x, y });
  if (state.nodes[nid]) state.nodes[nid].position = [x, y];
  TopologyPanel.redraw();
});

document.getElementById("editor-mcs").addEventListener("change", async e => {
  const nid = state.selectedNode;
  if (!nid) return;
  await api("PATCH", "/nodes/" + nid + "/mcs", { mcs: e.target.value });
});

document.getElementById("editor-npca").addEventListener("change", async e => {
  const nid = state.selectedNode;
  if (!nid) return;
  await api("PATCH", "/nodes/" + nid + "/npca", { enabled: e.target.checked });
});

document.getElementById("btn-remove-node").addEventListener("click", async () => {
  const nid = state.selectedNode;
  if (!nid || !confirm("Remove node " + nid + "?")) return;
  await api("DELETE", "/nodes/" + nid);
});

document.getElementById("btn-add-node").addEventListener("click", async () => {
  const id    = document.getElementById("new-node-id").value.trim();
  const type  = document.getElementById("new-node-type").value;
  const links = document.getElementById("new-node-links").value.split(",").map(s => s.trim());
  if (!id) { alert("Enter a node ID"); return; }
  const r = await api("POST", "/nodes", { id, type, links, position: [0, 0], mlo_mode: "str" });
  if (r.error) { alert("Error: " + r.error); return; }
  state.nodes[r.node_id] = r;
  TopologyPanel.redraw();
  refreshNodeDropdowns();
});

// ============================================================
// Traffic Injector
// ============================================================
document.getElementById("btn-inject-traffic").addEventListener("click", async () => {
  const src  = document.getElementById("traffic-src").value;
  const dst  = document.getElementById("traffic-dst").value;
  const type = document.getElementById("traffic-type").value;
  const rate = parseFloat(document.getElementById("traffic-rate").value);
  const ac   = document.getElementById("traffic-ac").value;
  const r = await api("POST", "/traffic", { src, dst, type, rate_mbps: rate, ac });
  if (r.error) alert("Inject error: " + r.error);
  else console.log("[Traffic] Injected:", r);
});

// ============================================================
// File Menu
// ============================================================
document.getElementById("btn-file-menu").addEventListener("click", e => {
  document.getElementById("file-dropdown").classList.toggle("hidden");
  e.stopPropagation();
});

document.getElementById("btn-open-session").addEventListener("click", async () => {
  document.getElementById("file-dropdown").classList.add("hidden");
  const sessions = await api("GET", "/sessions");
  const list = document.getElementById("session-list");
  list.innerHTML = (sessions || []).map(s => `
    <div class="session-item" data-id="${s.run_id}" data-path="${s.path || ""}">
      <div class="session-id">${s.run_id}</div>
      <div class="session-meta">${new Date((s.start_ts || 0) * 1000).toLocaleString()} &middot; ${s.total_bytes || 0} bytes</div>
    </div>`).join("");
  list.querySelectorAll(".session-item").forEach(el => {
    el.addEventListener("click", () => {
      document.getElementById("session-modal").classList.add("hidden");
      ReplayManager.loadFromRunId(el.dataset.id);
    });
  });
  document.getElementById("session-modal").classList.remove("hidden");
});

document.getElementById("session-modal-close").addEventListener("click", () => {
  document.getElementById("session-modal").classList.add("hidden");
});

// ============================================================
// Replay Manager
// ============================================================
const ReplayManager = (() => {
  let events = [], idx = 0, playing = false, timer = null;

  async function loadFromRunId(runId) {
    const evts = await api("GET", "/sessions/" + encodeURIComponent(runId) + "/events");
    start(Array.isArray(evts) ? evts : []);
  }

  function start(evts) {
    events = evts; idx = 0; playing = false;
    state.replayMode = true;
    setBadge("replay");
    document.getElementById("replay-bar").classList.remove("hidden");
    document.querySelectorAll(".sim-btn").forEach(b => b.disabled = true);
    document.getElementById("replay-play-pause").disabled = false;
    document.getElementById("replay-close").disabled = false;
    const scrubber = document.getElementById("replay-scrubber");
    scrubber.max = Math.max(events.length - 1, 0);
    scrubber.value = 0;
  }

  function stop() {
    clearTimeout(timer);
    playing = false;
    state.replayMode = false;
    document.getElementById("replay-bar").classList.add("hidden");
    document.querySelectorAll(".sim-btn").forEach(b => { b.disabled = false; });
    setBadge(state.simStatus);
  }

  function playNext() {
    if (!playing || idx >= events.length) { playing = false; return; }
    const ev = events[idx++];
    document.getElementById("replay-scrubber").value = idx;
    if (ev.now_us !== undefined) {
      document.getElementById("replay-ts").textContent = (ev.now_us / 1000).toFixed(2) + " ms";
      updateClock(ev.now_us);
    }
    if (ev.type) socket.emit(ev.type, ev);
    const speed = parseFloat(document.getElementById("replay-speed").value);
    timer = setTimeout(playNext, 16 / speed);
  }

  document.getElementById("replay-play-pause").addEventListener("click", () => {
    if (playing) {
      playing = false; clearTimeout(timer);
      document.getElementById("replay-play-pause").textContent = "▶";
    } else {
      playing = true;
      document.getElementById("replay-play-pause").textContent = "⏸";
      playNext();
    }
  });
  document.getElementById("replay-scrubber").addEventListener("input", e => {
    idx = parseInt(e.target.value);
  });
  document.getElementById("replay-close").addEventListener("click", stop);

  return { loadFromRunId, start, stop };
})();

// ============================================================
// Init
// ============================================================
(async function init() {
  try {
    const nodes = await api("GET", "/nodes");
    (nodes || []).forEach(n => { state.nodes[n.node_id] = n; });
    refreshNodeDropdowns();
  } catch (e) {
    console.warn("Could not fetch initial nodes:", e);
  }
  for (let i = 0; i < 4; i++) initPanel(i);
  TopologyPanel.redraw();
})();
