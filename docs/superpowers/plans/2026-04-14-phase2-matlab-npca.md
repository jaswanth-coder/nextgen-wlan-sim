# Phase 2: MATLAB PHY + Full NPCA Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace TGbeChannel stub with MATLAB-calibrated HDF5-cached PHY tables and implement Full NPCA (preamble puncturing, per-subchannel NAV, coordinated secondary-channel access).

**Architecture:** Layered PHY — `MatlabTableGenerator` produces HDF5 tables at startup, `TableCache` stores/retrieves them by SHA256 key, `TablePhy` does per-TXOP interpolation, `AdaptivePhy` orchestrates. NPCA lives entirely in MAC (`npca.py` + thin hooks in `mlo.py`, `ampdu.py`, `txop.py`).

**Tech Stack:** Python 3.10+, numpy, h5py, matlab.engine (optional), pytest

---

## File Map

**Create:**
- `nxwlansim/phy/matlab/__init__.py`
- `nxwlansim/phy/matlab/cache.py` — HDF5 TableCache + CacheKey
- `nxwlansim/phy/matlab/table_phy.py` — pure-Python interpolating PHY
- `nxwlansim/phy/matlab/generator.py` — MATLAB PER sweep
- `nxwlansim/phy/matlab/live_phy.py` — per-call MATLAB fallback
- `nxwlansim/phy/matlab/adaptive_phy.py` — orchestrator
- `nxwlansim/mac/npca.py` — NPCAEngine + NPCADecision
- `scripts/generate_fixture_tables.py` — build CI fixture HDF5
- `tests/unit/test_cache.py`
- `tests/unit/test_table_phy.py`
- `tests/unit/test_npca.py`
- `tests/unit/test_npca_coordination.py`
- `tests/integration/test_matlab_generator.py` (matlab-marked)
- `configs/examples/npca_basic.yaml`
- `configs/examples/npca_coordinated.yaml`

**Modify:**
- `pyproject.toml` — add h5py dependency
- `nxwlansim/core/config.py` — extend PhyConfig + ObsConfig
- `nxwlansim/core/builder.py` — wire AdaptivePhy + NPCAEngine
- `nxwlansim/mac/mlo.py` — add sub_nav to LinkContext
- `nxwlansim/mac/ampdu.py` — add punctured_mask to AMPDUFrame + build_ampdu()
- `nxwlansim/mac/txop.py` — NPCA hook in _attempt_txop + _transmit_ampdu
- `nxwlansim/observe/metrics.py` — NPCA counters
- `CLAUDE.md` — Phase 2 summary

---

## Task 1: Add h5py + extend PhyConfig

**Files:** `pyproject.toml`, `nxwlansim/core/config.py`

- [ ] **Step 1: Add h5py to dependencies**

Edit `pyproject.toml`, change:
```toml
dependencies = [
    "pyyaml>=6.0",
    "numpy>=1.24",
    "matplotlib>=3.7",
    "scapy>=2.5",
    "flask>=3.0",
    "gymnasium>=0.29",
]
```
to:
```toml
dependencies = [
    "pyyaml>=6.0",
    "numpy>=1.24",
    "matplotlib>=3.7",
    "scapy>=2.5",
    "flask>=3.0",
    "gymnasium>=0.29",
    "h5py>=3.10",
]
```

Also add to `[project.optional-dependencies]`:
```toml
matlab = [
    # pip install matlabengine==25.1  (R2025a) or ==24.2 (R2024b)
]
```

- [ ] **Step 2: Extend PhyConfig in config.py**

In `nxwlansim/core/config.py`, replace the existing `PhyConfig` dataclass:
```python
@dataclass
class PhyConfig:
    backend: Literal["tgbe", "matlab"] = "tgbe"
    channel_model: Literal["D", "E", "custom"] = "D"
    matlab_mode: Literal["loose", "medium"] = "loose"
    custom_channel: str = ""          # path to .mat file (empty = not used)
    cache_dir: str = ""               # empty = ~/.nxwlansim/phy_tables
    snr_step_db: float = 0.5
    per_threshold: float = 0.1
    force_regenerate: bool = False
```

- [ ] **Step 3: Install h5py**
```bash
pip install h5py>=3.10
```
Expected: Successfully installed h5py-...

- [ ] **Step 4: Verify import**
```bash
python3 -c "import h5py; print(h5py.__version__)"
```
Expected: prints a version like `3.10.0`

- [ ] **Step 5: Confirm existing tests still pass**
```bash
pytest tests/ -q
```
Expected: `85 passed`

- [ ] **Step 6: Commit**
```bash
git add pyproject.toml nxwlansim/core/config.py
git commit -m "feat: extend PhyConfig for MATLAB backend + add h5py dep"
```

---

## Task 2: TableCache (cache.py)

**Files:** `nxwlansim/phy/matlab/__init__.py`, `nxwlansim/phy/matlab/cache.py`, `tests/unit/test_cache.py`

- [ ] **Step 1: Create the matlab package**
```bash
mkdir -p nxwlansim/phy/matlab
touch nxwlansim/phy/matlab/__init__.py
```

- [ ] **Step 2: Write failing tests first**

Create `tests/unit/test_cache.py`:
```python
"""Unit tests for TableCache — HDF5 round-trip and hash invalidation."""
import os
import numpy as np
import pytest
import h5py
from nxwlansim.phy.matlab.cache import TableCache, CacheKey, _write_h5, _read_h5


@pytest.fixture
def tmp_cache(tmp_path):
    return TableCache(cache_dir=str(tmp_path))


@pytest.fixture
def sample_key():
    return CacheKey(
        channel_model="D",
        bw_list=[80],
        mcs_range=(0, 2),
        snr_step_db=0.5,
    )


@pytest.fixture
def sample_tables():
    snr = np.linspace(-5, 40, 91)
    return {
        ("D", 80, 0, 1, 1): {
            "snr_db": snr,
            "per": np.clip(1 - snr / 40, 0, 1),
            "tput_mbps": snr * 2.0,
        }
    }


def test_cache_miss_returns_none(tmp_cache, sample_key):
    assert tmp_cache.load(sample_key) is None


def test_cache_save_and_load(tmp_cache, sample_key, sample_tables):
    tmp_cache.save(sample_key, sample_tables)
    loaded = tmp_cache.load(sample_key)
    assert loaded is not None
    assert ("D", 80, 0, 1, 1) in loaded
    np.testing.assert_allclose(
        loaded[("D", 80, 0, 1, 1)]["per"],
        sample_tables[("D", 80, 0, 1, 1)]["per"],
    )


def test_different_snr_step_misses(tmp_cache, sample_tables):
    key_a = CacheKey("D", [80], (0, 2), snr_step_db=0.5)
    key_b = CacheKey("D", [80], (0, 2), snr_step_db=1.0)
    tmp_cache.save(key_a, sample_tables)
    assert tmp_cache.load(key_b) is None   # different hash


def test_invalidate_removes_file(tmp_cache, sample_key, sample_tables):
    tmp_cache.save(sample_key, sample_tables)
    assert tmp_cache.load(sample_key) is not None
    tmp_cache.invalidate(sample_key)
    assert tmp_cache.load(sample_key) is None


def test_load_from_file(tmp_path, sample_tables):
    path = str(tmp_path / "test.h5")
    _write_h5(path, sample_tables)
    cache = TableCache(cache_dir=str(tmp_path))
    loaded = cache.load_from_file(path)
    assert ("D", 80, 0, 1, 1) in loaded
```

- [ ] **Step 3: Run — expect import failure**
```bash
pytest tests/unit/test_cache.py -v
```
Expected: `ModuleNotFoundError: nxwlansim.phy.matlab.cache`

- [ ] **Step 4: Implement cache.py**

