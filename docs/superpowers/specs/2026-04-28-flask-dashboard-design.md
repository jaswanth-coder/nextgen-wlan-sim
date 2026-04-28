# Phase 3 Design: Flask Web Dashboard
**Date:** 2026-04-28
**Project:** nextgen-wlan-sim (nxwlansim)
**Status:** Approved — ready for implementation

---

## 1. Goals

1. Add a real-time browser dashboard to nxwlansim for live simulation monitoring, interactive mid-run control, and post-run replay.
2. Use Flask + Flask-SocketIO + Vanilla JS — no build toolchain, pure-Python server, compatible with future Gymnasium/AI integration.
3. Zero impact on existing engine/MAC/PHY code — SimBridge hooks in at the observe layer only.
4. Ship a `nxwlansim dashboard` CLI subcommand that launches everything in one command.

---

## 2. Scope

**In this phase:**
- 4-panel configurable grid dashboard (Topology, Throughput, Node Detail, Log Stream)
- Per-panel full-screen and swap
- Live WebSocket event stream from running sim
- REST control API (pause/resume/stop, speed, add/remove/move nodes, inject traffic, NPCA toggle)
- SessionStore: auto-save every run; replay from saved session or file picker
- Timeline scrubber for replay mode

**Not in this phase:**
- User authentication
- Multi-sim instances per process
- Mobile layout
- Dark/light theme toggle
- Multi-AP Coordination (Phase 4)
- Gymnasium RL env (separate phase)

---

## 3. Architecture

### New files

```
nxwlansim/
  dashboard/
    __init__.py
    server.py          ← Flask app + SocketIO setup + background thread runner
    bridge.py          ← SimBridge: hooks into engine, queues + emits events
    api.py             ← REST endpoints (control commands)
    events.py          ← SocketIO event name constants + payload schemas
    static/
      dashboard.js     ← panel grid, charts, drag-and-drop, full-screen
      dashboard.css    ← grid layout, panel chrome, sidebar styles
    templates/
      dashboard.html   ← single-page shell, loads JS/CSS + Chart.js from CDN
  observe/
    session_store.py   ← writes results/sessions/<timestamp>/ per run
```

### Modified files

```
nxwlansim/core/engine.py   ← add on_tx / on_state / on_metrics / on_log hook slots
nxwlansim/core/builder.py  ← attach SimBridge when obs.dashboard=true
nxwlansim/core/config.py   ← ObsConfig: dashboard (bool), dashboard_port (int=5050)
cli/__main__.py             ← add `nxwlansim dashboard` subcommand
```

### Component diagram

```
CLI / script
    │
    ▼
SimulationEngine.run()  ←──── SimBridge (hooks: on_tx, on_state, on_metrics, on_log)
                                   │
                                   │ emit via SocketIO
                                   ▼
                            Flask + Flask-SocketIO (eventlet)
                                   │
                            ┌──────┴───────┐
                            │  WebSocket   │  REST /api/*
                            │  (live data) │  (control cmds)
                            └──────────────┘
                                   │
                            Browser dashboard.html
                            ┌──────────────────────┐
                            │  2×2 Panel Grid       │
                            │  ┌──────┬──────┐     │
                            │  │ Topo │ Tput │     │
                            │  ├──────┼──────┤     │
                            │  │ Node │ Log  │     │
                            │  └──────┴──────┘     │
                            │  + collapsible        │
                            │    control sidebar    │
                            └──────────────────────┘
```

Engine runs in a background thread. Flask-SocketIO's `eventlet` async mode pushes events without blocking the sim.

---

## 4. Panel System

### Panel types

| Type | Content |
|------|---------|
| **Topology** | Canvas: nodes as circles (AP=square), links as colored lines. Colors: idle=gray, contending=yellow, TXOP=green, NPCA=purple. Click node to select. |
| **Throughput** | Scrolling Chart.js line chart. One line per node, last 10s of data, 100ms resolution. Pause freezes scroll. |
| **Node Detail** | Selected node stats: MCS, SNR, queue depths per AC (VO/VI/BE/BK), NPCA opportunities/used, BA timeout count. |
| **Log Stream** | Tail of sim event log, auto-scrolling. Filter by node ID or event type. |

