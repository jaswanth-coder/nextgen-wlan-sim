# nextgen-wlan-sim

A pure-Python discrete-event network simulator for **IEEE 802.11be (WiFi 7/8)** next-generation WLAN technologies.

**Phase 1 focus:** Multi-Link Operation (MLO) — STR, EMLSR, EMLMR  
**Upcoming:** NPCA · Multi-AP Coordination · C-OFDMA · WiFi 8

---

## Features

| Layer | What's modeled |
|-------|---------------|
| MAC | Cycle-accurate EDCA backoff, TXOP, A-MPDU, Block ACK, NAV |
| MLO | STR / EMLSR / EMLMR link managers, TID-to-link mapping |
| PHY | Pluggable: TGbe D/E channel (standalone) or MATLAB WLAN Toolbox (runtime) |
| Network | BSS-only · IP/UDP/TCP multi-AP · Full Multi-AP DS+roaming |
| Output | Text logs · CSV metrics · PCAP (Wireshark) · matplotlib viz · Gym env hook |

---

## Install

### From GitHub (recommended)
```bash
pip install git+https://github.com/jaswanth-coder/nextgen-wlan-sim.git
```

### From source
```bash
git clone https://github.com/jaswanth-coder/nextgen-wlan-sim.git
cd nextgen-wlan-sim
pip install -e ".[dev]"
```

### With MATLAB support
```bash
pip install -e ".[dev]"
# Then install matlabengine matching your MATLAB version:
pip install matlabengine==<your_matlab_version>
```

---

## Quick Start

### As a CLI tool
```bash
nxwlansim run configs/examples/mlo_str_basic.yaml
nxwlansim run configs/examples/mlo_emlsr_2sta.yaml --csv --pcap
```

### As a Python library
```python
import nxwlansim as nx

sim = nx.Simulation.from_yaml("configs/examples/mlo_str_basic.yaml")
results = sim.run()
print(results.summary())
```

### In a Jupyter notebook
```python
from nxwlansim import Simulation, quick_scenario

# Build a 2-link STR scenario programmatically
scenario = quick_scenario(
    mode="str",
    n_links=2,
    n_stas=5,
    duration_us=500_000,
)
results = scenario.run()
results.plot_throughput()
```

---

## YAML Configuration

```yaml
simulation:
  duration_us: 1000000
  seed: 42

network:
  mode: ip                  # bss | ip | multi_ap

phy:
  backend: tgbe             # tgbe | matlab
  channel_model: D          # D | E
  matlab_mode: medium       # loose | medium

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

## MATLAB Integration

### Loose mode (offline tables — no MATLAB at runtime)
```bash
matlab -batch "run('scripts/generate_matlab_tables.m')"
# Sets phy.backend: matlab, phy.matlab_mode: loose in your config
```

### Medium mode (MATLAB engine at runtime)
```bash
# Install matching matlabengine, then:
nxwlansim run config.yaml --phy-backend matlab --matlab-mode medium
```

If MATLAB is unavailable, the simulator automatically falls back to the built-in `TGbeChannel` with a warning.

---

## Project Roadmap

- [x] Phase 1 — MLO (STR · EMLSR · EMLMR)
- [ ] Phase 2 — NPCA (Non-Primary Channel Access)
- [ ] Phase 3 — Multi-AP Coordination (C-OFDMA, Co-SR)
- [ ] Phase 4 — WiFi 8, Mesh (802.11s)

---

## Repository Structure

```
nxwlansim/
├── core/        # DES engine, clock, node registry
├── mac/         # EDCA, MLO, A-MPDU, BA, NAV, frame structures
├── phy/         # PHY plugin interface, TGbe channel, MATLAB bridge
├── network/     # BSS, IP, Multi-AP network modes
├── traffic/     # Traffic generators (CBR, Poisson, VoIP, video)
├── observe/     # Logger, CSV, PCAP, visualization
└── gym/         # OpenAI Gymnasium env wrapper
```

---

## License

MIT
