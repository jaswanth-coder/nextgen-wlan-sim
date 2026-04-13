# WiFi 7/8 Network Simulator — Design Specification
**Date:** 2026-04-13  
**Phase:** 1 — MLO (Multi-Link Operation)  
**Status:** Approved  

---

## 1. Project Overview

A pure-Python, discrete-event network simulator targeting IEEE 802.11be (WiFi 7) and next-generation WiFi technologies. Phase 1 focuses exclusively on Multi-Link Operation (MLO) at the MAC layer, with a pluggable PHY abstraction layer that supports both a standalone statistical channel model and optional MATLAB WLAN Toolbox co-simulation.

### Primary Goals
- Protocol development and debugging of MLO features
- Performance benchmarking (throughput, latency, fairness)
- Academic research support (reproducible scenarios, exportable results)

### Non-Goals (Phase 1)
- Security layer (PMF, SAE, 4-way handshake) — excluded permanently
- WiFi 8 (EHT+, 320 MHz beyond table abstraction) — Phase 4
- Mesh / 802.11s — future phase
- C/C++ extensions — pure Python throughout; designed for OpenGym/RL integration

---

## 2. Technology Scope

### Phase 1 — MLO
| Feature | Standard Ref | Included |
|---------|-------------|---------|
| MLO STR (Simultaneous Transmit & Receive) | 802.11be §35.3.4 | ✅ |
| EMLSR (Enhanced Multi-Link Single Radio) | 802.11be §35.3.5 | ✅ |
| EMLMR (Enhanced Multi-Link Multi-Radio) | 802.11be §35.3.6 | ✅ |
| A-MPDU aggregation | 802.11-2020 §10.12 | ✅ |
| Block Acknowledgement (BA) | 802.11-2020 §10.24 | ✅ |
| EDCA (Enhanced Distributed Channel Access) | 802.11-2020 §10.22 | ✅ |
| TID-to-link mapping | 802.11be §35.3.7 | ✅ |

### Phase 2 — NPCA
- Non-Primary Channel Access modeling
- Dynamic channel bonding state machine

### Phase 3 — Multi-AP Coordination
- Coordinated OFDMA (C-OFDMA)
- Coordinated Spatial Reuse (Co-SR)
- AP-to-AP signaling (EHT Multi-AP)

### Phase 4 — WiFi 8 / Mesh
- 320 MHz channels, 16-stream features
- 802.11s mesh support

---

## 3. Architecture

### 3.1 High-Level Block Diagram

```
         ┌─────────────────────────────────────────────────────┐
         │                Simulation Core (DES)                 │
         │   EventQueue | SimClock (ns) | NodeRegistry | Config │
         └──────┬──────────────┬────────────────┬──────────────┘
                │              │                │
         ┌──────▼──┐    ┌──────▼──────┐   ┌────▼─────────────┐
         │ Network │    │  MAC Layer   │   │  PHY Abstraction  │
         │ Layer   │    │  (EDCA/MLO) │   │  (plugin slot)    │
         └────┬────┘    └──────┬──────┘   └────┬─────────────┘
              │                │               │
         ┌────▼────────────────▼───────────────▼──────────────┐
         │               Channel Model                          │
         │    TGbeChannel (standalone)  |  MatlabWlanPhy       │
         └─────────────────────────────────────────────────────┘
                                    │
         ┌──────────────────────────▼──────────────────────────┐
         │                  Observability                        │
         │      Logger | CSV | PCAP | Viz | Gym Hook            │
         └─────────────────────────────────────────────────────┘
```

### 3.2 Design Principles
- **No global mutable state** outside `SimulationEngine`
- **Events are pure callbacks**: `callback(engine, node, **kwargs)` — no side effects outside node state
- **PHY is a swappable plugin**: MAC never calls channel model directly, always via `PhyAbstraction` interface
- **Layers communicate only through the DES event queue** — no direct cross-layer function calls at runtime
- **OpenGym hook is a first-class observer** — no retrofitting needed

---

## 4. Repository Structure

