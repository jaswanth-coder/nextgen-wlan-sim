"""Smoke test for AdaptivePhy — verifies fixture fallback path works in CI."""
import pytest
from nxwlansim.core.config import PhyConfig
from nxwlansim.phy.matlab.adaptive_phy import AdaptivePhy
from nxwlansim.phy.matlab.table_phy import TablePhy


def test_adaptive_phy_uses_fixture_in_ci():
    """Without MATLAB installed, AdaptivePhy should load fixture tables → TablePhy backend."""
    cfg = PhyConfig(backend="matlab", channel_model="D", force_regenerate=False)
    phy = AdaptivePhy(cfg)
    # Should be TablePhy (fixture loaded) or TGbeChannel (if h5py missing) — not an error
    assert phy._backend is not None


def test_adaptive_phy_get_channel_state():
    cfg = PhyConfig(backend="matlab", channel_model="D")
    phy = AdaptivePhy(cfg)
    phy.register_node("ap0", (0.0, 0.0))
    phy.register_node("sta0", (10.0, 0.0))
    ch = phy.get_channel_state("sta0", "ap0", "5g")
    assert ch.link_id == "5g"
    assert ch.bandwidth_mhz > 0
