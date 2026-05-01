# nxwlansim — Project Context for Claude

## What this project is
IEEE 802.11be (Wi-Fi 7/8) MLO (Multi-Link Operation) network simulator written in Python.
Discrete-Event Simulation (DES) engine. Clock resolution: nanoseconds.

## Package layout
```
nxwlansim/
  core/
    engine.py       — DES engine (SimulationEngine), event loop, schedule/schedule_after
    config.py       — SimConfig, NodeConfig, TrafficConfig, ObsConfig (dataclasses + from_yaml/from_dict/quick_build)
    builder.py      — wires PHY, MAC, nodes, traffic before engine.run()
    registry.py     — NodeRegistry (aps(), stas(), get(), register())
    results.py      — SimResults (record_tx, record_ba_timeout, summary())
    node.py         — APNode, STANode
  mac/
    txop.py         — TXOPEngine: drives EDCA backoff → TXOP grant → A-MPDU TX → BA wait
                      IMPORTANT: calls engine._results.record_tx() AND engine._metrics.record_tx_event()
                      (the second call was a bug-fix — do not remove it)
    edca.py         — EDCAScheduler, per-AC queues, CW management
    mlo.py          — MLOLinkManager: STR / eMLSR / eMLMR link selection
    rx.py           — RXProcessor: ACK/BA generation, NAV updates
  phy/
    tgbe_channel.py — TGbeChannel: TGbe path-loss + MCS selection (default backend)
    interference.py — SINR interference tracker
  traffic/
    generators.py   — schedule_traffic_sources() — seeds initial traffic events
  observe/
    metrics.py      — MetricsCollector: periodic 10 ms sampler → CSV + viz feed
    viz.py          — SimViz: throughput time-series, topology, link-state Gantt (matplotlib Agg)
    logger.py       — SimLogger: per-event log
    pcap.py / pcap_hook.py — optional PCAP capture
  network/
    bss.py, ip_layer.py, multi_ap.py
  dashboard/                          — Phase 3 (complete)
    server.py   — Flask app + SocketIO setup + background thread runner
    bridge.py   — SimBridge: hooks into engine, queues + emits SocketIO events
    api.py      — REST control endpoints (pause/resume/stop, nodes, traffic)
    events.py   — SocketIO event name constants + payload schemas
    static/     — dashboard.js, dashboard.css
    templates/  — dashboard.html (single-page shell, Chart.js via CDN)
```

## Key wiring facts (read before touching engine/mac/observe)
- `engine._results`  → SimResults (summary table)
- `engine._metrics`  → MetricsCollector (CSV + viz feed); must call `record_tx_event()` on every successful TX
- `engine._viz`      → SimViz; receives samples via `_metrics` (do not call directly from MAC)
- `engine._registry` → NodeRegistry, set after `build_simulation()` inside `engine.run()`
- `engine.on_tx / on_state / on_metrics / on_log` → hook slots for SimBridge (None by default)
- Event priorities: PHY_COMPLETE=0, MAC_DECISION=1, TRAFFIC_GEN=2, OBSERVE=3

## Config quick-reference
```python
from nxwlansim.core.config import SimConfig, SimulationConfig, PhyConfig, NetworkConfig, ObsConfig, NodeConfig, TrafficConfig
from nxwlansim.core.engine import SimulationEngine

cfg = SimConfig(
    simulation=SimulationConfig(duration_us=300_000, seed=42),
    phy=PhyConfig(backend="tgbe", channel_model="D"),
    network=NetworkConfig(mode="bss"),
    obs=ObsConfig(log=True, csv=True, pcap=False, viz=True, output_dir="results/my_run"),
    nodes=[...],
    traffic=[...],
)
engine = SimulationEngine(cfg)
results = engine.run()
print(results.summary())
```
Or load from YAML: `SimConfig.from_yaml("configs/examples/mlo_str_basic.yaml")`
Or quick-build: `SimConfig.quick_build(mlo_mode="str", n_links=2, n_stas=3, duration_us=300_000)`

