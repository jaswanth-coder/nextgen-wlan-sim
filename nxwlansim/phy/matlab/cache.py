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
        if not _H5PY:
            logger.warning("[Cache] h5py not available — cannot load fixture from %s", path)
            return {}
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
