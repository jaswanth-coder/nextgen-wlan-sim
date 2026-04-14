# Phase 2 Design: MATLAB PHY Integration + Full NPCA
**Date:** 2026-04-14  
**Project:** nextgen-wlan-sim (nxwlansim)  
**Status:** Approved — ready for implementation

---

## 1. Goals

1. Replace the TGbeChannel stub with a research-accurate PHY backend driven by MATLAB WLAN Toolbox.
2. Implement Full NPCA (Non-Primary Channel Access) per IEEE 802.11be §35.3.3 — preamble puncturing, per-subchannel NAV, coordinated secondary-channel access.
3. Keep CI green without MATLAB installed (fixture tables + `pytest.mark.matlab` guard).
4. Zero changes to engine or engine API — PHY changes hidden behind `PhyBackend`; MAC changes are additive only (new fields + one hook in `_attempt_txop`).

---

## 2. Scope

**In Phase 2:**
- MATLAB-generated, HDF5-cached PER/SNR tables (TGbe-D, TGbe-E, custom `.mat`)
- `AdaptivePhy` orchestrator wired into `builder.py`
- Full NPCA engine: preamble puncturing, per-subchannel NAV, coordinated NAV propagation
- NPCA metrics: opportunities, used count, throughput gain
- Two new example YAML configs (npca_basic, npca_coordinated)
- Test fixtures + unit + integration test suite

**Not in Phase 2 (Phase 3):**
- Multi-AP coordination (C-OFDMA, Co-SR)
- Gymnasium RL env (`gym/env.py` step logic)
- Flask web dashboard
- WiFi 8 320 MHz / 16-stream features

---

## 3. Architecture

```
nxwlansim/
  phy/
    base.py                   (unchanged)
    tgbe_channel.py            (unchanged — fallback)
    interference.py            (unchanged)
    matlab/
      __init__.py
      generator.py             ← MATLAB table generation
      cache.py                 ← HDF5 read/write, hash invalidation
      table_phy.py             ← pure-Python interpolation
      live_phy.py              ← thin matlab.engine wrapper (cache miss)
      adaptive_phy.py          ← orchestrator, implements PhyBackend
  mac/
    npca.py                    ← NPCAEngine (new)
    mlo.py                     ← LinkContext: per-subchannel NAV added
    txop.py                    ← NPCAEngine hook in _attempt_txop
    ampdu.py                   ← punctured_mask + effective_bw_mhz on AMPDUFrame
  observe/
    metrics.py                 ← NPCA counters added
  configs/examples/
    npca_basic.yaml
    npca_coordinated.yaml
  tests/
    phy/
      test_table_phy.py
      test_cache.py
      test_matlab_generator.py  (matlab mark)
      test_live_phy.py          (matlab mark)
    mac/
      test_npca.py
      test_npca_coordination.py
    fixtures/
      tgbe_d_fixture.h5         ← small pre-committed table (3 MCS × 10 SNR)
```

**Key invariant:** `AdaptivePhy` is the only class `builder.py` ever instantiates when `phy.backend = matlab`. MAC layer and engine are unchanged.

---

## 4. MATLAB PHY Pipeline

### 4.1 Table Content

For each `{channel_model × bandwidth_mhz × mcs_index × n_tx × n_rx}`:

| Field | Values |
|-------|--------|
| `channel_model` | `D`, `E`, `custom` |
| `bandwidth_mhz` | `20, 40, 80, 160, 320` |
| `mcs_index` | `0–13` (802.11be) |
| `n_tx × n_rx` | `1×1, 2×2, 4×4` |
| `snr_db` | `-5.0` to `40.0` in `0.5 dB` steps (91 points) |

Output per entry: `snr_db[91] → per[91], tput_mbps[91]`

### 4.2 `generator.py` — `MatlabTableGenerator`

```
MatlabTableGenerator(engine=None)
  .generate(channel_configs: list[ChannelConfig]) → TableSet
    - starts matlab.engine("-nodisplay -nosplash") if not provided
    - for each combo: wlanTGbeChannel + wlanWaveformGenerator + awgn + wlanRecovery
    - custom channel: eng.load(mat_path) → inject channel matrix
    - returns TableSet dict keyed by (model, bw, mcs, n_tx, n_rx)
    - logs progress per combo
```

