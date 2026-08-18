#!/usr/bin/env python3
"""
train_emlmr_random_search.py — black-box optimizer for RLLinkSelectionPolicy weights.

Uses EmlmrPolicyEnv (nxwlansim/gym/rl/emlmr_gym_env.py) as a plain Gymnasium
env: samples random [w_queue, w_snr] weight vectors, runs one full episode
(one complete simulation) per sample via env.step(), and reports the
best-performing weights found.

New script only — does not modify any existing file.

Usage:
    python scripts/train_emlmr_random_search.py
    python scripts/train_emlmr_random_search.py --trials 30 --seed 7 \
        --config configs/examples/mlo_emlmr_multiap.yaml

Each trial runs a full simulation (~5-10s wall-clock for the default
config), so --trials 15 takes a couple of minutes. Pass a smaller/shorter
config via --config for faster iteration.
"""

from __future__ import annotations

import argparse
import logging
import time

import numpy as np

from nxwlansim.gym.rl import EmlmrPolicyEnv

# Quiet the simulator's per-event logging (e.g. "[BA-TIMEOUT] ..." warnings)
# so trial-by-trial search progress is readable. This only affects this
# script's process — no existing file is touched.
logging.getLogger("nxwlansim").setLevel(logging.ERROR)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument(
        "--config",
        default="configs/examples/mlo_emlmr_multiap.yaml",
        help="YAML scenario to optimize the EMLMR policy against.",
    )
    p.add_argument("--trials", type=int, default=15, help="Number of random weight samples to evaluate.")
    p.add_argument("--seed", type=int, default=42, help="RNG seed for reproducible search.")
    return p.parse_args()


def main() -> None:
    args = parse_args()
    rng = np.random.default_rng(args.seed)

    env = EmlmrPolicyEnv(args.config)
    env.reset()

    best_weights = None
    best_reward = float("-inf")
    history: list[tuple[tuple[float, float], float]] = []

    print(f"Random search: {args.trials} trials on {args.config}  (seed={args.seed})")
    print(f"{'trial':>5}  {'w_queue':>8}  {'w_snr':>8}  {'reward':>10}  {'time_s':>7}")

    for trial in range(1, args.trials + 1):
        weights = rng.uniform(low=env.action_space.low, high=env.action_space.high)
        t0 = time.time()
        _, reward, _, _, _ = env.step(weights)
        dt = time.time() - t0
        history.append((tuple(weights), reward))

        marker = ""
        if reward > best_reward:
            best_reward = reward
            best_weights = tuple(float(w) for w in weights)
            marker = "  <- new best"

        print(f"{trial:>5}  {weights[0]:>8.3f}  {weights[1]:>8.3f}  {reward:>10.3f}  {dt:>7.2f}{marker}")

    print()
    print("=== Best policy found ===")
    print(f"weights (w_queue, w_snr) = ({best_weights[0]:.3f}, {best_weights[1]:.3f})")
    print(f"reward (throughput Mbps - BA-timeout penalty) = {best_reward:.3f}")
    print()
    print("Reuse it directly (bypassing the Gym wrapper) with:")
    print(
        "  from nxwlansim.gym.rl import RLLinkSelectionPolicy, PolicyInjectableEngine\n"
        "  from nxwlansim.core.config import SimConfig\n"
        f"  cfg = SimConfig.from_yaml({args.config!r})\n"
        f"  policy = lambda: RLLinkSelectionPolicy({best_weights!r})\n"
        "  results = PolicyInjectableEngine(cfg, policy_factory=policy).run()\n"
        "  print(results.summary())"
    )


if __name__ == "__main__":
    main()
