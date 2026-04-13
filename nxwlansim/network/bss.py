"""BasicServiceSet — BSS-only network mode. Single AP + N STAs."""

from __future__ import annotations
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from nxwlansim.core.registry import NodeRegistry


class BasicServiceSet:
    """
    Manages a single BSS. No IP routing — frames addressed directly AP↔STA.
    """

    def __init__(self, ap_id: str, registry: "NodeRegistry"):
        self.ap_id = ap_id
        self._registry = registry

    @property
    def ap(self):
        return self._registry.get(self.ap_id)

    @property
    def stas(self):
        ap = self.ap
        return [self._registry.get(sid) for sid in ap.associated_stas]

    def route(self, src_id: str, dst_id: str) -> list[str]:
        """Return hop list: always [src, dst] in BSS mode."""
        return [src_id, dst_id]
