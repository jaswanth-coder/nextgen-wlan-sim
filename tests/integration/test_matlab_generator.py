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