```
wifi-netsim/
├── netsim/                        # importable package: `import netsim`
│   ├── core/
│   │   ├── engine.py              # DES event queue, simulation clock
│   │   ├── node.py                # AP / STA base node class
│   │   ├── registry.py            # global node & link registry
│   │   └── config.py              # YAML/dict config loader & validator
│   ├── mac/
│   │   ├── edca.py                # EDCA queues, backoff counter, AIFS/DIFS/SIFS timing
│   │   ├── mlo.py                 # MLOLinkManager: STR / EMLSR / EMLMR state machines
│   │   ├── ampdu.py               # A-MPDU aggregation engine & BA session scoreboard
│   │   ├── nav.py                 # NAV / virtual carrier sense
│   │   └── frame.py               # 802.11be frame dataclasses (MPDU, A-MPDU, Mgmt)
│   ├── phy/
│   │   ├── base.py                # PhyAbstraction ABC (plugin interface)
│   │   ├── tgbe_channel.py        # Standalone: TGbe D/E path loss + log-normal shadowing
│   │   └── matlab_phy.py          # MATLAB engine bridge (optional, graceful fallback)
│   ├── network/
│   │   ├── bss.py                 # BSS-only mode (single AP + STAs)
│   │   ├── ip_layer.py            # UDP/TCP traffic sources, static IP routing
│   │   └── multi_ap.py            # DS + roaming + Multi-AP coordination (Phase 3)
│   ├── traffic/
│   │   └── generators.py          # Poisson, CBR, VoIP, video burst traffic models
│   ├── observe/
│   │   ├── logger.py              # Structured text logger + CSV metrics writer
│   │   ├── pcap.py                # PCAP writer (libpcap format, radiotap headers)
│   │   └── viz.py                 # matplotlib live plot + optional Flask dashboard
│   └── gym/
│       └── env.py                 # OpenAI Gym / Gymnasium env wrapper (RL hook)
├── cli/
│   └── main.py                    # Entry point: `netsim run config.yaml`
├── configs/
│   └── examples/
│       ├── mlo_str_basic.yaml
│       ├── mlo_emlsr_2sta.yaml
│       └── mlo_emlmr_multiap.yaml
├── tests/
│   ├── unit/                      # MAC state machine, EDCA, BA scoreboard
│   ├── integration/               # Full scenario YAML → assert CSV metrics
│   └── fixtures/                  # Golden CSV files for regression
├── docs/
│   └── superpowers/specs/
├── notebooks/
│   └── mlo_throughput_demo.ipynb
└── pyproject.toml                 # package metadata, deps, CLI entry point
```

---

## 5. Core DES Engine

### 5.1 Simulation Clock
- **Resolution:** 64-bit integer, nanoseconds
- **Reason:** 802.11be minimum timing unit is 1 slot = 9 µs = 9,000 ns; SIFS = 16,000 ns — integer ns avoids floating-point drift across millions of events

### 5.2 Event Queue
```python
# Conceptual structure
Event(time_ns: int, priority: int, callback: Callable, kwargs: dict)
# Queue: heapq sorted by (time_ns, priority)
# Priority tiers: PHY_COMPLETE=0, MAC_DECISION=1, TRAFFIC_GEN=2
```

### 5.3 Timing Constants (802.11be, 6 GHz band default)
| Symbol | Value | Description |
|--------|-------|-------------|
| aSlotTime | 9 µs | Backoff slot |
| SIFS | 16 µs | Short IFS |
| DIFS | 34 µs | DCF IFS |
| AIFS[AC] | SIFS + AIFSN×aSlotTime | Per-AC IFS |
| TXOP limits | per AC per standard table | Max TXOP duration |

### 5.4 MATLAB PHY Deferred Event Pattern
MAC does not block waiting for MATLAB. Instead:
1. MAC schedules `PHY_REQUEST` event with frame params
2. Engine fires it; `MatlabWlanPhy.request_tx()` calls MATLAB engine synchronously (MATLAB is fast for single-frame ops)
3. MATLAB returns result; PHY schedules `PHY_RESPONSE` event at `now + computed_duration_ns`
4. MAC resumes on `PHY_RESPONSE`

This keeps the DES loop single-threaded and deterministic.

---

## 6. MLO MAC State Machine

### 6.1 Node Structure
Each AP/STA node contains:
- One `MLOLinkManager` — owns N `LinkContext` objects (one per band/link)
- One shared `BlockAckTable` — BA sessions indexed by (peer_mac, tid, link_id)
- One `EDCAScheduler` — manages 4 ACs (BE, BK, VI, VO) across all links

### 6.2 LinkContext State Machine
```
IDLE ──backoff_start──► BACKOFF ──channel_clear──► TXOP_GRANTED
  ▲                         │                           │
  │                   nav_busy/collision            frame_sent
  │                         │                           │
  └─────────────────── IDLE ◄── WAIT_BA ◄─── TRANSMITTING
                                    │
                              ba_timeout → retransmit / drop
```

### 6.3 MLO Mode Behaviors

**STR (Simultaneous Transmit & Receive):**
- All `LinkContext` instances run independent EDCA backoffs
- Frames can be in-flight on multiple links simultaneously
- BA sessions are per-link; MSDUs may be split across links by TID-to-link mapping
- No cross-link interference modeled at MAC (handled by PHY SNR computation)