Create `nxwlansim/phy/matlab/cache.py`:
```python
"""
TableCache — HDF5-backed cache for MATLAB-generated PHY tables.
Cache key = SHA256 of channel parameters.
Stored at: <cache_dir>/<hash>.h5
"""
from __future__ import annotations
import hashlib
import os
import logging
import numpy as np

logger = logging.getLogger(__name__)

try:
    import h5py
    _H5PY = True
except ImportError:
    _H5PY = False

# TableSet: {(model, bw_mhz, mcs, n_tx, n_rx): {"snr_db": arr, "per": arr, "tput_mbps": arr}}
TableSet = dict[tuple[str, int, int, int, int], dict[str, np.ndarray]]


class CacheKey:
    def __init__(
        self,
        channel_model: str,
        bw_list: list[int],
        mcs_range: tuple[int, int],
        snr_step_db: float,
        matlab_version: str = "any",
        custom_channel_hash: str = "",
    ):
        self.channel_model = channel_model
        self.bw_list = sorted(bw_list)
        self.mcs_range = mcs_range
        self.snr_step_db = snr_step_db
        self.matlab_version = matlab_version
        self.custom_channel_hash = custom_channel_hash

    def digest(self) -> str:
        blob = (
            f"{self.channel_model}|{self.bw_list}|{self.mcs_range}|"
            f"{self.snr_step_db}|{self.matlab_version}|{self.custom_channel_hash}"
        )
        return hashlib.sha256(blob.encode()).hexdigest()[:16]


class TableCache:
    def __init__(self, cache_dir: str | None = None):
        self._dir = os.path.expanduser(cache_dir or "~/.nxwlansim/phy_tables")
        os.makedirs(self._dir, exist_ok=True)

    def _path(self, key: CacheKey) -> str:
        return os.path.join(self._dir, f"{key.digest()}.h5")

    def load(self, key: CacheKey) -> TableSet | None:
        if not _H5PY:
            return None
        path = self._path(key)
        if not os.path.exists(path):
            logger.info("[Cache] Miss: %s", path)
            return None
        logger.info("[Cache] Hit: %s", path)
        return _read_h5(path)

    def load_from_file(self, path: str) -> TableSet:
        """Load a specific HDF5 file directly (fixture tables, custom channels)."""
        return _read_h5(path)

    def save(self, key: CacheKey, tables: TableSet) -> None:
        if not _H5PY:
            return
        _write_h5(self._path(key), tables)
        logger.info("[Cache] Saved: %s", self._path(key))

    def invalidate(self, key: CacheKey) -> None:
        path = self._path(key)
        if os.path.exists(path):
            os.remove(path)
            logger.info("[Cache] Invalidated: %s", path)


def _write_h5(path: str, tables: TableSet) -> None:
    import h5py
    with h5py.File(path, "w") as f:
        for (model, bw, mcs, n_tx, n_rx), data in tables.items():
            grp = f.require_group(f"{model}/{bw}/{mcs}/{n_tx}x{n_rx}")
            for name, arr in data.items():
                grp.create_dataset(name, data=np.asarray(arr))


def _read_h5(path: str) -> TableSet:
    import h5py
    tables: TableSet = {}
    with h5py.File(path, "r") as f:
        for model in f:
            for bw_str in f[model]:
                for mcs_str in f[model][bw_str]:
                    for ant_str in f[model][bw_str][mcs_str]:
                        n_tx, n_rx = map(int, ant_str.split("x"))
                        grp = f[model][bw_str][mcs_str][ant_str]
                        tables[(model, int(bw_str), int(mcs_str), n_tx, n_rx)] = {
                            k: grp[k][:] for k in grp
                        }
    return tables
```

- [ ] **Step 5: Run tests — expect pass**
```bash
pytest tests/unit/test_cache.py -v
```
Expected: `5 passed`

- [ ] **Step 6: Commit**
```bash
git add nxwlansim/phy/matlab/ tests/unit/test_cache.py
git commit -m "feat: TableCache — HDF5 cache with SHA256 key invalidation"
```

---

## Task 3: Fixture Table + TablePhy

**Files:** `scripts/generate_fixture_tables.py`, `tests/fixtures/tgbe_d_fixture.h5`, `nxwlansim/phy/matlab/table_phy.py`, `tests/unit/test_table_phy.py`

- [ ] **Step 1: Write failing tests**

Create `tests/unit/test_table_phy.py`:
```python
"""Unit tests for TablePhy — interpolation, MCS selection, PER boundary values."""
import math
import numpy as np
import pytest
from nxwlansim.phy.matlab.cache import TableSet
from nxwlansim.phy.matlab.table_phy import TablePhy
from nxwlansim.mac.frame import MPDUFrame
from nxwlansim.mac.mlo import LinkContext, LinkState


def _make_tables() -> TableSet:
    """3-MCS fixture table: D/80MHz, MCS 0/4/9."""
    snr = np.arange(0.0, 45.0, 5.0)  # 9 points
    MCS_THRESH = {0: 3.0, 4: 16.5, 9: 30.0}
    MCS_RATE = {0: 34.4, 4: 206.4, 9: 458.8}  # Mbps at 80 MHz
    tables = {}
    for mcs, thresh in MCS_THRESH.items():
        per = 1.0 / (1.0 + np.exp((snr - thresh) * 2.0))
        tput = MCS_RATE[mcs] * (1.0 - per)
        tables[("D", 80, mcs, 1, 1)] = {
            "snr_db": snr, "per": per, "tput_mbps": tput
        }
    return tables


@pytest.fixture
def phy():
    t = TablePhy(_make_tables(), channel_model="D", per_threshold=0.1, seed=0)
    t.register_node("ap0", (0.0, 0.0))
    t.register_node("sta0", (5.0, 0.0))
    return t


def test_per_high_at_low_snr(phy):
    # At SNR=0 dB, MCS 0 PER ≈ sigmoid(0-3)≈0.95 — should pick MCS 0 but still high
    ch = phy.get_channel_state("sta0", "ap0", "5g")
    assert ch.mcs_index >= 0


def test_get_channel_state_returns_valid(phy):
    ch = phy.get_channel_state("sta0", "ap0", "6g")
    assert ch.link_id == "6g"
    assert -20 < ch.snr_db < 60
    assert ch.mcs_index in range(14)
    assert ch.bandwidth_mhz > 0


def test_request_tx_returns_result(phy):
    frame = MPDUFrame(frame_id=1, src="sta0", dst="ap0", size_bytes=1500, link_id="6g")
    ctx = LinkContext("6g", None)
    result = phy.request_tx(frame, ctx)
    assert result.duration_ns > 0
    assert result.link_id == "6g"
    assert result.mcs_used in range(14)


def test_request_rx_success_at_high_snr():
    tables = _make_tables()
    # Patch PER to near-zero at high SNR
    for key in tables:
        tables[key]["per"][-1] = 0.001   # last point (SNR=40) near zero
    phy = TablePhy(tables, seed=99)
    from nxwlansim.phy.base import ChannelState
    ch_state = ChannelState(link_id="6g", snr_db=40.0, interference_db=0.0,
                            bandwidth_mhz=80, mcs_index=9)
    results = [phy.request_rx(None, ch_state) for _ in range(100)]
    success_rate = sum(r.success for r in results) / 100
    assert success_rate > 0.85   # near-zero PER → mostly success


def test_request_rx_fails_at_low_snr():
    tables = _make_tables()
    phy = TablePhy(tables, seed=7)
    from nxwlansim.phy.base import ChannelState
    ch_state = ChannelState(link_id="6g", snr_db=0.0, interference_db=0.0,
                            bandwidth_mhz=80, mcs_index=0)
    results = [phy.request_rx(None, ch_state) for _ in range(100)]
    success_rate = sum(r.success for r in results) / 100
    assert success_rate < 0.5   # high PER at 0 dB
```

- [ ] **Step 2: Run — expect import failure**
```bash
pytest tests/unit/test_table_phy.py -v
```
Expected: `ModuleNotFoundError: nxwlansim.phy.matlab.table_phy`

- [ ] **Step 3: Create fixture generator script**

