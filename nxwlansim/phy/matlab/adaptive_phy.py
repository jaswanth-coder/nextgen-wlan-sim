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

# Fixture path works in dev checkout only (tests/ dir not shipped with installed package).
# For installed deployments, supply a cache_dir with pre-generated tables.
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
        except ImportError as exc:
            logger.warning("[AdaptivePhy] matlab.engine not installed: %s", exc)
            return None
        except Exception as exc:
            # Only swallow MATLAB communication errors, not programmer errors
            exc_type = type(exc).__name__
            if any(s in exc_type for s in ("Matlab", "Engine", "matlab")):
                logger.warning("[AdaptivePhy] MATLAB error during generation: %s", exc)
                return None
            raise

    def register_node(self, node_id: str, position: tuple[float, float]) -> None:
        if hasattr(self._backend, "register_node"):
            self._backend.register_node(node_id, position)

    def get_channel_state(self, src_id: str, dst_id: str, link_id: str) -> ChannelState:
        return self._backend.get_channel_state(src_id, dst_id, link_id)

    def request_tx(self, frame: "Frame", link: "LinkContext") -> TxResult:
        return self._backend.request_tx(frame, link)

    def request_rx(self, frame: "Frame", channel: ChannelState) -> RxResult:
        return self._backend.request_rx(frame, channel)
