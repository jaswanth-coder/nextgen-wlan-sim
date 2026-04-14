# MATLAB R2025a — Ubuntu Install Guide

## 1. Install MATLAB (individual license, GUI method)

```bash
# Download Linux installer zip from mathworks.com/downloads after logging in
unzip matlab_R2025a_Linux.zip -d ~/matlab-installer
cd ~/matlab-installer
chmod +x install
./install   # GUI walks you through MathWorks login + license activation
```

Default install path: `/usr/local/MATLAB/R2025a`

### Silent/CLI install (alternative)
```bash
# Edit installer_input.txt inside the zip:
#   destinationFolder=/usr/local/MATLAB/R2025a
#   fileInstallationKey=XXXXX-XXXXX-XXXXX-XXXXX
#   agreeToLicense=yes
#   mode=silent
./install -inputFile ~/matlab-installer/installer_input.txt
```

## 2. Ubuntu dependencies (install before running MATLAB)

```bash
sudo apt-get install -y \
    libxt6 libxmu6 libgl1-mesa-glx libglu1-mesa \
    libasound2 libXtst6 libXrandr2 libXcursor1 \
    libxss1 libXcomposite1 libXdamage1 libxkbcommon0 \
    ca-certificates
```

## 3. Install matlabengine Python package

```bash
# R2025a → version 25.1
pip install matlabengine==25.1

# Version map:
# R2025a → 25.1  |  R2024b → 24.2  |  R2024a → 24.1  |  R2023b → 23.2
```

Requires Python 3.9–3.12 (R2025a).

## 4. Environment variables (add to ~/.bashrc)

```bash
export MATLAB_ROOT=/usr/local/MATLAB/R2025a
export LD_LIBRARY_PATH=$MATLAB_ROOT/bin/glnxa64:$MATLAB_ROOT/sys/os/glnxa64:$LD_LIBRARY_PATH
# For headless / no display:
export MATLAB_SHELL=/bin/bash
```

## 5. Verify WLAN Toolbox

```python
# scripts/verify_matlab.py
import matlab.engine

eng = matlab.engine.start_matlab("-nodisplay -nosplash -nodesktop")

# Check WLAN Toolbox
result = eng.ver('wlan', nargout=1)
print("WLAN Toolbox:", result)

has_wlan = eng.license('test', 'WLAN_System_Toolbox', nargout=1)
print("Licensed:", bool(has_wlan))

eng.quit()
print("OK")
```

```bash
python3 scripts/verify_matlab.py
```

## 6. Kernel 6.x note

MATLAB R2024b+ supports kernel 5.15+. Kernel 6.17 is fully compatible — no patches needed.
