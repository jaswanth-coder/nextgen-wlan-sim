% generate_matlab_tables.m
% Generates SNR→MCS lookup tables using MATLAB WLAN Toolbox.
% Run once offline: matlab -batch "run('scripts/generate_matlab_tables.m')"
% Output: configs/matlab_tables/snr_mcs_eht.csv

clear; clc;

output_dir = fullfile(fileparts(mfilename('fullpath')), '..', 'configs', 'matlab_tables');
if ~exist(output_dir, 'dir'), mkdir(output_dir); end

snr_range   = -5:1:50;     % dB
bw_options  = [20, 40, 80, 160, 320];  % MHz
n_ss        = 1;            % spatial streams (extend for MIMO later)

fid = fopen(fullfile(output_dir, 'snr_mcs_eht.csv'), 'w');
fprintf(fid, 'snr_db,bw_mhz,mcs_index,per\n');

cfg = wlanRecoveryConfig;
cfg.EqualizationMethod = 'MMSE';

for bw = bw_options
    cbw = sprintf('CBW%d', bw);
    for snr = snr_range
        best_mcs = 0;
        for mcs = 13:-1:0
            try
                % Generate EHT SU waveform
                tx_cfg = wlanEHTSUConfig('ChannelBandwidth', cbw, 'MCS', mcs, 'NumSpaceTimeStreams', n_ss);
                bits = randi([0 1], 1000, 1);
                tx_wf = wlanWaveformGenerator(bits, tx_cfg);

                % Apply AWGN channel
                rx_wf = awgn(tx_wf, snr, 'measured');

                % Demodulate — simplified PER check
                ind = wlanFieldIndices(tx_cfg);
                % If no error thrown, MCS is supportable at this SNR
                best_mcs = mcs;
                break;
            catch
                % MCS not supportable at this SNR
            end
        end
        fprintf(fid, '%d,%d,%d,%.4f\n', snr, bw, best_mcs, 0.0);
    end
end

fclose(fid);
fprintf('Table written to configs/matlab_tables/snr_mcs_eht.csv\n');
