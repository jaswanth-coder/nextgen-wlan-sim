"""
SimConfig — loads and validates simulation configuration from YAML or dict.
"""

from __future__ import annotations

import yaml
from dataclasses import dataclass, field
from typing import Literal, Optional


@dataclass
class SimulationConfig:
    duration_us: int = 1_000_000
    seed: int = 42


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


@dataclass
class NetworkConfig:
    mode: Literal["bss", "ip", "multi_ap"] = "bss"


@dataclass
class ObsConfig:
    log: bool = True
    csv: bool = True
    pcap: bool = False
    viz: bool = False
    gym: bool = False
    output_dir: str = "results"


@dataclass
class NodeConfig:
    id: str = ""
    type: Literal["ap", "sta"] = "sta"
    links: list = field(default_factory=lambda: ["6g"])
    mlo_mode: Literal["str", "emlsr", "emlmr", "none"] = "str"
    emlsr_transition_delay_us: int = 64
    emlmr_n_radios: int = 2
    position: list = field(default_factory=lambda: [0.0, 0.0])


@dataclass
class TrafficConfig:
    src: str = ""
    dst: str = ""
    type: Literal["udp_cbr", "poisson", "voip", "video"] = "udp_cbr"
    rate_mbps: float = 50.0
    ac: Literal["BE", "BK", "VI", "VO"] = "BE"


@dataclass
class SimConfig:
    simulation: SimulationConfig = field(default_factory=SimulationConfig)
    phy: PhyConfig = field(default_factory=PhyConfig)
    network: NetworkConfig = field(default_factory=NetworkConfig)
    obs: ObsConfig = field(default_factory=ObsConfig)
    nodes: list[NodeConfig] = field(default_factory=list)
    traffic: list[TrafficConfig] = field(default_factory=list)

    @classmethod
    def from_yaml(cls, path: str) -> "SimConfig":
        with open(path) as f:
            raw = yaml.safe_load(f)
        return cls.from_dict(raw)

    @classmethod
    def from_dict(cls, d: dict) -> "SimConfig":
        cfg = cls()
        if "simulation" in d:
            cfg.simulation = SimulationConfig(**d["simulation"])
        if "phy" in d:
            cfg.phy = PhyConfig(**d["phy"])
        if "network" in d:
            cfg.network = NetworkConfig(**d["network"])
        if "obs" in d:
            cfg.obs = ObsConfig(**d["obs"])
        if "nodes" in d:
            cfg.nodes = [NodeConfig(**n) for n in d["nodes"]]
        if "traffic" in d:
            cfg.traffic = [TrafficConfig(**t) for t in d["traffic"]]
        return cfg

    @classmethod
    def quick_build(
        cls,
        mlo_mode: str = "str",
        n_links: int = 2,
        n_stas: int = 5,
        duration_us: int = 500_000,
        seed: int = 42,
    ) -> "SimConfig":
        """Build a minimal config for notebook/REPL quick-start."""
        import math
        links = ["5g", "6g"][:n_links] if n_links <= 2 else ["2g", "5g", "6g"][:n_links]
        nodes = [NodeConfig(id="ap0", type="ap", links=links, mlo_mode=mlo_mode, position=[0.0, 0.0])]
        radius = 10.0
        for i in range(n_stas):
            angle = 2 * math.pi * i / n_stas
            pos = [round(radius * math.cos(angle), 2), round(radius * math.sin(angle), 2)]
            nodes.append(NodeConfig(id=f"sta{i}", type="sta", links=links, mlo_mode=mlo_mode, position=pos))
        traffic = [
            TrafficConfig(src=f"sta{i}", dst="ap0", type="udp_cbr", rate_mbps=50.0, ac="BE")
            for i in range(n_stas)
        ]
        return cls(
            simulation=SimulationConfig(duration_us=duration_us, seed=seed),
            nodes=nodes,
            traffic=traffic,
        )