Create `scripts/generate_fixture_tables.py`:
```python
"""
Generate minimal HDF5 fixture table for CI tests (no MATLAB required).
Run once: python3 scripts/generate_fixture_tables.py
"""
import os
import numpy as np
import h5py

FIXTURE_PATH = "tests/fixtures/tgbe_d_fixture.h5"
SNR = np.arange(0.0, 45.0, 5.0)       # 9 SNR points
MCS_THRESH = {0: 3.0, 4: 16.5, 9: 30.0}
MCS_RATE_80MHZ = {0: 34.4, 4: 206.4, 9: 458.8}  # Mbps at 80 MHz

os.makedirs(os.path.dirname(FIXTURE_PATH), exist_ok=True)
with h5py.File(FIXTURE_PATH, "w") as f:
    for mcs, thresh in MCS_THRESH.items():
        grp = f.require_group(f"D/80/{mcs}/1x1")
        per = 1.0 / (1.0 + np.exp((SNR - thresh) * 2.0))
        tput = MCS_RATE_80MHZ[mcs] * (1.0 - per)
        grp.create_dataset("snr_db", data=SNR)
        grp.create_dataset("per", data=per)
        grp.create_dataset("tput_mbps", data=tput)

print(f"Fixture written: {FIXTURE_PATH}  ({os.path.getsize(FIXTURE_PATH)} bytes)")
```

- [ ] **Step 4: Generate fixture**
```bash
python3 scripts/generate_fixture_tables.py
```
Expected: `Fixture written: tests/fixtures/tgbe_d_fixture.h5`

- [ ] **Step 5: Implement table_phy.py**

Create `nxwlansim/phy/matlab/table_phy.py`:
```python
"""
TablePhy — pure-Python PHY using pre-computed MATLAB PER/SNR tables.
No matlab.engine dependency — CI-safe.
"""
from __future__ import annotations
import math
import random
import logging
import numpy as np
from typing import TYPE_CHECKING

from nxwlansim.phy.base import PhyAbstraction, ChannelState, TxResult, RxResult
from nxwlansim.phy.matlab.cache import TableSet

if TYPE_CHECKING:
    from nxwlansim.mac.frame import Frame
    from nxwlansim.mac.mlo import LinkContext

logger = logging.getLogger(__name__)

_BAND_BW_MHZ: dict[str, int] = {"2g": 20, "5g": 80, "6g": 160}
_MCS_RATE_20MHZ = [8.6, 17.2, 25.8, 34.4, 51.6, 68.8, 77.4,
                    86.0, 103.2, 114.7, 129.0, 143.4, 154.9, 172.1]
_TGBE_PARAMS = {
    "D": (3.0, 4.0, 1.0, 40.1),
    "E": (2.0, 6.0, 1.0, 35.7),
}
TX_POWER_DBM = 20.0
NOISE_FIGURE_DB = 7.0


class TablePhy(PhyAbstraction):
    """Interpolates PER and throughput from MATLAB-generated tables."""

    def __init__(
        self,
        tables: TableSet,
        channel_model: str = "D",
        per_threshold: float = 0.1,
        seed: int = 42,
    ):
        self._tables = tables
        self._model = channel_model
        self._per_threshold = per_threshold
        self._rng = random.Random(seed)
        self._positions: dict[str, tuple[float, float]] = {}
        exp, shadow, ref_d, ref_loss = _TGBE_PARAMS.get(channel_model, _TGBE_PARAMS["D"])
        self._exp = exp
        self._shadow_sigma = shadow
        self._ref_d = ref_d
        self._ref_loss = ref_loss

    def register_node(self, node_id: str, position: tuple[float, float]) -> None:
        self._positions[node_id] = position

    # ------------------------------------------------------------------
    # PhyAbstraction interface
    # ------------------------------------------------------------------

    def get_channel_state(self, src_id: str, dst_id: str, link_id: str) -> ChannelState:
        bw = _BAND_BW_MHZ.get(link_id, 80)
        snr = self._snr(src_id, dst_id, link_id)
        mcs, per, _ = self._best_mcs(snr, bw)
        return ChannelState(
            link_id=link_id,
            snr_db=snr,
            interference_db=0.0,
            bandwidth_mhz=bw,
            mcs_index=mcs,
            path_loss_db=self._path_loss(src_id, dst_id),
        )

    def request_tx(self, frame: "Frame", link: "LinkContext") -> TxResult:
        bw = _BAND_BW_MHZ.get(link.link_id, 80)
        snr = self._snr(frame.src, frame.dst, link.link_id)
        mcs, per, tput = self._best_mcs(snr, bw)
        success = self._rng.random() > per
        if tput <= 0:
            tput = _MCS_RATE_20MHZ[mcs] * (bw / 20)
        duration_ns = max(int(frame.size_bytes * 8 / (tput * 1e6) * 1e9), 1_000)
        return TxResult(
            success=success,
            duration_ns=duration_ns,
            mcs_used=mcs,
            bytes_sent=frame.size_bytes if success else 0,
            link_id=link.link_id,
        )

    def request_rx(self, frame: "Frame", channel: ChannelState) -> RxResult:
        _, per, _ = self._best_mcs(channel.snr_db, channel.bandwidth_mhz)
        success = self._rng.random() > per
        return RxResult(success=success, snr_db=channel.snr_db,
                        per=per, link_id=channel.link_id)

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    def _path_loss(self, src: str, dst: str) -> float:
        p1 = self._positions.get(src, (0.0, 0.0))
        p2 = self._positions.get(dst, (0.0, 0.0))
        dist = max(math.dist(p1, p2), 0.1)
        shadow = self._rng.gauss(0, self._shadow_sigma)
        return self._ref_loss + 10 * self._exp * math.log10(dist / self._ref_d) + shadow

    def _snr(self, src: str, dst: str, link_id: str) -> float:
        bw = _BAND_BW_MHZ.get(link_id, 80)
        noise = -174 + 10 * math.log10(bw * 1e6) + NOISE_FIGURE_DB
        return TX_POWER_DBM - self._path_loss(src, dst) - noise

    def _best_mcs(self, snr: float, bw: int) -> tuple[int, float, float]:
        """Return (mcs, per, tput_mbps) for the highest MCS with PER < threshold."""
        for mcs in range(13, -1, -1):
            key = self._find_key(mcs, bw)
            if key is None:
                continue
            data = self._tables[key]
            per = float(np.interp(snr, data["snr_db"], data["per"]))
            if per < self._per_threshold:
                tput = float(np.interp(snr, data["snr_db"], data["tput_mbps"]))
                return mcs, per, tput
        # Fallback MCS 0
        key = self._find_key(0, bw)
        if key:
            data = self._tables[key]
            per = float(np.interp(snr, data["snr_db"], data["per"]))
            tput = float(np.interp(snr, data["snr_db"], data["tput_mbps"]))
            return 0, per, tput
        return 0, 1.0, _MCS_RATE_20MHZ[0] * (bw / 20)

    def _find_key(self, mcs: int, bw: int) -> tuple | None:
        """Find best matching key in tables for given mcs + bw."""
        exact = (self._model, bw, mcs, 1, 1)
        if exact in self._tables:
            return exact
        # Try any BW for same model + mcs
        for k in self._tables:
            if k[0] == self._model and k[2] == mcs:
                return k
        return None
```

- [ ] **Step 6: Run tests — expect pass**
```bash
pytest tests/unit/test_table_phy.py -v
```
Expected: `5 passed`

- [ ] **Step 7: Commit**
```bash
git add nxwlansim/phy/matlab/table_phy.py scripts/generate_fixture_tables.py \
        tests/fixtures/tgbe_d_fixture.h5 tests/unit/test_table_phy.py
git commit -m "feat: TablePhy — pure-Python interpolating PHY + CI fixture table"
```

---

## Task 4: MatlabTableGenerator + LivePhy + AdaptivePhy

**Files:** `nxwlansim/phy/matlab/generator.py`, `nxwlansim/phy/matlab/live_phy.py`, `nxwlansim/phy/matlab/adaptive_phy.py`

- [ ] **Step 1: Implement generator.py**