MATLAB functions used: `wlanTGbeChannel`, `wlanWaveformGenerator`, `wlanEHTMUConfig`,
`wlanEHTSUConfig`, `awgn`, `wlanEHTRecoveryConfig`, `wlanRecovery`.

### 4.3 `cache.py` — `TableCache`

```
TableCache(cache_dir: str = "~/.nxwlansim/phy_tables")
  .load(params: CacheKey) → TableSet | None
  .save(params: CacheKey, tables: TableSet)
  .invalidate(params: CacheKey)

CacheKey = SHA256(channel_model + bw_list + mcs_range + snr_step + matlab_version)
Storage: <cache_dir>/<hash>.h5  (HDF5 via h5py)
```

Cache miss triggers → `MatlabTableGenerator.generate()` → `TableCache.save()`.  
Custom channel: hash includes SHA256 of `.mat` file content.

### 4.4 `table_phy.py` — `TablePhy`

Pure Python, no MATLAB import. CI-safe.

```
TablePhy(tables: TableSet, path_loss_model: TGbeChannel)
  .get_channel_state(src, dst, link_id) → ChannelState
    - distance → path-loss → SNR  (uses existing TGbeChannel.path_loss())
    - interpolate(tables[mcs], snr) → per, tput_mbps
    - select best MCS where per < per_threshold (default 0.1)
    - return ChannelState(snr_db, mcs_index, per, bandwidth_mhz)

  .request_tx(frame, link_ctx) → TxResult
    - Bernoulli(per) draw → success/fail
    - duration = frame.size_bytes × 8 / tput_mbps

  .request_rx(frame, channel) → RxResult
    - independent Bernoulli draw per subframe
```

### 4.5 `live_phy.py` — `MatlabLivePhy`

Called only on cache miss (custom channel not yet cached).

```
MatlabLivePhy(engine: matlab.engine)
  .get_channel_state(src, dst, link_id) → ChannelState
    - eng.wlanTGbeChannel(snr, model, bw, mcs)
    - returns ChannelState; result inserted into TableCache
```

### 4.6 `adaptive_phy.py` — `AdaptivePhy`

Orchestrator. Implements `PhyBackend`. This is what `builder.py` instantiates.

```
AdaptivePhy(config: PhyConfig, registry: NodeRegistry)
  .__init__():
    - TableCache.load(params)
      → hit:  TablePhy(tables)
      → miss: MatlabTableGenerator.generate() → cache → TablePhy
    - if custom channel and not cached: MatlabLivePhy ready as fallback
  .get_channel_state() → delegates to TablePhy (fast path always)
  .request_tx()        → delegates to TablePhy
  .request_rx()        → delegates to TablePhy
  .register_node()     → delegates to TablePhy.path_loss_model
```

### 4.7 Config

```yaml
phy:
  backend: matlab
  channel_model: D          # D | E | custom
  custom_channel: ~          # path/to/channel.mat (optional)
  cache_dir: ~/.nxwlansim/phy_tables
  snr_step_db: 0.5
  per_threshold: 0.1
  force_regenerate: false
```

---

## 5. Full NPCA

### 5.1 Sub-channel Model

A 320 MHz MLO link is divided into 4×80 MHz sub-channels, indexed 0–3.  
A `punctured_mask` bitmask marks which sub-channels are excluded from TX.  
`effective_bw_mhz = total_bw × popcount(~punctured_mask) / n_subchannels`

### 5.2 `LinkContext` additions (`mlo.py`)

```python
sub_nav: dict[int, int]   # subchannel_id → nav_expiry_ns
punctured_mask: int = 0

def free_subchannels(now_ns) → list[int]   # subchannels with clear NAV
def set_sub_nav(subchannel_id, duration_ns, now_ns)
```

### 5.3 `npca.py` — `NPCAEngine`

