"""
NxWlanSimEnv — OpenAI Gymnasium environment wrapper.
Exposes the simulator as a Gym env for RL-based MAC policy research.
Stub for Phase 1 — action/observation spaces defined here for Phase 3 RL integration.
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
    logger.debug("gymnasium not installed — NxWlanSimEnv unavailable.")


if _GYM_AVAILABLE:

    class NxWlanSimEnv(gym.Env):
        """
        Gymnasium env wrapping nxwlansim.

        Observation: per-link queue depth, SNR, current MCS for each STA
        Action:      link selection for EMLMR, or MCS override
        Reward:      aggregate throughput - penalty for retransmissions
        """

        metadata = {"render_modes": ["human"]}

        def __init__(self, config_path: str, render_mode=None):
            super().__init__()
            self.render_mode = render_mode
            self._config_path = config_path
            self._sim = None

            # Placeholder spaces — sized for 2-link, 5-STA scenario
            self.observation_space = gym.spaces.Box(
                low=0.0, high=1.0, shape=(5 * 2 * 3,), dtype=float
            )  # n_stas × n_links × [queue_depth, snr_norm, mcs_norm]

            self.action_space = gym.spaces.Discrete(3)
            # 0=link0, 1=link1, 2=both (STR)

        def reset(self, seed=None, options=None):
            super().reset(seed=seed)
            import nxwlansim as nx
            self._sim = nx.Simulation.from_yaml(self._config_path)
            obs = self._get_obs()
            return obs, {}

        def step(self, action):
            # Apply action to EMLMR link selection policy
            # Run sim forward one step (1 TXOP)
            obs = self._get_obs()
            reward = 0.0   # populated in Phase 3
            terminated = False
            truncated = False
            return obs, reward, terminated, truncated, {}

        def _get_obs(self):
            import numpy as np
            return np.zeros(self.observation_space.shape, dtype=float)

        def render(self):
            pass

else:

    class NxWlanSimEnv:
        def __init__(self, *args, **kwargs):
            raise ImportError(
                "gymnasium is required for NxWlanSimEnv. "
                "Install with: pip install gymnasium"
            )