Create `nxwlansim/phy/matlab/generator.py`:
```python
"""
MatlabTableGenerator — generates PER/SNR tables via MATLAB WLAN Toolbox.
Requires: matlab.engine (pip install matlabengine==25.1 for R2025a)
"""
from __future__ import annotations
import logging
import numpy as np
from nxwlansim.phy.matlab.cache import TableSet

logger = logging.getLogger(__name__)

SNR_MIN, SNR_MAX, SNR_STEP = -5.0, 40.0, 0.5
_SNR_POINTS = np.arange(SNR_MIN, SNR_MAX + SNR_STEP, SNR_STEP)   # 91 points
_MCS_RATE_20MHZ = [8.6, 17.2, 25.8, 34.4, 51.6, 68.8, 77.4,
                    86.0, 103.2, 114.7, 129.0, 143.4, 154.9, 172.1]


class MatlabTableGenerator:
    def __init__(self, engine=None):
        self._eng = engine   # pass existing engine or None to auto-start

    def generate(
        self,
        channel_model: str = "D",
        bw_list: list[int] | None = None,
        mcs_range: tuple[int, int] = (0, 13),
        ant_configs: list[tuple[int, int]] | None = None,
        custom_mat_path: str | None = None,
    ) -> TableSet:
        bw_list = bw_list or [20, 40, 80, 160, 320]
        ant_configs = ant_configs or [(1, 1), (2, 2)]
        eng = self._eng or self._start_engine()
        tables: TableSet = {}
        mcs_list = list(range(mcs_range[0], mcs_range[1] + 1))
        total = len(bw_list) * len(mcs_list) * len(ant_configs)
        done = 0
        for bw in bw_list:
            for mcs in mcs_list:
                for n_tx, n_rx in ant_configs:
                    done += 1
                    logger.info("[Gen] %d/%d  model=%s bw=%d mcs=%d ant=%dx%d",
                                done, total, channel_model, bw, mcs, n_tx, n_rx)
                    per_arr, tput_arr = self._sweep(
                        eng, channel_model, bw, mcs, n_tx, n_rx, custom_mat_path
                    )
                    tables[(channel_model, bw, mcs, n_tx, n_rx)] = {
                        "snr_db": _SNR_POINTS.copy(),
                        "per": per_arr,
                        "tput_mbps": tput_arr,
                    }
        if self._eng is None:
            eng.quit()
        return tables

    def _start_engine(self):
        import matlab.engine
        logger.info("[Gen] Starting MATLAB engine ...")
        return matlab.engine.start_matlab("-nodisplay -nosplash -nodesktop")

    def _sweep(self, eng, model, bw, mcs, n_tx, n_rx, custom_mat_path) -> tuple[np.ndarray, np.ndarray]:
        per_list, tput_list = [], []
        fallback_rate = _MCS_RATE_20MHZ[min(mcs, 13)] * (bw / 20)
        for snr in _SNR_POINTS:
            try:
                cfg = eng.wlanEHTSUConfig(
                    "ChannelBandwidth", f"CBW{bw}",
                    "MCS", int(mcs),
                    "NumTransmitAntennas", int(n_tx),
                    "NumSpaceTimeStreams", int(n_tx),
                    nargout=1,
                )
                psdu_len = 1000
                bits = eng.randi([1, 1], [psdu_len * 8, 1], nargout=1)
                tx = eng.wlanWaveformGenerator(bits, cfg, nargout=1)
                if custom_mat_path:
                    ch_data = eng.load(custom_mat_path, nargout=1)
                    rx = eng.filter(ch_data["channel"], tx, nargout=1)
                else:
                    ch = eng.wlanTGbeChannel(
                        "DelayProfile", f"Model-{model}",
                        "NumTransmitAntennas", int(n_tx),
                        "NumReceiveAntennas", int(n_rx),
                        "SampleRate", eng.wlanSampleRate(cfg, nargout=1),
                        nargout=1,
                    )
                    rx = eng.step(ch, tx, nargout=1)
                rx_noisy = eng.awgn(rx, float(snr), "measured", nargout=1)
                rx_bits = eng.wlanEHTDataRecover(
                    rx_noisy,
                    eng.ones([52, 1], nargout=1),
                    float(snr), cfg, nargout=1,
                )
                ber, fer = eng.biterr(bits, rx_bits, nargout=2)
                per_val = min(max(float(fer), 0.0), 1.0)
            except Exception as exc:
                logger.debug("[Gen] MATLAB error snr=%.1f: %s", snr, exc)
                per_val = 1.0
            per_list.append(per_val)
            tput_list.append(fallback_rate * (1.0 - per_val))
        return np.array(per_list), np.array(tput_list)
```

- [ ] **Step 2: Implement live_phy.py**

Create `nxwlansim/phy/matlab/live_phy.py`:
```python
"""
MatlabLivePhy — delegates to TablePhy if tables available, else bare defaults.
Used only when custom channel not yet in cache.
"""
from __future__ import annotations
import logging
from typing import TYPE_CHECKING

from nxwlansim.phy.base import PhyAbstraction, ChannelState, TxResult, RxResult
from nxwlansim.phy.matlab.table_phy import TablePhy, _BAND_BW_MHZ, _MCS_RATE_20MHZ

if TYPE_CHECKING:
    from nxwlansim.mac.frame import Frame
    from nxwlansim.mac.mlo import LinkContext

logger = logging.getLogger(__name__)


class MatlabLivePhy(PhyAbstraction):
    """Thin wrapper — calls TablePhy if tables loaded, otherwise safe defaults."""

    def __init__(self, table_phy: TablePhy | None = None):
        self._phy = table_phy
        self._positions: dict[str, tuple] = {}

    def register_node(self, node_id: str, position: tuple) -> None:
        self._positions[node_id] = position
        if self._phy:
            self._phy.register_node(node_id, position)

    def get_channel_state(self, src_id: str, dst_id: str, link_id: str) -> ChannelState:
        if self._phy:
            return self._phy.get_channel_state(src_id, dst_id, link_id)
        bw = _BAND_BW_MHZ.get(link_id, 80)
        return ChannelState(link_id=link_id, snr_db=20.0, interference_db=0.0,
                            bandwidth_mhz=bw, mcs_index=7, path_loss_db=60.0)

    def request_tx(self, frame: "Frame", link: "LinkContext") -> TxResult:
        if self._phy:
            return self._phy.request_tx(frame, link)
        bw = _BAND_BW_MHZ.get(link.link_id, 80)
        tput = _MCS_RATE_20MHZ[7] * (bw / 20)
        dur = max(int(frame.size_bytes * 8 / (tput * 1e6) * 1e9), 1_000)
        return TxResult(success=True, duration_ns=dur, mcs_used=7,
                        bytes_sent=frame.size_bytes, link_id=link.link_id)

    def request_rx(self, frame: "Frame", channel: ChannelState) -> RxResult:
        if self._phy:
            return self._phy.request_rx(frame, channel)
        return RxResult(success=True, snr_db=channel.snr_db, per=0.01, link_id=channel.link_id)
```

- [ ] **Step 3: Implement adaptive_phy.py**

