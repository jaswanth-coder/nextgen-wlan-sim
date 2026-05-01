"""
Generate minimal HDF5 fixture table for CI tests (no MATLAB required).
Run once: python3 scripts/generate_fixture_tables.py
"""
import os
import numpy as np
import h5py

FIXTURE_PATH = "tests/fixtures/tgbe_d_fixture.h5"
SNR = np.arange(0.0, 45.0, 5.0)       # 9 SNR points
MCS_THRESH = {0: 3.0, 4: 16.5, 9: 30.0}
MCS_RATE_80MHZ = {0: 34.4, 4: 206.4, 9: 458.8}  # Mbps at 80 MHz

os.makedirs(os.path.dirname(FIXTURE_PATH), exist_ok=True)
with h5py.File(FIXTURE_PATH, "w") as f:
    for mcs, thresh in MCS_THRESH.items():
        grp = f.require_group(f"D/80/{mcs}/1x1")
        per = 1.0 / (1.0 + np.exp((SNR - thresh) * 2.0))
        tput = MCS_RATE_80MHZ[mcs] * (1.0 - per)
        grp.create_dataset("snr_db", data=SNR)
        grp.create_dataset("per", data=per)
        grp.create_dataset("tput_mbps", data=tput)

print(f"Fixture written: {FIXTURE_PATH}  ({os.path.getsize(FIXTURE_PATH)} bytes)")
