"""
nxwlansim — Next-Generation WLAN Simulator
IEEE 802.11be (WiFi 7/8): MLO, NPCA, Multi-AP Coordination

Usage:
    import nxwlansim as nx
    sim = nx.Simulation.from_yaml("config.yaml")
    results = sim.run()
"""

__version__ = "0.1.0"
__author__ = "jaswanth-coder"

from nxwlansim.core.engine import SimulationEngine
from nxwlansim.core.config import SimConfig

class Simulation:
    """Top-level simulation object. Entry point for library usage."""

    def __init__(self, config: SimConfig):
        self.config = config
        self._engine = SimulationEngine(config)

    @classmethod
    def from_yaml(cls, path: str) -> "Simulation":
        from nxwlansim.core.config import SimConfig
        return cls(SimConfig.from_yaml(path))

    @classmethod
    def from_dict(cls, d: dict) -> "Simulation":
        from nxwlansim.core.config import SimConfig
        return cls(SimConfig.from_dict(d))

    def run(self):
        return self._engine.run()


def quick_scenario(
    mode: str = "str",
    n_links: int = 2,
    n_stas: int = 5,
    duration_us: int = 500_000,
    seed: int = 42,
) -> "Simulation":
    """Build a simple MLO scenario programmatically for notebooks/REPL."""
    from nxwlansim.core.config import SimConfig
    cfg = SimConfig.quick_build(
        mlo_mode=mode,
        n_links=n_links,
        n_stas=n_stas,
        duration_us=duration_us,
        seed=seed,
    )
    return Simulation(cfg)