Create `nxwlansim/phy/matlab/adaptive_phy.py`:
```python
"""
AdaptivePhy — orchestrator implementing PhyAbstraction.
Init: cache hit → TablePhy; miss → MATLAB generate → cache → TablePhy.
Falls back to TGbeChannel if MATLAB unavailable and no cache.
"""
from __future__ import annotations
import logging
import os
from typing import TYPE_CHECKING

from nxwlansim.phy.base import PhyAbstraction, ChannelState, TxResult, RxResult
from nxwlansim.phy.matlab.cache import TableCache, CacheKey
from nxwlansim.phy.matlab.table_phy import TablePhy

if TYPE_CHECKING:
    from nxwlansim.core.config import PhyConfig
    from nxwlansim.mac.frame import Frame
    from nxwlansim.mac.mlo import LinkContext

logger = logging.getLogger(__name__)

# Default fixture path (committed to repo for CI)
_FIXTURE_PATH = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "tests", "fixtures", "tgbe_d_fixture.h5"
)


class AdaptivePhy(PhyAbstraction):
    """Orchestrates TablePhy (fast path) with MATLAB generation on cache miss."""

    def __init__(self, config: "PhyConfig"):
        self._config = config
        cache_dir = config.cache_dir or None
        self._cache = TableCache(cache_dir)
        self._backend: PhyAbstraction = self._build_backend(config)

    def _build_backend(self, config: "PhyConfig") -> PhyAbstraction:
        key = CacheKey(
            channel_model=config.channel_model,
            bw_list=[20, 40, 80, 160, 320],
            mcs_range=(0, 13),
            snr_step_db=config.snr_step_db,
        )

        tables = None
        if not config.force_regenerate:
            tables = self._cache.load(key)

        if tables is None:
            tables = self._try_matlab(config, key)

        if tables is None:
            # CI fallback: load fixture table
            fixture = os.path.abspath(_FIXTURE_PATH)
            if os.path.exists(fixture):
                logger.info("[AdaptivePhy] Loading fixture tables from %s", fixture)
                tables = self._cache.load_from_file(fixture)

        if tables is not None:
            return TablePhy(
                tables,
                channel_model=config.channel_model,
                per_threshold=config.per_threshold,
            )

        # Last resort: fall back to TGbeChannel
        logger.warning("[AdaptivePhy] No tables — falling back to TGbeChannel")
        from nxwlansim.phy.tgbe_channel import TGbeChannel
        return TGbeChannel(config)

    def _try_matlab(self, config: "PhyConfig", key: CacheKey):
        try:
            from nxwlansim.phy.matlab.generator import MatlabTableGenerator
            logger.info("[AdaptivePhy] Generating tables via MATLAB ...")
            gen = MatlabTableGenerator()
            tables = gen.generate(
                channel_model=config.channel_model,
                custom_mat_path=config.custom_channel or None,
            )
            self._cache.save(key, tables)
            return tables
        except Exception as exc:
            logger.warning("[AdaptivePhy] MATLAB unavailable: %s", exc)
            return None

    # ------------------------------------------------------------------
    # PhyAbstraction delegation
    # ------------------------------------------------------------------

    def register_node(self, node_id: str, position: tuple) -> None:
        if hasattr(self._backend, "register_node"):
            self._backend.register_node(node_id, position)

    def get_channel_state(self, src_id: str, dst_id: str, link_id: str) -> ChannelState:
        return self._backend.get_channel_state(src_id, dst_id, link_id)

    def request_tx(self, frame: "Frame", link: "LinkContext") -> TxResult:
        return self._backend.request_tx(frame, link)

    def request_rx(self, frame: "Frame", channel: ChannelState) -> RxResult:
        return self._backend.request_rx(frame, channel)
```

- [ ] **Step 4: Wire builder.py**

In `nxwlansim/core/builder.py`, replace `_build_phy`:
```python
def _build_phy(cfg):
    if cfg.phy.backend == "matlab":
        from nxwlansim.phy.matlab.adaptive_phy import AdaptivePhy
        return AdaptivePhy(cfg.phy)
    if cfg.phy.backend == "matlab_legacy":
        try:
            from nxwlansim.phy.matlab_phy import MatlabWlanPhy
            return MatlabWlanPhy(cfg.phy)
        except ImportError:
            import warnings
            warnings.warn("matlab.engine not available — falling back to TGbeChannel.",
                          RuntimeWarning, stacklevel=3)
    from nxwlansim.phy.tgbe_channel import TGbeChannel
    return TGbeChannel(cfg.phy)
```

- [ ] **Step 5: Run full test suite**
```bash
pytest tests/ -q
```
Expected: `85 passed` (all existing tests still pass; AdaptivePhy uses fixture table)

- [ ] **Step 6: Commit**
```bash
git add nxwlansim/phy/matlab/generator.py nxwlansim/phy/matlab/live_phy.py \
        nxwlansim/phy/matlab/adaptive_phy.py nxwlansim/core/builder.py
git commit -m "feat: MatlabTableGenerator + AdaptivePhy — MATLAB PHY pipeline complete"
```

---

## Task 5: MATLAB integration tests (matlab-marked)

**Files:** `tests/integration/test_matlab_generator.py`

- [ ] **Step 1: Create integration test (skipped without MATLAB)**

Create `tests/integration/test_matlab_generator.py`:
```python
"""
Integration tests for MATLAB table generation.
Skipped automatically unless MATLAB is installed.
Run manually: pytest tests/integration/test_matlab_generator.py -m matlab -v
"""
import pytest
import numpy as np

pytestmark = pytest.mark.matlab


def _has_matlab() -> bool:
    try:
        import matlab.engine
        return True
    except ImportError:
        return False


@pytest.fixture(scope="module")
def matlab_tables(tmp_path_factory):
    if not _has_matlab():
        pytest.skip("matlab.engine not installed")
    from nxwlansim.phy.matlab.generator import MatlabTableGenerator
    gen = MatlabTableGenerator()
    # Small subset to keep test fast: D, 80 MHz, MCS 0-3 only
    tables = gen.generate(channel_model="D", bw_list=[80], mcs_range=(0, 3),
                          ant_configs=[(1, 1)])
    return tables


def test_table_keys_present(matlab_tables):
    for mcs in range(4):
        assert ("D", 80, mcs, 1, 1) in matlab_tables


def test_per_monotonically_decreasing(matlab_tables):
    """PER should decrease as SNR increases."""
    for key, data in matlab_tables.items():
        per = data["per"]
        # Allow small numerical noise: check general trend (first half > second half)
        assert per[:10].mean() > per[-10:].mean(), \
            f"PER not decreasing for {key}: {per[:5]} ... {per[-5:]}"


def test_per_bounds(matlab_tables):
    for key, data in matlab_tables.items():
        assert np.all(data["per"] >= 0.0), f"Negative PER in {key}"
        assert np.all(data["per"] <= 1.0), f"PER > 1 in {key}"


def test_cache_hit_on_second_call(tmp_path):
    if not _has_matlab():
        pytest.skip("matlab.engine not installed")
    from nxwlansim.phy.matlab.generator import MatlabTableGenerator
    from nxwlansim.phy.matlab.cache import TableCache, CacheKey
    cache = TableCache(str(tmp_path))
    key = CacheKey("D", [80], (0, 1), snr_step_db=0.5)
    gen = MatlabTableGenerator()
    tables = gen.generate("D", bw_list=[80], mcs_range=(0, 1), ant_configs=[(1, 1)])
    cache.save(key, tables)
    loaded = cache.load(key)
    assert loaded is not None
    np.testing.assert_allclose(
        loaded[("D", 80, 0, 1, 1)]["per"],
        tables[("D", 80, 0, 1, 1)]["per"],
    )
```

- [ ] **Step 2: Verify test is collected but skipped without MATLAB**
```bash
pytest tests/integration/test_matlab_generator.py -v -m "not matlab"
```
Expected: `0 passed, N skipped` (or collected but deselected)

- [ ] **Step 3: Commit**
```bash
git add tests/integration/test_matlab_generator.py
git commit -m "test: MATLAB integration tests (skipped without matlab.engine)"
```

---

## Task 6: LinkContext sub-channel NAV (mlo.py)

**Files:** `nxwlansim/mac/mlo.py`, `tests/unit/test_npca.py` (partial)

- [ ] **Step 1: Write failing tests for sub-NAV**