## Example configs (configs/examples/)
- mlo_str_basic.yaml       — 1 AP + 3 STAs, STR, 5g+6g, mixed traffic
- mlo_emlsr_2sta.yaml      — eMLSR mode, 2 STAs
- mlo_emlmr_multiap.yaml   — eMLMR + multi-AP
- emlsr_vs_str_comparison.yaml
- heavy_load_str.yaml
- hidden_node.yaml
- mixed_ac_priority.yaml
- multiap_roaming.yaml
- voip_tid_steering.yaml

## Demo / runnable scripts
- `scripts/run_mlo_demo.py` — 1 AP + 3 STAs, STR, 5g+6g, 300 ms. Produces:
    results/mlo_demo/throughput_per_node.png
    results/mlo_demo/topology.png
    results/mlo_demo/link_states.png
    results/mlo_demo/metrics.csv
- `nxwlansim dashboard --config configs/examples/npca_basic.yaml --port 5050` — live dashboard
- `nxwlansim dashboard --replay results/sessions/<dir>/` — replay mode

## MLO modes supported
- `str`   — Simultaneous Transmit & Receive (both links active independently)
- `emlsr` — Enhanced Multi-Link Single Radio (transitions between links)
- `emlmr` — Enhanced Multi-Link Multi-Radio

## Known issues / watch-outs
- sta1 BA-TIMEOUTs at 100 Mbps VI load — expected under heavy contention (CW doubles per collision), not a bug
- `obs.viz: true` required in config to generate PNG plots
- PCAP disabled by default (`pcap: false`); enable per-node with `obs.pcap: true`
- matlab PHY backend falls back to tgbe automatically if matlab.engine not installed

## Fixed bugs (Phase 1 debt cleared)
- **TX double-count** (`mac/txop.py`): `record_tx()` was called at TX start AND after BA. Fixed — now only counts bytes after successful BA receipt. Throughput numbers were ~2× inflated before this fix.
- **LoadBalancePolicy** (`mac/mlo.py`): was a stub that just returned idle links. Now sorts by real EDCA queue depth (least-loaded link first). Used by EMLMR mode.
- **MetricsCollector not fed** (`mac/txop.py`): `engine._metrics.record_tx_event()` was never called — viz throughput plots were empty. Fixed by wiring it into the post-BA success path.

## Phase 2 additions (MATLAB PHY + Full NPCA)

### MATLAB PHY pipeline (`nxwlansim/phy/matlab/`)
- `cache.py` — `TableCache` + `CacheKey` (SHA256-keyed HDF5 storage)
- `table_phy.py` — `TablePhy` pure-Python interpolating backend (CI-safe)
- `generator.py` — `MatlabTableGenerator` (calls WLAN Toolbox at startup)
- `live_phy.py` — `MatlabLivePhy` (reserved for future custom-channel live path)
- `adaptive_phy.py` — `AdaptivePhy` orchestrator (what builder instantiates for `backend: matlab`)

To activate: set `phy.backend: matlab` in YAML config.
- With MATLAB installed: generates + caches tables on first run (~60 s), instant on subsequent runs.
- Without MATLAB (CI): loads `tests/fixtures/tgbe_d_fixture.h5` automatically.

### Full NPCA (`nxwlansim/mac/npca.py`)
- `NPCAEngine` — evaluates per-subchannel NAV, returns `NPCADecision`
- `NPCADecision` — `use_npca`, `punctured_mask`, `effective_bw_mhz`
- `LinkContext.sub_nav` — per-subchannel NAV dict (added to `mlo.py`)
- `AMPDUFrame.punctured_mask` + `effective_bw_mhz` (added to `frame.py`)
- NPCA hook in `txop._attempt_txop()` — evaluates + coordinates before each TX
- `NPCAEngine` attached to every node by `builder._attach_mac()`

### NPCA metrics
- `MetricsCollector.record_npca_event()` — called from txop on every TXOP attempt
- CSV columns added: `npca_opportunities`, `npca_used`, `npca_gain_mbps`

