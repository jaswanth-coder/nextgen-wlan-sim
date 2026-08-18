"""
EmlmrPolicyEnv — episode-level Gymnasium environment for tuning EMLMR
link-selection policies.

One Gym "step" == one complete simulation run. The DES engine has no
pause/resume hook (see policy_engine.py for why), so this env suits
black-box / episodic optimizers (random search, CMA-ES, evolutionary
strategies, contextual bandits) rather than per-timestep RL. If/when the
engine grows a resumable run loop, a true step-wise env can be added
alongside this one without touching it.

Action      : Box(2,) -- [w_queue, w_snr] weights fed to RLLinkSelectionPolicy
Observation : Box(3,) -- static scenario features
              [n_stas, n_emlmr_stas, total_offered_load_mbps]
              (constant for a fixed config; mainly here so this conforms to
              the Gym API cleanly when training across multiple configs)
Reward      : sum of per-node throughput (Mbps) minus a penalty per BA timeout
"""

from __future__ import annotations

import logging

logger = logging.getLogger(__name__)

try:
    import gymnasium as gym
    import numpy as np
    _GYM_AVAILABLE = True
except ImportError:
    _GYM_AVAILABLE = False
    logger.debug("gymnasium not installed — EmlmrPolicyEnv unavailable.")


if _GYM_AVAILABLE:

    class EmlmrPolicyEnv(gym.Env):
        """
        Example:
            env = EmlmrPolicyEnv("configs/examples/mlo_emlmr_multiap.yaml")
            obs, info = env.reset()
            obs, reward, terminated, truncated, info = env.step([1.0, 0.0])
            print(info["summary"])
        """

        metadata = {"render_modes": ["human"]}

        def __init__(self, config_path: str, ba_timeout_penalty: float = 0.5, render_mode=None):
            super().__init__()
            self.render_mode = render_mode
            self._config_path = config_path
            self._ba_timeout_penalty = ba_timeout_penalty
            self._last_results = None

            self.action_space = gym.spaces.Box(
                low=np.array([0.0, 0.0], dtype=float),
                high=np.array([5.0, 5.0], dtype=float),
                dtype=float,
            )
            self.observation_space = gym.spaces.Box(
                low=0.0, high=1e6, shape=(3,), dtype=float
            )

        def reset(self, seed=None, options=None):
            super().reset(seed=seed)
            self._last_results = None
            return self._static_obs(), {}

        def step(self, action):
            from nxwlansim.core.config import SimConfig
            from nxwlansim.gym.rl.policy_engine import PolicyInjectableEngine
            from nxwlansim.gym.rl.policies import RLLinkSelectionPolicy

            weights = tuple(float(w) for w in action)
            cfg = SimConfig.from_yaml(self._config_path)
            engine = PolicyInjectableEngine(
                cfg, policy_factory=lambda: RLLinkSelectionPolicy(weights)
            )
            results = engine.run()
            self._last_results = results

            reward = self._compute_reward(results, engine)
            obs = self._static_obs()
            terminated = True   # each step is a complete, self-contained episode
            truncated = False
            info = {"summary": results.summary()}
            return obs, reward, terminated, truncated, info

        def _compute_reward(self, results, engine) -> float:
            dur_us = engine.clock_ns / 1_000.0
            total_tput = 0.0
            total_penalty = 0.0
            for m in results._node_metrics.values():
                total_tput += m.throughput_mbps(dur_us)
                total_penalty += m.ba_timeouts * self._ba_timeout_penalty
            return total_tput - total_penalty

        def _static_obs(self):
            from nxwlansim.core.config import SimConfig
            cfg = SimConfig.from_yaml(self._config_path)
            n_stas = sum(1 for n in cfg.nodes if n.type == "sta")
            n_emlmr = sum(1 for n in cfg.nodes if n.type == "sta" and n.mlo_mode == "emlmr")
            offered_load = sum(getattr(t, "rate_mbps", 0.0) for t in cfg.traffic)
            return np.array([n_stas, n_emlmr, offered_load], dtype=float)

        def render(self):
            if self._last_results is not None:
                print(self._last_results.summary())

else:

    class EmlmrPolicyEnv:
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "gymnasium is required for EmlmrPolicyEnv. "
                "Install with: pip install gymnasium"
            )