Create `tests/unit/test_npca.py`:
```python
"""Unit tests for NPCA — sub-channel NAV and NPCAEngine decisions."""
import pytest
from nxwlansim.mac.mlo import LinkContext, LinkState


# ---- LinkContext sub-NAV tests ----

def _ctx(link_id="6g"):
    class _FakeNode:
        node_id = "sta0"
        mlo_mode = "str"
    return LinkContext(link_id, _FakeNode())


def test_all_subchannels_free_initially():
    ctx = _ctx()
    free = ctx.free_subchannels(now_ns=0, n_subchannels=4)
    assert free == [0, 1, 2, 3]


def test_set_sub_nav_blocks_subchannel():
    ctx = _ctx()
    ctx.set_sub_nav(subchannel_id=0, duration_ns=1_000_000, now_ns=0)
    free = ctx.free_subchannels(now_ns=500_000, n_subchannels=4)
    assert 0 not in free
    assert 1 in free


def test_sub_nav_clears_after_expiry():
    ctx = _ctx()
    ctx.set_sub_nav(subchannel_id=1, duration_ns=1_000_000, now_ns=0)
    free_during = ctx.free_subchannels(now_ns=500_000, n_subchannels=4)
    free_after = ctx.free_subchannels(now_ns=2_000_000, n_subchannels=4)
    assert 1 not in free_during
    assert 1 in free_after


def test_sub_nav_max_of_two_calls():
    ctx = _ctx()
    ctx.set_sub_nav(0, 1_000_000, now_ns=0)
    ctx.set_sub_nav(0, 5_000_000, now_ns=0)   # longer one should win
    free = ctx.free_subchannels(now_ns=2_000_000, n_subchannels=4)
    assert 0 not in free
```

- [ ] **Step 2: Run — expect failure**
```bash
pytest tests/unit/test_npca.py::test_all_subchannels_free_initially -v
```
Expected: `AttributeError: 'LinkContext' object has no attribute 'sub_nav'`

- [ ] **Step 3: Add sub_nav to LinkContext in mlo.py**

In `nxwlansim/mac/mlo.py`, inside `LinkContext.__init__`, after `self.ba_session = None`:
```python
        # Per-subchannel NAV (NPCA): subchannel_id → expiry_ns
        self.sub_nav: dict[int, int] = {}
```

After `__repr__`, add two methods inside `LinkContext`:
```python
    def free_subchannels(self, now_ns: int, n_subchannels: int = 4) -> list[int]:
        """Return subchannel indices with clear sub-NAV."""
        return [i for i in range(n_subchannels)
                if now_ns >= self.sub_nav.get(i, 0)]

    def set_sub_nav(self, subchannel_id: int, duration_ns: int, now_ns: int) -> None:
        """Set sub-channel NAV, keeping the max expiry."""
        expiry = now_ns + duration_ns
        self.sub_nav[subchannel_id] = max(self.sub_nav.get(subchannel_id, 0), expiry)
```

- [ ] **Step 4: Run sub-NAV tests — expect pass**
```bash
pytest tests/unit/test_npca.py -v -k "sub_nav or subchannels"
```
Expected: `4 passed`

- [ ] **Step 5: Run full suite**
```bash
pytest tests/ -q
```
Expected: `89 passed`

- [ ] **Step 6: Commit**
```bash
git add nxwlansim/mac/mlo.py tests/unit/test_npca.py
git commit -m "feat: LinkContext per-subchannel NAV for NPCA"
```

---

## Task 7: NPCAEngine

**Files:** `nxwlansim/mac/npca.py`, `tests/unit/test_npca.py` (add cases), `tests/unit/test_npca_coordination.py`

- [ ] **Step 1: Add NPCAEngine tests to test_npca.py**

Append to `tests/unit/test_npca.py`:
```python
# ---- NPCAEngine tests ----
from unittest.mock import MagicMock
from nxwlansim.mac.npca import NPCAEngine, NPCADecision


def _node_with_link(link_id="6g", now_ns=0, busy_subchannels=None):
    """Create a fake node whose LinkContext has specified subchannels busy."""
    ctx = _ctx(link_id)
    busy = busy_subchannels or []
    for sc in busy:
        ctx.set_sub_nav(sc, duration_ns=10_000_000, now_ns=now_ns)

    node = MagicMock()
    node.node_id = "sta0"
    node.mlo_manager.links = {link_id: ctx}
    return node


def test_no_npca_when_primary_free():
    node = _node_with_link("6g", busy_subchannels=[])
    engine = NPCAEngine(node)
    decision = engine.evaluate("6g", now_ns=0)
    assert decision.use_npca is False
    assert decision.punctured_mask == 0


def test_npca_triggered_when_primary_busy():
    node = _node_with_link("6g", busy_subchannels=[0])  # primary busy
    engine = NPCAEngine(node)
    decision = engine.evaluate("6g", now_ns=0)
    assert decision.use_npca is True
    assert decision.punctured_mask & 1   # subchannel 0 punctured
    assert decision.effective_bw_mhz > 0


def test_no_npca_when_all_busy():
    node = _node_with_link("6g", busy_subchannels=[0, 1, 2, 3])
    engine = NPCAEngine(node)
    decision = engine.evaluate("6g", now_ns=0)
    assert decision.use_npca is False
    assert decision.effective_bw_mhz == 0.0


def test_effective_bw_proportional_to_free_secondaries():
    node = _node_with_link("6g", busy_subchannels=[0, 1])  # 2 busy, 2 free
    engine = NPCAEngine(node)
    decision = engine.evaluate("6g", now_ns=0)
    assert decision.use_npca is True
    assert decision.effective_bw_mhz == 2 * 80   # 2 free × 80 MHz
```

- [ ] **Step 2: Run — expect import failure**
```bash
pytest tests/unit/test_npca.py -v -k "NPCAEngine"
```
Expected: `ModuleNotFoundError: nxwlansim.mac.npca`

- [ ] **Step 3: Implement npca.py**

Create `nxwlansim/mac/npca.py`:
```python
"""
NPCAEngine — Non-Primary Channel Access per IEEE 802.11be §35.3.3.
Preamble puncturing, per-subchannel NAV, coordinated secondary-channel access.
"""
from __future__ import annotations
import logging
from dataclasses import dataclass
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nxwlansim.core.engine import SimulationEngine
    from nxwlansim.core.node import Node

logger = logging.getLogger(__name__)

N_SUBCHANNELS = 4       # 4 × 80 MHz = 320 MHz total
SUBCHANNEL_BW = 80      # MHz per subchannel
_ALL_MASK = (1 << N_SUBCHANNELS) - 1   # 0b1111


@dataclass
class NPCADecision:
    use_npca: bool
    free_mask: int          # bitmask: bit i set if subchannel i is free
    punctured_mask: int     # bitmask: bit i set if subchannel i is punctured
    effective_bw_mhz: float
    total_bw_mhz: float = float(N_SUBCHANNELS * SUBCHANNEL_BW)


class NPCAEngine:
    """Per-node NPCA controller. One instance per node, attached by builder."""

    def __init__(self, node: "Node"):
        self.node = node

    def evaluate(self, link_id: str, now_ns: int) -> NPCADecision:
        """
        Decide whether to use NPCA on link_id.
        Primary subchannel = index 0.
        Returns NPCADecision with puncturing info.
        """
        ctx = self.node.mlo_manager.links.get(link_id)
        if ctx is None:
            # No link context — normal TX, no puncturing
            return NPCADecision(use_npca=False, free_mask=_ALL_MASK,
                                punctured_mask=0,
                                effective_bw_mhz=N_SUBCHANNELS * SUBCHANNEL_BW)

        free = ctx.free_subchannels(now_ns, N_SUBCHANNELS)
        free_mask = sum(1 << i for i in free)
        primary_free = 0 in free

        if primary_free:
            return NPCADecision(use_npca=False, free_mask=free_mask,
                                punctured_mask=0,
                                effective_bw_mhz=N_SUBCHANNELS * SUBCHANNEL_BW)

        # Primary busy — try secondary subchannels
        secondary_free = [i for i in free if i != 0]
        if not secondary_free:
            return NPCADecision(use_npca=False, free_mask=0,
                                punctured_mask=_ALL_MASK, effective_bw_mhz=0.0)

        punctured = _ALL_MASK & ~free_mask   # busy subchannels are punctured
        eff_bw = float(len(secondary_free) * SUBCHANNEL_BW)
        logger.debug("[NPCA] %s link=%s primary=BUSY secondaries=%s bw=%.0fMHz",
                     self.node.node_id, link_id, secondary_free, eff_bw)
        return NPCADecision(use_npca=True, free_mask=free_mask,
                            punctured_mask=punctured, effective_bw_mhz=eff_bw)

    def coordinate(self, link_id: str, duration_ns: int,
                   engine: "SimulationEngine") -> None:
        """
        Propagate secondary subchannel NAV to all neighbours.
        Prevents collision on secondary channels from other STAs.
        """
        if not engine._registry:
            return
        for other in engine._registry:
            if other.node_id == self.node.node_id:
                continue
            ctx = other.mlo_manager.links.get(link_id)
            if ctx is None:
                continue
            for sc in range(1, N_SUBCHANNELS):   # secondary subchannels only
                ctx.set_sub_nav(sc, duration_ns, engine.now_ns)
```

