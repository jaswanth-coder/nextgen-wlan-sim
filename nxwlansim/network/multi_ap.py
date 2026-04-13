"""
MultiAPCoordinator — Phase 3 placeholder.
AP-to-AP signaling, roaming, C-OFDMA, Co-SR hooks.
"""

from __future__ import annotations


class MultiAPCoordinator:
    """
    Placeholder for Phase 3 Multi-AP Coordination.
    Provides hooks for:
      - AP-to-AP signaling (ideal backhaul, configurable latency)
      - Roaming: STA triggers reassociation on RSSI threshold
      - C-OFDMA resource unit allocation
      - Coordinated Spatial Reuse (Co-SR)
    """

    def __init__(self):
        self._backhaul_latency_ns: int = 0   # ideal by default
        self._roam_rssi_threshold_db: float = -70.0

    def set_backhaul_latency_us(self, latency_us: int) -> None:
        self._backhaul_latency_ns = latency_us * 1_000

    # Stubs — to be implemented in Phase 3
    def coordinate_ofdma(self, *args, **kwargs):
        raise NotImplementedError("C-OFDMA: Phase 3")

    def coordinate_sr(self, *args, **kwargs):
        raise NotImplementedError("Co-SR: Phase 3")

    def trigger_roam(self, sta_id: str, target_ap_id: str, engine):
        raise NotImplementedError("Roaming: Phase 3")
