"""
builder.py — wires together nodes, PHY, MAC, network layer from SimConfig.
Called once by SimulationEngine.run() before the event loop starts.
"""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nxwlansim.core.engine import SimulationEngine

from nxwlansim.core.registry import NodeRegistry
from nxwlansim.core.node import APNode, STANode


def build_simulation(engine: "SimulationEngine") -> NodeRegistry:
    cfg = engine.config
    registry = NodeRegistry()

    # 1. Build PHY backend
    phy = _build_phy(cfg)

    # 2. Instantiate nodes
    for node_cfg in cfg.nodes:
        node = APNode(node_cfg) if node_cfg.type == "ap" else STANode(node_cfg)
        node.phy = phy
        node.attach(engine)
        registry.register(node)

    # 3. Associate STAs to nearest AP
    _associate_nodes(registry)

    # 4. Attach MAC components (MLO manager, EDCA scheduler) — Phase 1 stubs
    _attach_mac(engine, registry)

    # 5. Schedule initial traffic generation events
    _schedule_traffic(engine, registry, cfg)

    return registry


def _build_phy(cfg):
    if cfg.phy.backend == "matlab":
        from nxwlansim.phy.matlab.adaptive_phy import AdaptivePhy
        return AdaptivePhy(cfg.phy)
    from nxwlansim.phy.tgbe_channel import TGbeChannel
    return TGbeChannel(cfg.phy)


def _associate_nodes(registry: NodeRegistry) -> None:
    import math
    aps = registry.aps()
    if not aps:
        return
    for sta in registry.stas():
        nearest_ap = min(
            aps,
            key=lambda ap: math.dist(sta.position, ap.position),
        )
        sta.associated_ap = nearest_ap.node_id
        nearest_ap.associate(sta.node_id)


def _attach_mac(engine, registry: NodeRegistry) -> None:
    from nxwlansim.mac.mlo import MLOLinkManager
    from nxwlansim.mac.edca import EDCAScheduler
    from nxwlansim.mac.txop import TXOPEngine
    from nxwlansim.mac.rx import RXProcessor
    for node in registry:
        node.mlo_manager = MLOLinkManager(node, engine)
        node.edca_scheduler = EDCAScheduler(node, engine)
        node.txop_engine = TXOPEngine(node, engine)
        node.rx_processor = RXProcessor(node, engine)
        from nxwlansim.mac.npca import NPCAEngine
        node.npca_engine = NPCAEngine(node)
        node.pcap_hook = None   # set below if pcap enabled

    # Register node positions with PHY after all nodes are built
    for node in registry:
        if hasattr(node.phy, "register_node"):
            node.phy.register_node(node.node_id, node.position)

    # Attach PCAP hooks if enabled
    if engine.config.obs.pcap:
        import os
        from nxwlansim.observe.pcap import PCAPWriter
        from nxwlansim.observe.pcap_hook import PCAPHook
        pcap_dir = os.path.join(engine.config.obs.output_dir, "pcap")
        writer = PCAPWriter(pcap_dir)
        engine._pcap_writer = writer
        for node in registry:
            node.pcap_hook = PCAPHook(node.node_id, writer)


def _schedule_traffic(engine, registry: NodeRegistry, cfg) -> None:
    from nxwlansim.traffic.generators import schedule_traffic_sources
    schedule_traffic_sources(engine, registry, cfg.traffic)
    # Boot TXOP engines for all nodes — starts backoff loops on each link
    for node in registry:
        for link_id in node.links:
            node.txop_engine.start_link(link_id)