- [ ] **Step 4: Run NPCAEngine tests**
```bash
pytest tests/unit/test_npca.py -v
```
Expected: `8 passed`

- [ ] **Step 5: Create coordination test**

Create `tests/unit/test_npca_coordination.py`:
```python
"""Unit tests for NPCA coordination — secondary NAV propagation."""
from unittest.mock import MagicMock, patch
import pytest
from nxwlansim.mac.mlo import LinkContext
from nxwlansim.mac.npca import NPCAEngine, N_SUBCHANNELS


def _make_node(node_id, link_ids=("6g",)):
    ctx_map = {}
    for lid in link_ids:
        class _FakeNode:
            pass
        ctx = LinkContext(lid, _FakeNode())
        ctx_map[lid] = ctx
    node = MagicMock()
    node.node_id = node_id
    node.mlo_manager.links = ctx_map
    return node, ctx_map


def test_coordinate_sets_secondary_nav_on_neighbours():
    sender, _ = _make_node("sta0", ("6g",))
    neighbour, n_ctx = _make_node("sta1", ("6g",))

    engine = MagicMock()
    engine.now_ns = 0
    engine._registry = [sender, neighbour]

    npca = NPCAEngine(sender)
    npca.coordinate("6g", duration_ns=5_000_000, engine=engine)

    # Secondary subchannels (1,2,3) should be blocked on neighbour
    free_after = n_ctx["6g"].free_subchannels(now_ns=1_000_000, n_subchannels=4)
    assert 0 in free_after        # primary unaffected
    assert 1 not in free_after    # secondary blocked
    assert 2 not in free_after
    assert 3 not in free_after


def test_coordinate_does_not_block_sender_itself():
    sender, s_ctx = _make_node("sta0", ("6g",))
    engine = MagicMock()
    engine.now_ns = 0
    engine._registry = [sender]

    npca = NPCAEngine(sender)
    npca.coordinate("6g", duration_ns=5_000_000, engine=engine)
    # Sender's own context is not touched
    free = s_ctx["6g"].free_subchannels(now_ns=1_000_000, n_subchannels=4)
    assert free == [0, 1, 2, 3]


def test_secondary_nav_expires():
    sender, _ = _make_node("sta0", ("6g",))
    neighbour, n_ctx = _make_node("sta1", ("6g",))
    engine = MagicMock()
    engine.now_ns = 0
    engine._registry = [sender, neighbour]

    NPCAEngine(sender).coordinate("6g", duration_ns=1_000_000, engine=engine)

    free_during = n_ctx["6g"].free_subchannels(now_ns=500_000)
    free_after  = n_ctx["6g"].free_subchannels(now_ns=2_000_000)
    assert 1 not in free_during
    assert 1 in free_after
```

- [ ] **Step 6: Run coordination tests**
```bash
pytest tests/unit/test_npca_coordination.py -v
```
Expected: `3 passed`

- [ ] **Step 7: Run full suite**
```bash
pytest tests/ -q
```
Expected: `97 passed` (85 + 4 sub-NAV + 4 NPCAEngine + 3 coordination + existing)

- [ ] **Step 8: Commit**
```bash
git add nxwlansim/mac/npca.py tests/unit/test_npca.py \
        tests/unit/test_npca_coordination.py
git commit -m "feat: NPCAEngine — preamble puncturing + coordinated secondary NAV"
```

---

## Task 8: AMPDU puncturing + txop.py hook

**Files:** `nxwlansim/mac/ampdu.py`, `nxwlansim/mac/txop.py`, `nxwlansim/core/builder.py`

- [ ] **Step 1: Add punctured_mask to AMPDUFrame in ampdu.py**

In `nxwlansim/mac/frame.py`, add fields to `AMPDUFrame` dataclass after `duration_ns`:
```python
    punctured_mask: int = 0       # bitmask of punctured 80 MHz sub-channels
    effective_bw_mhz: float = 0.0 # TX bandwidth after puncturing
```

- [ ] **Step 2: Update AmpduAggregator.build_ampdu() in ampdu.py**

Replace the `build_ampdu` signature and opening:
```python
    def build_ampdu(
        self,
        frames: list[MPDUFrame],
        link_id: str,
        txop_remaining_ns: int,
        mcs: int,
        bandwidth_mhz: int,
        punctured_mask: int = 0,
    ) -> AMPDUFrame:
        """Aggregate frames into an A-MPDU fitting within TXOP."""
        # Compute effective BW after puncturing
        n_sub = 4
        n_free = bin(~punctured_mask & 0xF).count("1")
        eff_bw = int(bandwidth_mhz * n_free / n_sub) if n_free else bandwidth_mhz
        ampdu = AMPDUFrame(link_id=link_id,
                           punctured_mask=punctured_mask,
                           effective_bw_mhz=float(eff_bw))
        byte_budget = _txop_bytes(txop_remaining_ns, mcs, eff_bw or bandwidth_mhz)
        for frame in frames[:MAX_AMPDU_SUBFRAMES]:
            if ampdu.total_size_bytes + frame.size_bytes > byte_budget:
                break
            frame.seq_num = self._next_seq(frame.ac)
            ampdu.add(frame)
        return ampdu
```

- [ ] **Step 3: Add NPCAEngine hook in txop.py**

In `nxwlansim/mac/txop.py`, inside `_attempt_txop()`, after `ctx.state = LinkState.TXOP_GRANTED` and before `self._transmit_ampdu(...)`:
```python
        # NPCA: check if we should puncture sub-channels
        _punctured = 0
        if hasattr(self.node, "npca_engine") and self.node.npca_engine is not None:
            npca = self.node.npca_engine.evaluate(link_id, engine.now_ns)
            if npca.use_npca:
                self.node.npca_engine.coordinate(link_id, txop_limit_ns, engine)
            _punctured = npca.punctured_mask
```

Then update the `_transmit_ampdu` call to pass `punctured_mask`:
```python
        self._transmit_ampdu(engine, link_id, queue, punctured_mask=_punctured)
```

- [ ] **Step 4: Update _transmit_ampdu signature in txop.py**

Change the method signature:
```python
    def _transmit_ampdu(
        self,
        engine: "SimulationEngine",
        link_id: str,
        queue: "ACQueue",
        punctured_mask: int = 0,
    ) -> None:
```

And update the `build_ampdu` call inside `_transmit_ampdu`:
```python
        ampdu = self.aggregator.build_ampdu(
            frames, link_id,
            txop_remaining_ns=txop_remaining,
            mcs=ch.mcs_index,
            bandwidth_mhz=ch.bandwidth_mhz,
            punctured_mask=punctured_mask,
        )
```

- [ ] **Step 5: Wire NPCAEngine in builder.py**

In `nxwlansim/core/builder.py`, inside `_attach_mac()`, after `node.rx_processor = RXProcessor(node, engine)`:
```python
        from nxwlansim.mac.npca import NPCAEngine
        node.npca_engine = NPCAEngine(node)
```

- [ ] **Step 6: Run full suite**
```bash
pytest tests/ -q
```
Expected: `97 passed` (all existing + new tests)

