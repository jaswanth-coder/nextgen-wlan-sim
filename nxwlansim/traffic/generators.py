"""
Traffic generators: UDP CBR, Poisson, VoIP (G.711), Video burst.
Each generator schedules DES events to inject frames into the MAC queue.
"""

from __future__ import annotations

import random
import itertools
import logging
from typing import TYPE_CHECKING

from nxwlansim.mac.frame import MPDUFrame
from nxwlansim.core.engine import TRAFFIC_GEN

if TYPE_CHECKING:
    from nxwlansim.core.engine import SimulationEngine
    from nxwlansim.core.registry import NodeRegistry
    from nxwlansim.core.config import TrafficConfig

logger = logging.getLogger(__name__)
_frame_id = itertools.count(1)


class UDPCBRGenerator:
    """Constant Bit Rate UDP traffic source."""

    def __init__(self, src: str, dst: str, rate_mbps: float, ac: str,
                 payload_bytes: int = 1460):
        self.src = src
        self.dst = dst
        self.ac = ac
        self.payload_bytes = payload_bytes
        self._interval_ns = int(payload_bytes * 8 / (rate_mbps * 1e6) * 1e9)

    def start(self, engine: "SimulationEngine", registry: "NodeRegistry") -> None:
        engine.schedule(
            time_ns=engine.now_ns,
            callback=self._send,
            priority=TRAFFIC_GEN,
            engine_ref=engine,
            registry=registry,
        )

    def _send(self, engine, engine_ref, registry, **_) -> None:
        node = registry.get(self.src)
        frame = MPDUFrame(
            frame_id=next(_frame_id),
            src=self.src,
            dst=self.dst,
            size_bytes=self.payload_bytes,
            ac=self.ac,
            timestamp_ns=engine.now_ns,
        )
        node.edca_scheduler.enqueue(frame)
        engine.schedule_after(
            delay_ns=self._interval_ns,
            callback=self._send,
            priority=TRAFFIC_GEN,
            engine_ref=engine_ref,
            registry=registry,
        )


class PoissonGenerator:
    """Poisson-distributed packet arrivals."""

    def __init__(self, src: str, dst: str, rate_mbps: float, ac: str,
                 payload_bytes: int = 1460, seed: int = 0):
        self.src = src
        self.dst = dst
        self.ac = ac
        self.payload_bytes = payload_bytes
        self._mean_interval_ns = int(payload_bytes * 8 / (rate_mbps * 1e6) * 1e9)
        self._rng = random.Random(seed)

    def start(self, engine: "SimulationEngine", registry: "NodeRegistry") -> None:
        engine.schedule(
            time_ns=engine.now_ns,
            callback=self._send,
            priority=TRAFFIC_GEN,
            engine_ref=engine,
            registry=registry,
        )

    def _send(self, engine, engine_ref, registry, **_) -> None:
        node = registry.get(self.src)
        frame = MPDUFrame(
            frame_id=next(_frame_id),
            src=self.src,
            dst=self.dst,
            size_bytes=self.payload_bytes,
            ac=self.ac,
            timestamp_ns=engine.now_ns,
        )
        node.edca_scheduler.enqueue(frame)
        delay = int(self._rng.expovariate(1 / self._mean_interval_ns))
        engine.schedule_after(
            delay_ns=delay,
            callback=self._send,
            priority=TRAFFIC_GEN,
            engine_ref=engine_ref,
            registry=registry,
        )


class VoIPGenerator:
    """G.711 VoIP: 20 ms talk spurts, 160-byte frames @ 64 kbps."""

    def __init__(self, src: str, dst: str):
        self.src = src
        self.dst = dst

    def start(self, engine: "SimulationEngine", registry: "NodeRegistry") -> None:
        engine.schedule(
            time_ns=engine.now_ns,
            callback=self._send,
            priority=TRAFFIC_GEN,
            engine_ref=engine,
            registry=registry,
        )

    def _send(self, engine, engine_ref, registry, **_) -> None:
        node = registry.get(self.src)
        frame = MPDUFrame(
            frame_id=next(_frame_id),
            src=self.src,
            dst=self.dst,
            size_bytes=160,
            ac="VO",
            timestamp_ns=engine.now_ns,
        )
        node.edca_scheduler.enqueue(frame)
        engine.schedule_after(
            delay_ns=20_000_000,   # 20 ms
            callback=self._send,
            priority=TRAFFIC_GEN,
            engine_ref=engine_ref,
            registry=registry,
        )


class VideoGenerator:
    """H.265 video burst: variable frame sizes, 30 fps."""

    def __init__(self, src: str, dst: str, bitrate_mbps: float = 20.0, seed: int = 0):
        self.src = src
        self.dst = dst
        self._frame_interval_ns = int(1e9 / 30)   # 30 fps = ~33 ms
        self._frame_bytes = int(bitrate_mbps * 1e6 / 8 / 30)
        self._rng = random.Random(seed)

    def start(self, engine: "SimulationEngine", registry: "NodeRegistry") -> None:
        engine.schedule(
            time_ns=engine.now_ns,
            callback=self._send,
            priority=TRAFFIC_GEN,
            engine_ref=engine,
            registry=registry,
        )

    def _send(self, engine, engine_ref, registry, **_) -> None:
        node = registry.get(self.src)
        # Vary frame size ±20% to simulate I/P/B frames
        size = int(self._frame_bytes * self._rng.uniform(0.8, 1.2))
        frame = MPDUFrame(
            frame_id=next(_frame_id),
            src=self.src,
            dst=self.dst,
            size_bytes=size,
            ac="VI",
            timestamp_ns=engine.now_ns,
        )
        node.edca_scheduler.enqueue(frame)
        engine.schedule_after(
            delay_ns=self._frame_interval_ns,
            callback=self._send,
            priority=TRAFFIC_GEN,
            engine_ref=engine_ref,
            registry=registry,
        )


_GENERATOR_MAP = {
    "udp_cbr": UDPCBRGenerator,
    "poisson":  PoissonGenerator,
    "voip":     VoIPGenerator,
    "video":    VideoGenerator,
}


def schedule_traffic_sources(
    engine: "SimulationEngine",
    registry: "NodeRegistry",
    traffic_cfgs: list["TrafficConfig"],
) -> None:
    for tc in traffic_cfgs:
        cls = _GENERATOR_MAP.get(tc.type)
        if cls is None:
            logger.warning("Unknown traffic type: %s", tc.type)
            continue
        if tc.type == "udp_cbr":
            gen = UDPCBRGenerator(tc.src, tc.dst, tc.rate_mbps, tc.ac)
        elif tc.type == "poisson":
            gen = PoissonGenerator(tc.src, tc.dst, tc.rate_mbps, tc.ac)
        elif tc.type == "voip":
            gen = VoIPGenerator(tc.src, tc.dst)
        elif tc.type == "video":
            gen = VideoGenerator(tc.src, tc.dst, tc.rate_mbps)
        else:
            continue
        gen.start(engine, registry)
        logger.debug("Traffic source scheduled: %s → %s (%s)", tc.src, tc.dst, tc.type)