### Panel chrome

Each panel header has:
- Panel title label
- **↔** swap button — dropdown to pick a different panel type
- **⛶** expand button — full-screen toggle (Escape or click again to exit)

Default layout: Topology (top-left), Throughput (top-right), Node Detail (bottom-left), Log Stream (bottom-right).

---

## 5. Control Sidebar

Collapsible right sidebar with three sections:

### Sim Controls
- Pause / Resume / Stop buttons
- Sim clock display (current sim time in ms)
- Speed multiplier selector: 1×, 2×, 5×, 10×, Max
  - Implemented as a wall-clock throttle: the engine sleeps `event_delta_ns / multiplier` of real time after each event. "Max" = no sleep (as fast as possible, default DES behaviour).

### Node Editor (active when a node is selected)
- Drag node on topology → `PATCH /api/nodes/{id}/position`
- MCS override: dropdown (Auto / MCS 0–13)
- NPCA enabled: toggle → `PATCH /api/nodes/{id}/npca`
- Add node: type (AP/STA), position, links → `POST /api/nodes`
  - Engine must pause briefly; builder wires PHY + MAC for the new node; registry.register() is called; engine resumes. Node will not have backlog traffic until a traffic source is injected separately.
- Remove selected node → `DELETE /api/nodes/{id}`
  - Node's pending events are drained before removal; outstanding BA sessions are cancelled.

### Traffic Injector
- Source / Destination node dropdowns
- Type: UDP CBR / VoIP / Burst
- Rate (Mbps) + AC (VO/VI/BE/BK)
- Inject button → `POST /api/traffic`

---

## 6. WebSocket Events (server → browser)

| Event | Payload | Rate |
|-------|---------|------|
| `sim:tick` | `{now_us, speed_x}` | every 10ms sim time |
| `tx:event` | `{node_id, link_id, bytes, mcs, snr_db, npca}` | every TX |
| `link:state` | `{node_id, link_id, state}` | on state change |
| `metrics:sample` | `{node_id, tput_mbps, queue_depths, npca_opportunities, npca_used}` | every 100ms sim time |
| `log:line` | `{level, ts_us, node_id, msg}` | every log event |
| `sim:status` | `{status: running\|paused\|stopped, now_us}` | on status change |
| `node:added` | `{node_id, type, position, links}` | when node added |
| `node:removed` | `{node_id}` | when node removed |
| `session:saved` | `{path, run_id}` | on auto-save complete |

---

## 7. REST API (browser → server)

| Method | Path | Body | Action |
|--------|------|------|--------|
| `POST` | `/api/sim/pause` | — | Pause engine |
| `POST` | `/api/sim/resume` | — | Resume engine |
| `POST` | `/api/sim/stop` | — | Stop engine |
| `PATCH` | `/api/sim/speed` | `{multiplier}` | Set speed multiplier |
| `GET` | `/api/nodes` | — | List all nodes |
| `POST` | `/api/nodes` | `{type, position, links, mlo_mode}` | Add node mid-run |
| `DELETE` | `/api/nodes/{id}` | — | Remove node mid-run |
| `PATCH` | `/api/nodes/{id}/position` | `{x, y}` | Move node |
| `PATCH` | `/api/nodes/{id}/mcs` | `{mcs\|"auto"}` | Override MCS |
| `PATCH` | `/api/nodes/{id}/npca` | `{enabled}` | Toggle NPCA |
| `POST` | `/api/traffic` | `{src, dst, type, rate_mbps, ac}` | Inject traffic source |
| `GET` | `/api/sessions` | — | List saved sessions |
| `GET` | `/api/sessions/{id}` | — | Get run metadata |
| `GET` | `/api/sessions/{id}/metrics` | `?from_us&to_us` | Fetch CSV slice |
| `GET` | `/api/sessions/{id}/log` | `?from_us&to_us` | Fetch log slice |

---

## 8. SimBridge

`SimBridge` registers four hooks into the engine at build time (when `obs.dashboard=true`):

```python
engine.on_tx      = bridge.on_tx       # called after every successful BA
engine.on_state   = bridge.on_state    # called on LinkState transitions
engine.on_metrics = bridge.on_metrics  # called by MetricsCollector._sample()
engine.on_log     = bridge.on_log      # called by SimLogger
```

