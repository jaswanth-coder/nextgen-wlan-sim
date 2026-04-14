"""
MatlabTableGenerator — generates PER/SNR tables via MATLAB WLAN Toolbox.
Requires: matlab.engine (pip install matlabengine==25.1 for R2025a)
"""
from __future__ import annotations
import logging
import numpy as np
from nxwlansim.phy.matlab.cache import TableSet
from nxwlansim.phy.matlab.table_phy import _MCS_RATE_20MHZ

logger = logging.getLogger(__name__)

SNR_MIN, SNR_MAX, SNR_STEP = -5.0, 40.0, 0.5
_SNR_POINTS = np.arange(SNR_MIN, SNR_MAX + SNR_STEP, SNR_STEP)   # 91 points


class MatlabTableGenerator:
    def __init__(self, engine=None):
        self._eng = engine

    def generate(
        self,
        channel_model: str = "D",
        bw_list: list[int] | None = None,
        mcs_range: tuple[int, int] = (0, 13),
        ant_configs: list[tuple[int, int]] | None = None,
        custom_mat_path: str | None = None,
    ) -> TableSet:
        bw_list = bw_list or [20, 40, 80, 160, 320]
        ant_configs = ant_configs or [(1, 1), (2, 2), (4, 4)]
        eng = self._eng or self._start_engine()
        tables: TableSet = {}
        mcs_list = list(range(mcs_range[0], mcs_range[1] + 1))
        total = len(bw_list) * len(mcs_list) * len(ant_configs)
        done = 0
        for bw in bw_list:
            for mcs in mcs_list:
                for n_tx, n_rx in ant_configs:
                    done += 1
                    logger.info("[Gen] %d/%d  model=%s bw=%d mcs=%d ant=%dx%d",
                                done, total, channel_model, bw, mcs, n_tx, n_rx)
                    per_arr, tput_arr = self._sweep(
                        eng, channel_model, bw, mcs, n_tx, n_rx, custom_mat_path
                    )
                    tables[(channel_model, bw, mcs, n_tx, n_rx)] = {
                        "snr_db": _SNR_POINTS.copy(),
                        "per": per_arr,
                        "tput_mbps": tput_arr,
                    }
        if self._eng is None:
            eng.quit()
        return tables

    def _start_engine(self):
        import matlab.engine
        logger.info("[Gen] Starting MATLAB engine ...")
        return matlab.engine.start_matlab("-nodisplay -nosplash -nodesktop")

    def _sweep(self, eng, model, bw, mcs, n_tx, n_rx, custom_mat_path) -> tuple[np.ndarray, np.ndarray]:
        per_list, tput_list = [], []
        fallback_rate = _MCS_RATE_20MHZ[min(mcs, 13)] * (bw / 20)
        for snr in _SNR_POINTS:
            try:
                cfg = eng.wlanEHTSUConfig(
                    "ChannelBandwidth", f"CBW{bw}",
                    "MCS", int(mcs),
                    "NumTransmitAntennas", int(n_tx),
                    "NumSpaceTimeStreams", int(n_tx),
                    nargout=1,
                )
                psdu_len = 1000
                bits = eng.randi([1, 1], [psdu_len * 8, 1], nargout=1)
                tx = eng.wlanWaveformGenerator(bits, cfg, nargout=1)
                if custom_mat_path:
                    ch_data = eng.load(custom_mat_path, nargout=1)
                    rx = eng.filter(ch_data["channel"], tx, nargout=1)
                else:
                    ch = eng.wlanTGbeChannel(
                        "DelayProfile", f"Model-{model}",
                        "NumTransmitAntennas", int(n_tx),
                        "NumReceiveAntennas", int(n_rx),
                        "SampleRate", eng.wlanSampleRate(cfg, nargout=1),
                        nargout=1,
                    )
                    rx = eng.step(ch, tx, nargout=1)
                rx_noisy = eng.awgn(rx, float(snr), "measured", nargout=1)
                rx_bits = eng.wlanEHTDataRecover(
                    rx_noisy,
                    eng.ones([52, 1], nargout=1),
                    float(snr), cfg, nargout=1,
                )
                ber, fer = eng.biterr(bits, rx_bits, nargout=2)
                per_val = min(max(float(fer), 0.0), 1.0)
            except Exception as exc:
                logger.debug("[Gen] MATLAB error snr=%.1f: %s", snr, exc)
                per_val = 1.0
            per_list.append(per_val)
            tput_list.append(fallback_rate * (1.0 - per_val))
        return np.array(per_list), np.array(tput_list)
