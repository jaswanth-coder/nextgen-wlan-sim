"""
CLI entry point: nxwlansim

Usage:
    nxwlansim run configs/examples/mlo_str_basic.yaml
    nxwlansim run config.yaml --csv --pcap --viz
    nxwlansim run config.yaml --phy-backend matlab --matlab-mode medium
    nxwlansim info
"""

import argparse
import logging
import sys


def main():
    parser = argparse.ArgumentParser(
        prog="nxwlansim",
        description="Next-Generation WLAN Simulator — IEEE 802.11be (WiFi 7/8)",
    )
    sub = parser.add_subparsers(dest="command", required=True)

    # --- run ---
    run_p = sub.add_parser("run", help="Run a simulation from a YAML config file")
    run_p.add_argument("config", help="Path to YAML config file")
    run_p.add_argument("--log",          action="store_true", help="Enable text logging")
    run_p.add_argument("--csv",          action="store_true", help="Write CSV metrics")
    run_p.add_argument("--pcap",         action="store_true", help="Write PCAP captures")
    run_p.add_argument("--viz",          action="store_true", help="Enable visualization")
    run_p.add_argument("--phy-backend",  choices=["tgbe", "matlab"], help="PHY backend override")
    run_p.add_argument("--matlab-mode",  choices=["loose", "medium"], help="MATLAB mode override")
    run_p.add_argument("--output-dir",   default="results", help="Output directory")
    run_p.add_argument("-v", "--verbose", action="store_true", help="Verbose logging")

    # --- info ---
    info_p = sub.add_parser("info", help="Print simulator version and dependency status")

    args = parser.parse_args()

    logging.basicConfig(
        level=logging.DEBUG if getattr(args, "verbose", False) else logging.INFO,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    )

    if args.command == "run":
        _run(args)
    elif args.command == "info":
        _info()


def _run(args) -> None:
    import nxwlansim as nx
    from nxwlansim.core.config import SimConfig

    cfg = SimConfig.from_yaml(args.config)

    # CLI overrides
    if args.log:    cfg.obs.log  = True
    if args.csv:    cfg.obs.csv  = True
    if args.pcap:   cfg.obs.pcap = True
    if args.viz:    cfg.obs.viz  = True
    if args.phy_backend:  cfg.phy.backend     = args.phy_backend
    if args.matlab_mode:  cfg.phy.matlab_mode = args.matlab_mode
    cfg.obs.output_dir = args.output_dir

    sim = nx.Simulation(cfg)
    results = sim.run()
    print(results.summary())


def _info() -> None:
    import nxwlansim
    print(f"nxwlansim version : {nxwlansim.__version__}")
    print(f"Python            : {sys.version.split()[0]}")
    # Check optional deps
    for pkg in ["numpy", "matplotlib", "scapy", "flask", "gymnasium", "matlab.engine"]:
        try:
            __import__(pkg.replace(".", "_") if "." in pkg else pkg)
            status = "installed"
        except ImportError:
            status = "NOT installed"
        print(f"  {pkg:<20} {status}")


if __name__ == "__main__":
    main()

