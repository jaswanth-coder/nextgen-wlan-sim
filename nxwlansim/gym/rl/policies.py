"""
RLLinkSelectionPolicy — a parametrized EMLMR link-selection policy.

Drop-in alternative to mac.mlo.RoundRobinPolicy / LoadBalancePolicy, driven
by an external weight vector instead of a fixed heuristic, so it can be
tuned by an RL / black-box optimizer via EmlmrPolicyEnv (see
emlmr_gym_env.py).

Score per idle link = -w_queue * queue_depth + w_snr * snr_db
The top `n_radios` idle links by score are assigned a radio.

This subclasses the existing LinkSelectionPolicy ABC defined in
nxwlansim/mac/mlo.py — that file is not modified. Injection into a running
node happens via the public MLOLinkManager.set_emlmr_policy() hook.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Sequence

from nxwlansim.mac.mlo import LinkSelectionPolicy, LinkState

if TYPE_CHECKING:
    from nxwlansim.mac.mlo import LinkContext


class RLLinkSelectionPolicy(LinkSelectionPolicy):
    """EMLMR link selection driven by a 2-element weight vector [w_queue, w_snr]."""

    def __init__(self, weights: Sequence[float] = (1.0, 0.0)):
        if len(weights) != 2:
            raise ValueError("weights must be [w_queue, w_snr]")
        self.w_queue = float(weights[0])
        self.w_snr = float(weights[1])
        # Decision log for reward shaping / debugging: (link_id, queue_depth, snr_db)
        self.decisions: list[tuple[str, int, float]] = []

    def select(self, contexts: list["LinkContext"], n_radios: int) -> list["LinkContext"]:
        idle = [c for c in contexts if c.state == LinkState.IDLE]
        if not idle:
            return []

        scored = [(ctx, self._score(ctx)) for ctx in idle]
        scored.sort(key=lambda pair: pair[1], reverse=True)
        selected = [ctx for ctx, _ in scored[:n_radios]]

        for ctx in selected:
            self.decisions.append((ctx.link_id, self._queue_depth(ctx), self._snr_db(ctx)))

        return selected

    def _score(self, ctx: "LinkContext") -> float:
        return -self.w_queue * self._queue_depth(ctx) + self.w_snr * self._snr_db(ctx)

    @staticmethod
    def _queue_depth(ctx: "LinkContext") -> int:
        sched = getattr(ctx.node, "edca_scheduler", None)
        if sched is None:
            return 0
        return sum(len(q._queue) for q in sched.queues.values())

    @staticmethod
    def _snr_db(ctx: "LinkContext") -> float:
        node = ctx.node
        phy = getattr(node, "phy", None)
        ap_id = getattr(node, "associated_ap", None)
        if phy is None or ap_id is None or not hasattr(phy, "get_channel_state"):
            return 0.0
        try:
            return phy.get_channel_state(node.node_id, ap_id, ctx.link_id).snr_db
        except Exception:
            return 0.0
