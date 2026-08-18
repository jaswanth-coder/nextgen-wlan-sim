"""
Unit tests for nxwlansim.gym.rl — EmlmrPolicyEnv and RLLinkSelectionPolicy.

New test file only; does not modify any existing test.
"""
import pytest

gymnasium = pytest.importorskip("gymnasium")

from nxwlansim.gym.rl import EmlmrPolicyEnv, RLLinkSelectionPolicy
from nxwlansim.mac.mlo import LinkContext, LinkState


EXAMPLE_CONFIG = "configs/examples/mlo_emlmr_multiap.yaml"


class _FakeNode:
    node_id = "sta0"
    mlo_mode = "emlmr"
    edca_scheduler = None
    phy = None
    associated_ap = None


def test_policy_rejects_wrong_weight_length():
    with pytest.raises(ValueError):
        RLLinkSelectionPolicy(weights=(1.0,))


def test_policy_select_returns_empty_when_no_idle_links():
    ctx = LinkContext("6g", _FakeNode())
    ctx.state = LinkState.TRANSMITTING
    policy = RLLinkSelectionPolicy(weights=(1.0, 0.0))
    assert policy.select([ctx], n_radios=2) == []


def test_policy_select_respects_n_radios():
    node = _FakeNode()
    contexts = [LinkContext(link_id, node) for link_id in ("5g", "6g")]
    policy = RLLinkSelectionPolicy(weights=(1.0, 0.0))
    selected = policy.select(contexts, n_radios=1)
    assert len(selected) == 1
    assert selected[0] in contexts


def test_env_reset_returns_static_obs():
    env = EmlmrPolicyEnv(EXAMPLE_CONFIG)
    obs, info = env.reset()
    assert obs.shape == (3,)
    # mlo_emlmr_multiap.yaml has 3 STAs, 2 of which are emlmr
    assert obs[0] == 3
    assert obs[1] == 2


def test_env_step_runs_full_episode_and_returns_reward():
    env = EmlmrPolicyEnv(EXAMPLE_CONFIG)
    env.reset()
    obs, reward, terminated, truncated, info = env.step([1.0, 0.0])
    assert terminated is True
    assert truncated is False
    assert isinstance(reward, float)
    assert reward > 0.0   # some throughput should be achieved
    assert "summary" in info
