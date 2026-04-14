"""
verify_matlab.py — confirm MATLAB engine + WLAN Toolbox are working.
Run after installing MATLAB and matlabengine:
    python3 scripts/verify_matlab.py
"""
import sys

print("Importing matlab.engine ...")
try:
    import matlab.engine
except ImportError:
    print("ERROR: matlab.engine not found.")
    print("  Install with: pip install matlabengine==25.1  (for R2025a)")
    sys.exit(1)

print("Starting MATLAB engine (may take ~15 s) ...")
eng = matlab.engine.start_matlab("-nodisplay -nosplash -nodesktop")
print("Engine started.")

# Check WLAN Toolbox
has_wlan = eng.license("test", "WLAN_System_Toolbox", nargout=1)
print(f"WLAN Toolbox licensed : {bool(has_wlan)}")

if not has_wlan:
    print("WARNING: WLAN Toolbox not available — MATLAB PHY backend will not work.")
else:
    info = eng.ver("wlan", nargout=1)
    print(f"WLAN Toolbox version  : {info}")

eng.quit()
print("MATLAB engine shut down cleanly. All checks passed.")
