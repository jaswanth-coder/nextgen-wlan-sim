# Algorithm Research Guide — nxwlansim

## How this simulator helps you build & test new algorithms

---

### What the simulator gives you as a platform

It's a controlled lab. You define the network, run time, and traffic — the simulator handles all the low-level 802.11be mechanics (backoff, TXOP, A-MPDU, BA, channel model). You just plug in your algorithm.

---

### 1. Traffic Allocation Algorithms

**What it means:** Deciding which STA gets how much airtime, on which link, at what priority.

**Where to plug in:** `mac/edca.py` — the EDCA scheduler decides queue priorities and CW (contention window) sizes. Replace or modify the scheduling logic there with your own (e.g. weighted fair queuing, deadline-aware scheduling, RL-based).

**How the simulator helps:** Run the same scenario with your algorithm vs. the default EDCA and compare `results.summary()` — throughput, BA timeouts, latency from the CSV.

---

### 2. Channel Selection Algorithms

**What it means:** Deciding which link (5g / 6g) to use for a given transmission, or dynamically switching.

**Where to plug in:** `mac/mlo.py` — the MLOLinkManager picks links per TXOP. You can write a new selection policy (e.g. load-aware, SINR-based, learned).

**How the simulator helps:** The PHY backend gives you per-link SINR and MCS via `phy.get_channel_state()`. Your algorithm reads that, picks a link, and the simulator shows you the throughput/retransmission impact.

---

### 3. MLO Performance Analysis

**What it means:** Comparing STR vs eMLSR vs eMLMR under different loads, distances, and traffic mixes.

**Where to plug in:** No code change needed — just swap `mlo_mode` in the config YAML. Run multiple configs, collect the CSV outputs, and compare.

**How the simulator helps:** The link-state Gantt chart (`link_states.png`) visually shows you when each link is active — you can see the difference between STR (both links busy simultaneously) and eMLSR (one link at a time with transition delay).

---

### General Workflow for Any New Algorithm

```
1. Write your algorithm in the relevant mac/ or phy/ file
2. Run the same YAML scenario with old vs new
3. Compare: results.summary() table + metrics.csv + plots
4. Tune and repeat
```

The simulator is deterministic (fixed seed), so differences between runs are purely from your algorithm — not randomness.