### New example configs
- `configs/examples/npca_basic.yaml` — 1 AP + 2 STAs, heavy BE load
- `configs/examples/npca_coordinated.yaml` — 1 AP + 4 STAs, coordinated NPCA

### Setup docs
- `docs/setup/matlab_ubuntu_install.md` — R2025a Ubuntu install guide
- `scripts/verify_matlab.py` — confirms WLAN Toolbox is installed and licensed
- `scripts/generate_fixture_tables.py` — regenerates CI fixture HDF5

## PENDING: MATLAB activation (do this next session)

MATLAB R2025a is licensed but not yet installed. Once installed on this Ubuntu machine:

1. Follow `docs/setup/matlab_ubuntu_install.md` for R2025a Ubuntu install steps.
2. Run `python3 scripts/verify_matlab.py` — confirms WLAN Toolbox is licensed and working.
3. Run a sim with `phy.backend: matlab` to warm the HDF5 cache (~60 s first run, instant after):
   ```bash
   python3 -c "
   from nxwlansim.core.config import SimConfig
   from nxwlansim.core.engine import SimulationEngine
   cfg = SimConfig.from_yaml('configs/examples/npca_basic.yaml')
   # Edit the yaml or override: cfg.phy.backend = 'matlab'
   r = SimulationEngine(cfg).run()
   print(r.summary())
   "
   ```
4. The generated tables are cached at `~/.nxwlansim/phy_tables/` — subsequent runs are fast.

## Phase 3: Flask Web Dashboard (complete)

### What it adds
Real-time browser dashboard: live monitoring + interactive mid-run control + post-run replay.

### Launch command
```bash
nxwlansim dashboard --config configs/examples/npca_basic.yaml --port 5050
# open http://localhost:5050
```

### Architecture
- **SimBridge** (`dashboard/bridge.py`) hooks into engine's `on_tx / on_state / on_metrics / on_log` slots
- **Flask + Flask-SocketIO** (`dashboard/server.py`) — threading async_mode, WebSocket for live events
- **REST API** (`dashboard/api.py`) — control commands (pause/resume/stop, add/remove/move nodes, inject traffic)
- **SessionStore** (`observe/session_store.py`) — auto-saves every run to `results/sessions/<timestamp>/`
- **dashboard.html + dashboard.js** — 4-panel grid (Topology, Throughput, Node Detail, Log Stream)

### Panel system
- 2×2 configurable grid; each panel independently swappable and full-screen expandable
- Default: Topology (top-left), Throughput (top-right), Node Detail (bottom-left), Log Stream (bottom-right)

### Control sidebar (collapsible)
- **Sim controls**: pause / resume / stop / speed multiplier (1×–Max)
- **Node editor**: drag position, MCS override, NPCA toggle, add/remove node
- **Traffic injector**: source, destination, type (UDP CBR/VoIP/Burst), rate, AC

### Replay mode
- Session history sidebar: lists `results/sessions/` runs with timestamp + config summary
- File picker: load any `results/` directory manually
- Timeline scrubber (play/pause/speed) at bottom; control sidebar disabled in replay mode

### Key SocketIO events (server → browser)
`sim:tick`, `tx:event`, `link:state`, `metrics:sample`, `log:line`, `sim:status`, `node:added`, `node:removed`, `session:saved`

### Session files saved per run
```
results/sessions/<timestamp>_<config>/
  config.yaml      ← copy of run config
  metrics.csv      ← MetricsCollector output
  events.jsonl     ← one JSON line per event (used for replay)
  meta.json        ← {run_id, start_ts, end_ts, n_nodes, total_bytes}
```

### New dependencies
```toml
"flask-socketio>=5.3",
"eventlet>=0.35",
```

### Design spec
`docs/superpowers/specs/2026-04-28-flask-dashboard-design.md`

## Test suite
```bash
pytest tests/ -q
```
Golden regression suite in `tests/`. CLI tests in `tests/test_cli.py`.
