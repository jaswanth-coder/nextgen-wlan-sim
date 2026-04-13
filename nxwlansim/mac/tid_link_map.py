"""
TID-to-Link Mapping — IEEE 802.11be §35.3.7

Maps Traffic Identifiers (TIDs 0-15) to specific links for MLO transmission.
Controls which TIDs are allowed on which links, enabling traffic steering.

Default mapping (negotiated via AddBAReq/MLE):
  - All TIDs allowed on all links (no restriction)

Custom mappings:
  - VoIP (TID 6,7) → 6 GHz only (low latency)
  - Video (TID 4,5) → 5 GHz + 6 GHz
  - Best-effort (TID 0,3) → any link
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional


# 802.11be TID → AC mapping
TID_TO_AC: dict[int, str] = {
    0: "BE", 1: "BK", 2: "BK", 3: "BE",
    4: "VI", 5: "VI", 6: "VO", 7: "VO",
    8: "BE", 9: "BK", 10: "BK", 11: "BE",
    12: "VI", 13: "VI", 14: "VO", 15: "VO",
}


@dataclass
class TIDLinkMap:
    """
    TID-to-link mapping for one MLO node.
    allowed_links[tid] = set of link_ids that TID can use.
    Empty set = no restriction (use any link).
    """
    allowed_links: dict[int, set] = field(
        default_factory=lambda: {tid: set() for tid in range(16)}
    )
    preferred_link: dict[int, Optional[str]] = field(
        default_factory=lambda: {tid: None for tid in range(16)}
    )

    def set_tid_links(self, tid: int, links: list[str], preferred: str | None = None) -> None:
        """Restrict TID to specific links."""
        self.allowed_links[tid] = set(links)
        self.preferred_link[tid] = preferred

    def get_links_for_tid(self, tid: int, available_links: list[str]) -> list[str]:
        """
        Return allowed links for tid, filtered by currently available links.
        If no restriction, return all available links.
        """
        allowed = self.allowed_links.get(tid, set())
        if not allowed:
            return list(available_links)   # no restriction
        return [l for l in available_links if l in allowed]

    def get_preferred_link(self, tid: int, available_links: list[str]) -> str | None:
        """Return preferred link for tid if available, else first allowed."""
        pref = self.preferred_link.get(tid)
        if pref and pref in available_links:
            return pref
        links = self.get_links_for_tid(tid, available_links)
        return links[0] if links else None

    def restrict_ac_to_link(self, ac: str, link_id: str) -> None:
        """Convenience: restrict all TIDs for an AC to a specific link."""
        for tid, mapped_ac in TID_TO_AC.items():
            if mapped_ac == ac:
                if not self.allowed_links[tid]:
                    self.allowed_links[tid] = {link_id}
                else:
                    self.allowed_links[tid].add(link_id)
                self.preferred_link[tid] = link_id


def default_map() -> TIDLinkMap:
    """No restrictions — all TIDs on all links."""
    return TIDLinkMap()


def voip_optimized_map(voip_link: str = "6g", data_links: list | None = None) -> TIDLinkMap:
    """
    VoIP-optimized: route VO TIDs to low-latency 6 GHz link,
    VI/BE/BK to remaining links.
    """
    m = TIDLinkMap()
    data_links = data_links or ["5g", "6g"]
    # VO TIDs (6,7,14,15) → voip_link preferred
    for tid in [6, 7, 14, 15]:
        m.set_tid_links(tid, [voip_link], preferred=voip_link)
    # VI TIDs (4,5,12,13) → any data link
    for tid in [4, 5, 12, 13]:
        m.set_tid_links(tid, data_links)
    return m


def load_balance_map(links: list[str]) -> TIDLinkMap:
    """
    Round-robin TID distribution across links.
    Useful for STR throughput maximization.
    """
    m = TIDLinkMap()
    n = len(links)
    for tid in range(16):
        link = links[tid % n]
        m.set_tid_links(tid, links, preferred=link)
    return m