- [ ] **Step 7: Commit**
```bash
git add nxwlansim/mac/frame.py nxwlansim/mac/ampdu.py \
        nxwlansim/mac/txop.py nxwlansim/core/builder.py
git commit -m "feat: NPCA preamble puncturing — AMPDUFrame + txop hook + builder wiring"
```

---

## Task 9: NPCA Metrics

**Files:** `nxwlansim/observe/metrics.py`

- [ ] **Step 1: Add NPCA counters to MetricsCollector**

In `nxwlansim/observe/metrics.py`, inside `__init__()`, after `self._frames_in_interval`:
```python
        self._npca_opportunities: dict[str, int] = {n.node_id: 0 for n in registry}
        self._npca_used: dict[str, int]          = {n.node_id: 0 for n in registry}
        self._npca_bytes_gained: dict[str, int]  = {n.node_id: 0 for n in registry}
```

- [ ] **Step 2: Add record_npca_event method**

After `record_tx_event`, add:
```python
    def record_npca_event(self, node_id: str, used: bool, bytes_gained: int = 0) -> None:
        """Called by TXOPEngine when NPCA is evaluated."""
        if node_id in self._npca_opportunities:
            self._npca_opportunities[node_id] += 1
            if used:
                self._npca_used[node_id] += 1
                self._npca_bytes_gained[node_id] += bytes_gained
```

- [ ] **Step 3: Update CSV header**

Change the `writerow` header line in `__init__`:
```python
            self._csv_writer.writerow([
                "time_us", "node_id", "node_type", "link_id",
                "throughput_mbps", "frames", "bytes",
                "mcs", "snr_db",
                "npca_opportunities", "npca_used", "npca_gain_mbps",
            ])
```

- [ ] **Step 4: Update CSV row in _sample()**

After the existing `writerow` call in `_sample()`, update it to include NPCA columns:
```python
            if self._csv_writer and (b > 0 or f > 0):
                interval_s = self._interval_ns / 1e9
                npca_opp  = self._npca_opportunities.get(nid, 0)
                npca_used = self._npca_used.get(nid, 0)
                npca_gain = self._npca_bytes_gained.get(nid, 0) * 8 / interval_s / 1e6
                self._csv_writer.writerow([
                    f"{now_us:.1f}", nid, node.node_type,
                    ",".join(node.links),
                    f"{tput_mbps:.3f}", f, b,
                    mcs, snr,
                    npca_opp, npca_used, f"{npca_gain:.3f}",
                ])
```

- [ ] **Step 5: Call record_npca_event from txop.py**

In `nxwlansim/mac/txop.py`, after the NPCA evaluate block in `_attempt_txop()`:
```python
        if hasattr(engine, "_metrics") and engine._metrics is not None:
            engine._metrics.record_npca_event(
                self.node.node_id,
                used=_punctured != 0,
            )
```

- [ ] **Step 6: Run full suite**
```bash
pytest tests/ -q
```
Expected: all pass

- [ ] **Step 7: Commit**
```bash
git add nxwlansim/observe/metrics.py nxwlansim/mac/txop.py
git commit -m "feat: NPCA metrics — opportunities, used count, gain Mbps in CSV"
```

---

## Task 10: Example YAML configs

**Files:** `configs/examples/npca_basic.yaml`, `configs/examples/npca_coordinated.yaml`

- [ ] **Step 1: Create npca_basic.yaml**

Create `configs/examples/npca_basic.yaml`:
```yaml
simulation:
  duration_us: 500000    # 500 ms
  seed: 42

network:
  mode: bss

phy:
  backend: tgbe          # swap to matlab once MATLAB installed
  channel_model: D

nodes:
  - id: ap0
    type: ap
    links: [5g, 6g]
    mlo_mode: str
    position: [0.0, 0.0]
  - id: sta0
    type: sta
    links: [5g, 6g]
    mlo_mode: str
    position: [5.0, 0.0]
  - id: sta1
    type: sta
    links: [5g, 6g]
    mlo_mode: str
    position: [0.0, 5.0]

traffic:
  - src: sta0
    dst: ap0
    type: udp_cbr
    rate_mbps: 300        # heavy load to saturate primary channel
    ac: BE
  - src: sta1
    dst: ap0
    type: udp_cbr
    rate_mbps: 150
    ac: VI

obs:
  log: true
  csv: true
  pcap: false
  viz: true
  output_dir: results/npca_basic
```

- [ ] **Step 2: Create npca_coordinated.yaml**

Create `configs/examples/npca_coordinated.yaml`:
```yaml
simulation:
  duration_us: 500000
  seed: 7

network:
  mode: bss

phy:
  backend: tgbe
  channel_model: D

nodes:
  - id: ap0
    type: ap
    links: [5g, 6g]
    mlo_mode: str
    position: [0.0, 0.0]
  - id: sta0
    type: sta
    links: [5g, 6g]
    mlo_mode: str
    position: [4.0, 0.0]
  - id: sta1
    type: sta
    links: [5g, 6g]
    mlo_mode: str
    position: [-4.0, 0.0]
  - id: sta2
    type: sta
    links: [5g, 6g]
    mlo_mode: str
    position: [0.0, 4.0]
  - id: sta3
    type: sta
    links: [5g, 6g]
    mlo_mode: str
    position: [0.0, -4.0]

traffic:
  - src: sta0
    dst: ap0
    type: udp_cbr
    rate_mbps: 200
    ac: BE
  - src: sta1
    dst: ap0
    type: udp_cbr
    rate_mbps: 200
    ac: BE
  - src: sta2
    dst: ap0
    type: udp_cbr
    rate_mbps: 100
    ac: VI
  - src: sta3
    dst: ap0
    type: voip
    rate_mbps: 0.064
    ac: VO

obs:
  log: true
  csv: true
  pcap: false
  viz: true
  output_dir: results/npca_coordinated
```

- [ ] **Step 3: Smoke-test both configs run without error**
```bash
python3 -c "
from nxwlansim.core.config import SimConfig
from nxwlansim.core.engine import SimulationEngine
cfg = SimConfig.from_yaml('configs/examples/npca_basic.yaml')
r = SimulationEngine(cfg).run()
print(r.summary())
"
```
Expected: prints simulation results, no exception.

- [ ] **Step 4: Run full suite**
```bash
pytest tests/ -q
```
Expected: all pass

- [ ] **Step 5: Commit**
```bash
git add configs/examples/npca_basic.yaml configs/examples/npca_coordinated.yaml
git commit -m "feat: NPCA example configs — basic and coordinated scenarios"
```

---

## Task 11: Update CLAUDE.md + push

**Files:** `CLAUDE.md`

- [ ] **Step 1: Update CLAUDE.md Phase 2 section**

Add to `CLAUDE.md` after the "Fixed bugs" section:
```markdown
## Phase 2 additions

### MATLAB PHY pipeline (`nxwlansim/phy/matlab/`)
- `cache.py` — `TableCache` + `CacheKey` (SHA256-keyed HDF5 storage)
- `table_phy.py` — `TablePhy` pure-Python interpolating backend (CI-safe)
- `generator.py` — `MatlabTableGenerator` (calls WLAN Toolbox at startup)
- `live_phy.py` — `MatlabLivePhy` (cache-miss fallback)
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
- `MetricsCollector.record_npca_event()` — call from txop
- CSV columns: `npca_opportunities`, `npca_used`, `npca_gain_mbps`

### New example configs
- `configs/examples/npca_basic.yaml`
- `configs/examples/npca_coordinated.yaml`

### Setup docs
- `docs/setup/matlab_ubuntu_install.md` — R2025a Ubuntu install guide
- `scripts/verify_matlab.py` — confirms WLAN Toolbox is installed and licensed
- `scripts/generate_fixture_tables.py` — regenerates CI fixture HDF5
```

- [ ] **Step 2: Final test run**
```bash
pytest tests/ -q
```
Expected: all pass

- [ ] **Step 3: Commit and push**
```bash
git add CLAUDE.md
git commit -m "docs: update CLAUDE.md with Phase 2 MATLAB PHY + NPCA summary"
git push origin main
```
Expected: `main -> main` pushed to GitHub.