```
NPCAEngine(node, engine)
  .evaluate(link_id, engine_now_ns) → NPCADecision
    - primary subchannel (idx 0) busy? → check secondaries
    - free_mask = bitmask of free secondary subchannels
    - if any free: use_npca=True, punctured_mask = ~free_mask & all_mask
    - if primary free: use_npca=False (normal TX)
    - returns NPCADecision(use_npca, free_mask, punctured_mask, effective_bw_mhz)

  .coordinate(link_id, duration_ns, engine)
    - propagates secondary sub-channel NAV to all nodes on same link
    - calls ctx.set_sub_nav() on each neighbour's LinkContext
```

### 5.4 `AMPDUFrame` additions (`ampdu.py`)

```python
punctured_mask: int = 0        # 0 = no puncturing
effective_bw_mhz: float = 0.0  # computed from punctured_mask
```

`AmpduAggregator.build_ampdu()` accepts `punctured_mask`, sets `effective_bw_mhz`,
adjusts MCS lookup to use `effective_bw_mhz` column in PHY table.

### 5.5 `txop.py` hook

In `_attempt_txop()`, after TXOP granted:
```python
npca = self.node.npca_engine.evaluate(link_id, engine.now_ns)
if npca.use_npca:
    self.node.npca_engine.coordinate(link_id, txop_limit_ns, engine)
# pass npca.punctured_mask into build_ampdu()
```

`builder.py` attaches `NPCAEngine` to every node (alongside existing MAC components).

### 5.6 NPCA Metrics (`metrics.py`)

```
Per-node counters added to MetricsCollector:
  npca_opportunities  — primary busy, secondary checked
  npca_used           — secondary TX actually fired
  npca_tput_gain_mbps — extra bytes from NPCA vs. waiting
```

CSV gains columns: `npca_opportunities, npca_used, npca_gain_mbps`

---

## 6. New Example Configs

**`configs/examples/npca_basic.yaml`**  
1 AP + 2 STAs, STR, 320 MHz (4 sub-channels), heavy BE load on primary, NPCA enabled.

**`configs/examples/npca_coordinated.yaml`**  
1 AP + 4 STAs, STR, 320 MHz, coordinated NPCA across all STAs to demonstrate collision-free secondary access.

---

## 7. Testing Strategy

### Unit tests (no MATLAB required — CI safe)

| Test file | What it covers |
|-----------|---------------|
| `tests/phy/test_table_phy.py` | Interpolation correctness, PER boundary values |
| `tests/phy/test_cache.py` | Hash invalidation, round-trip save/load |
| `tests/mac/test_npca.py` | NPCADecision logic, punctured_mask, sub-NAV expiry |
| `tests/mac/test_npca_coordination.py` | Two-STA collision prevention via coordinated NAV |

Fixture: `tests/fixtures/tgbe_d_fixture.h5` — tiny pre-committed table (3 MCS × 10 SNR points, TGbe-D, 80 MHz).

### Integration tests (require MATLAB — `@pytest.mark.matlab`)

| Test file | What it covers |
|-----------|---------------|
| `tests/phy/test_matlab_generator.py` | Real table generation, PER monotonicity |
| `tests/phy/test_live_phy.py` | Custom `.mat` channel, cache warming |

### Regression

- All 85 existing tests pass unchanged.
- New golden: `mlo_str_basic.yaml` with `backend: matlab` uses fixture tables; throughput within 5% of tgbe baseline.

---

## 8. Dependencies Added

```toml
[project.optional-dependencies]
matlab = ["matlabengine>=24.2", "h5py>=3.10"]
dev    = [...existing..., "h5py>=3.10"]
```

`h5py` added to base deps (needed for cache even without MATLAB).  
`matlabengine` stays optional — sim degrades gracefully to tgbe if absent.

---

## 9. Implementation Order

1. `phy/matlab/cache.py` + `table_phy.py` + fixture table → unit tests green
2. `phy/matlab/generator.py` + `live_phy.py` + `adaptive_phy.py`
3. `builder.py` wiring for `backend: matlab`
4. `mac/mlo.py` sub-channel NAV additions
5. `mac/npca.py` NPCAEngine
6. `mac/ampdu.py` + `mac/txop.py` NPCA hooks
7. `observe/metrics.py` NPCA counters
8. Example YAML configs
9. Full test suite
10. CLAUDE.md update
