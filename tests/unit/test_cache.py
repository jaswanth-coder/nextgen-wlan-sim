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
    assert tmp_cache.load(key_b) is None


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
