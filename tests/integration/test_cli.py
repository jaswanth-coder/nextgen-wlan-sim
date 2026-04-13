"""
CLI integration tests.
Runs `nxwlansim` as a subprocess to verify end-to-end CLI operation.
"""

import os
import subprocess
import sys
import pytest

EXAMPLES_DIR = os.path.join(
    os.path.dirname(__file__), "..", "..", "configs", "examples"
)


def run_cli(*args, timeout=30):
    """Run nxwlansim CLI and return (returncode, stdout, stderr)."""
    cmd = [sys.executable, "-m", "nxwlansim.cli.main"] + list(args)
    result = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        timeout=timeout,
        cwd=os.path.join(os.path.dirname(__file__), "..", ".."),
    )
    return result.returncode, result.stdout, result.stderr


def test_cli_info():
    """nxwlansim info must print version and exit 0."""
    rc, out, err = run_cli("info")
    assert rc == 0, f"CLI info failed:\n{err}"
    assert "nxwlansim version" in out
    assert "0.1.0" in out


def test_cli_run_str_basic():
    """nxwlansim run mlo_str_basic.yaml must exit 0 and print summary."""
    config = os.path.join(EXAMPLES_DIR, "mlo_str_basic.yaml")
    rc, out, err = run_cli("run", config, "--output-dir", "/tmp/nxwlansim_cli_test")
    assert rc == 0, f"CLI run failed:\n{err}\n{out}"
    assert "Duration" in out or "Simulation" in out


def test_cli_run_with_csv_flag():
    """nxwlansim run --csv must create metrics.csv."""
    config = os.path.join(EXAMPLES_DIR, "mlo_str_basic.yaml")
    output_dir = "/tmp/nxwlansim_cli_csv_test"
    rc, out, err = run_cli("run", config, "--csv", "--output-dir", output_dir)
    assert rc == 0, f"CLI run --csv failed:\n{err}"
    csv_path = os.path.join(output_dir, "metrics.csv")
    assert os.path.exists(csv_path), "metrics.csv not created by CLI"


def test_cli_run_emlsr():
    rc, out, err = run_cli(
        "run",
        os.path.join(EXAMPLES_DIR, "mlo_emlsr_2sta.yaml"),
        "--output-dir", "/tmp/nxwlansim_cli_emlsr",
    )
    assert rc == 0, f"EMLSR CLI run failed:\n{err}"


def test_cli_run_unknown_config_exits_nonzero():
    """Missing config file must exit non-zero."""
    rc, out, err = run_cli("run", "/nonexistent/config.yaml")
    assert rc != 0