Events are queued in a `collections.deque(maxlen=10_000)`. A background `eventlet` greenlet drains it to SocketIO at ≤60 events/s to avoid flooding the browser. Oldest events are dropped when the deque is full (the sim never blocks).

---

## 9. SessionStore

Every dashboard-started run is auto-saved:

```
results/
  sessions/
    2026-04-28T16-30-00_mlo_str_basic/
      config.yaml      ← copy of run config
      metrics.csv      ← MetricsCollector output
      events.jsonl     ← one JSON line per TX/state/log event (for replay)
      meta.json        ← {run_id, start_ts, end_ts, n_nodes, total_bytes}
```

The replay loader reads `events.jsonl` and re-emits events at playback speed via the same SocketIO events — the browser sees no difference between live and replay.

---

## 10. Replay Mode

Triggered via **File** menu (top navbar):
- **Open session** — sidebar list of `results/sessions/` directories with timestamp + config summary
- **Open file** — manual file picker for any `results/` directory

Timeline scrubber appears at bottom: play/pause + timestamp slider + speed selector (0.5×, 1×, 2×, 5×).

All control sidebar buttons are disabled (greyed out) in replay mode.

---

## 11. Testing Strategy

### Unit tests (no browser, no running sim)

| File | What it covers |
|------|---------------|
| `tests/unit/test_bridge.py` | SimBridge queues events correctly, rate-limits to 60/s, drops oldest when deque full |
| `tests/unit/test_api.py` | Flask test client: each REST endpoint returns correct status + JSON |
| `tests/unit/test_session_store.py` | SessionStore writes `meta.json` + `events.jsonl`; replay loader re-emits correct sequence |

### Integration tests

| File | What it covers |
|------|---------------|
| `tests/integration/test_dashboard_live.py` | Start sim + dashboard in-process, connect SocketIO test client, assert `metrics:sample` received |
| `tests/integration/test_replay.py` | Run sim → save session → replay at 5× → assert events re-emitted in order |

### Manual smoke-test checklist

```bash
nxwlansim dashboard --config configs/examples/npca_basic.yaml --port 5050
# open http://localhost:5050
```

- [ ] Topology renders nodes + links with correct colors
- [ ] Throughput chart scrolls during run
- [ ] Pause/resume works; clock freezes/resumes
- [ ] Node drag updates position on topology
- [ ] Inject traffic adds a new line on throughput chart
- [ ] Replay scrubber plays back a saved session
- [ ] Full-screen works for all 4 panel types
- [ ] Panel swap works for all panel types

---

## 12. Dependencies Added

```toml
[project.dependencies]
# add to existing list:
"flask-socketio>=5.3",
"eventlet>=0.35",
```

`flask` is already a dependency. `eventlet` is the async worker required by Flask-SocketIO for background thread + WebSocket coexistence.

---

## 13. CLI Usage

```bash
# Launch dashboard (starts sim + opens server)
nxwlansim dashboard --config configs/examples/npca_basic.yaml --port 5050

# Launch dashboard in replay-only mode (no sim)
nxwlansim dashboard --replay results/sessions/2026-04-28T16-30-00_mlo_str_basic/

# Existing CLI unchanged
nxwlansim run configs/examples/mlo_str_basic.yaml
```

---

## 14. Implementation Order

1. `ObsConfig` dashboard fields + `engine.py` hook slots
2. `observe/session_store.py` + unit tests
3. `dashboard/bridge.py` + unit tests
4. `dashboard/server.py` + `dashboard/api.py` + unit tests
5. `dashboard/templates/dashboard.html` + `static/dashboard.css` — static shell + grid layout
6. `static/dashboard.js` — panel system (swap, full-screen, Chart.js throughput)
7. Topology canvas + node selection
8. Node Detail panel + Log Stream panel
9. Control sidebar (pause/resume/stop/speed)
10. Node editor (drag position, MCS override, NPCA toggle, add/remove)
11. Traffic injector
12. Replay mode (scrubber + session list + file picker)
13. `cli/__main__.py` — `dashboard` subcommand
14. Integration tests
15. CLAUDE.md update