**EMLSR (Enhanced Multi-Link Single Radio):**
- `MLOLinkManager` tracks a single `active_radio_link`
- All non-active links remain in IDLE, monitoring for trigger frames
- On EMLSR trigger frame received on link L:
  - Pause backoff on all other links
  - Schedule `EMLSR_TRANSITION` event at `now + transition_delay_ns` (configurable 0–256 µs)
  - After transition: set `active_radio_link = L`, resume EDCA on L
- On TXOP end: release all links to resume independent backoff

**EMLMR (Enhanced Multi-Link Multi-Radio):**
- Extends EMLSR to N radios (N configurable per node)
- `LinkSelectionPolicy` is a pluggable class:
  - `RoundRobinPolicy` — default
  - `LoadBalancePolicy` — assign link with shortest queue
  - `RLAgentPolicy` — delegates to gym env action (Phase 3+)

### 6.4 A-MPDU & Block Acknowledgement
- `AmpduAggregator` collects MSDUs up to min(TXOP_remaining, max_ampdu_len, 256 subframes)
- BA scoreboard: 256-bit bitmap per session (802.11-2020 §10.24.3)
- Immediate BA: BA sent within SIFS after A-MPDU reception
- BA timeout: configurable (default 10 ms); triggers retransmit of unacked subframes

---

## 7. PHY Abstraction Layer

### 7.1 Plugin Interface
```python
class PhyAbstraction(ABC):
    def request_tx(self, frame: Frame, link: LinkContext) -> TxResult: ...
        # Returns: duration_ns, success, mcs_used, bytes_sent
    
    def request_rx(self, frame: Frame, channel: ChannelState) -> RxResult: ...
        # Returns: success (bool), snr_db, per (packet error rate)
    
    def get_channel_state(self, src_id, dst_id, link_id) -> ChannelState: ...
        # Returns: snr_db, interference_db, bandwidth_mhz, mcs_index
```

### 7.2 TGbeChannel (Standalone)
- **Path loss model:** TGbe Model D (indoor office, NLOS) and Model E (large open space)
  - Reference: ns-3 `WifiPhy` TGbe channel implementation (IEEE 802.11-09/0308r1)
- **Shadowing:** log-normal, σ = 4 dB (Model D) / 6 dB (Model E)
- **Interference:** per-link SINR computed from all active TXOPs at each PHY slot boundary
- **MCS selection:** SNR→MCS lookup from 802.11be Table 36-124 (EHT MCS 0–13, up to 4096-QAM 5/6)
- **Bandwidth:** 20/40/80/160/320 MHz channel models

### 7.3 MatlabWlanPhy (Optional)
- **Dependency:** `matlabengine` Python package + MATLAB R2023b+ with WLAN Toolbox
- **Loose mode (no MATLAB running):** Use pre-exported CSV lookup tables generated offline via `scripts/generate_matlab_tables.m`
- **Medium mode (runtime):** Single MATLAB engine instance started at sim init; calls:
  - `wlanWaveformGenerator` — generate EHT waveform parameters
  - `wlanTGbeChannel` — apply TGbe channel model
  - `wlanRecoveryConfig` — decode and return PER/SNR
- **Fallback:** If `import matlab.engine` fails → log warning → auto-use `TGbeChannel`
- **Interface contract:** Identical `PhyAbstraction` API — MAC layer is unaware of which PHY is active

---

## 8. Network Layer Modes

Configured via `network.mode` in YAML. Modes are additive.

### Mode: `bss`
- Single `BasicServiceSet`: 1 AP + up to 50 STAs
- No IP routing; frames addressed directly AP↔STA
- All traffic generators attach to STAs or AP

### Mode: `ip`
- Multiple BSSs connected via ideal wired Distribution System (DS)
- Static IP routing table (no dynamic routing protocols)
- Traffic sources: UDP (CBR, Poisson), TCP (bulk transfer), VoIP (G.711), Video (H.265 burst)
- ARP modeled as a single-event lookup (no broadcast storms)

### Mode: `multi_ap`
- Extends `ip` with:
  - AP-to-AP coordination channel (ideal backhaul, configurable latency)
  - Roaming: STA triggers reassociation DES event on RSSI threshold
  - Placeholder hooks for Phase 3 C-OFDMA and Co-SR

---

## 9. Observability & Output

All outputs are opt-in via config flags or CLI arguments.

| Output | CLI Flag | Config Key | Format | Notes |
|--------|----------|-----------|--------|-------|
| Text log | `--log` | `obs.log: true` | Structured text | Per-event, timestamped |
| CSV metrics | `--csv` | `obs.csv: true` | CSV | Per-STA, per-link, per-interval |
| PCAP | `--pcap` | `obs.pcap: true` | libpcap | One file per link; radiotap with MLO link ID, MCS, BW |
| Visualization | `--viz` | `obs.viz: true` | matplotlib / Flask | Live topology + queue depths + throughput |
| Gym obs | internal | `obs.gym: true` | dict | Called each sim step when gym env active |

PCAP radiotap header includes:
- MLO link ID (custom namespace)
- MCS index, spatial streams, bandwidth
- RSSI, noise floor
- Timestamp (ns precision)

---

## 10. YAML Configuration Format

```yaml
simulation:
  duration_us: 1000000       # 1 second
  seed: 42
  
network:
  mode: ip                   # bss | ip | multi_ap

phy:
  backend: tgbe              # tgbe | matlab
  channel_model: D           # D | E
  matlab_mode: medium        # loose | medium (only if backend: matlab)

nodes:
  - id: ap0
    type: ap
    links: [2g, 5g, 6g]
    mlo_mode: str
    position: [0, 0]
  - id: sta0
    type: sta
    links: [5g, 6g]
    mlo_mode: emlsr
    emlsr_transition_delay_us: 64
    position: [5, 3]

traffic:
  - src: sta0
    dst: ap0
    type: udp_cbr
    rate_mbps: 100
    ac: BE

obs:
  log: true
  csv: true
  pcap: false
  viz: false
```

---

## 11. MATLAB Integration Guide

### Setup
```bash
pip install matlabengine          # must match installed MATLAB version
# In MATLAB: cd(matlabroot); cd extern/engines/python; python setup.py install
```

### Loose Mode (offline tables)
```bash
# Run once to generate lookup tables:
matlab -batch "run('scripts/generate_matlab_tables.m')"
# Generates: configs/matlab_tables/snr_mcs_eht.csv
```

### Medium Mode (runtime)
```python
import netsim
sim = netsim.Simulation.from_yaml("configs/examples/mlo_str_basic.yaml")
sim.config.phy.backend = "matlab"
sim.config.phy.matlab_mode = "medium"
sim.run()
```

### CI / No-MATLAB Environments
Tests that require MATLAB are decorated `@pytest.mark.matlab` and skipped unless `--matlab` flag passed. All other tests use `TGbeChannel`.

---

## 12. Testing Strategy

### Unit Tests (`tests/unit/`)
- EDCA backoff counter decrement and freeze/resume
- NAV setting and expiry
- A-MPDU aggregation boundary conditions (max subframes, TXOP limit)
- BA scoreboard: ack, reorder, gap detection, timeout
- MLO STR: independent link backoffs don't interfere
- EMLSR transition: correct link freeze/resume on trigger frame
- EMLMR policy: round-robin and load-balance link assignment

### Integration Tests (`tests/integration/`)
- STR throughput: 2-link STR STA must achieve >1.8× single-link throughput
- EMLSR: verify only one link in TXOP at a time
- EMLMR: N-radio STA achieves near-N× throughput under ideal conditions
- PCAP output: Wireshark can open and decode all generated files
- MATLAB fallback: if `matlab.engine` missing, sim runs with `TGbeChannel` without error

### Regression Suite (`tests/fixtures/`)
- Golden CSV files for each example YAML scenario
- CI asserts: metric values within ±1% of golden (deterministic with fixed seed)

---

## 13. Phased Delivery Roadmap

| Phase | Feature Set | Target Scale |
|-------|------------|-------------|
| 1 | MLO (STR + EMLSR + EMLMR), EDCA, A-MPDU, BA, TGbeChannel, MATLAB bridge | 5 APs, 50 STAs |
| 2 | NPCA, dynamic channel bonding | 5 APs, 50 STAs |
| 3 | Multi-AP Coordination (C-OFDMA, Co-SR), roaming | 10 APs, 100 STAs |
| 4 | WiFi 8 features, Mesh (802.11s), RL agent policy | 20+ APs, 200+ STAs |

---

## 14. Dependencies

```toml
[project]
name = "wifi-netsim"
requires-python = ">=3.10"

dependencies = [
    "pyyaml>=6.0",          # config loading
    "numpy>=1.24",           # channel math, SNR tables
    "matplotlib>=3.7",       # visualization
    "scapy>=2.5",            # PCAP writing (radiotap)
    "flask>=3.0",            # optional web dashboard
    "gymnasium>=0.29",       # OpenAI Gym env wrapper
    "pytest>=7.4",           # test runner
]

# Optional:
# matlabengine — MATLAB WLAN Toolbox bridge
```

---

*Spec written 2026-04-13. Phase 1 implementation to follow.*
