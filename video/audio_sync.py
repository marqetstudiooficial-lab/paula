"""Detección de golpes en la música para cortar las fotos al ritmo (numpy, sin librerías extra).

- `onsets(path)`: momentos (s) en que cambia el sonido — ataques en medios/agudos, que es
  donde están los «tics» y percusiones; se descartan los que caen a menos de `min_gap`.
- `silence_start(path)`: primer momento, tras la parte sonora, en que el audio cae a silencio
  (el corte en seco donde entra el plano final). None si no hay.
- `duration(path)`.
"""
import subprocess

import numpy as np

SR, HOP, N = 22050, 256, 2048


def _load(path):
    raw = subprocess.run(["ffmpeg", "-v", "error", "-i", path, "-vn", "-ac", "1", "-ar", str(SR),
                          "-f", "f32le", "-"], capture_output=True, check=True).stdout
    return np.frombuffer(raw, np.float32)


def duration(path):
    return len(_load(path)) / SR


def onsets(path, lo=150, hi=11000, min_gap=0.06, sensitivity=0.15):
    x = _load(path)
    frames = np.lib.stride_tricks.sliding_window_view(x, N)[::HOP] * np.hanning(N)
    spec = np.abs(np.fft.rfft(frames, axis=1))
    freqs = np.fft.rfftfreq(N, 1 / SR)
    band = (freqs >= lo) & (freqs < hi)
    log = np.log1p(10 * spec[:, band])
    flux = np.concatenate([[0], np.maximum(np.diff(log, axis=0), 0).sum(1)])
    flux /= max(flux.max(), 1e-9)
    thr = np.convolve(flux, np.ones(41) / 41, "same") + sensitivity
    t = (np.arange(len(flux)) * HOP + N / 2) / SR  # centro de la ventana
    out = []
    for i in range(4, len(flux) - 4):
        if flux[i] > thr[i] and flux[i] == flux[i - 4:i + 5].max():
            if not out or t[i] - out[-1] >= min_gap:
                out.append(float(t[i]))
    return out


def silence_start(path, floor_ratio=0.2, min_len=0.3):
    x = _load(path)
    win = int(0.02 * SR)
    rms = np.sqrt((x[: len(x) // win * win].reshape(-1, win) ** 2).mean(1))
    loud = np.percentile(rms, 75)
    quiet = rms < loud * floor_ratio
    need = int(min_len / 0.02)
    started = False
    for i in range(len(rms)):
        if not quiet[i]:
            started = True
        elif started and quiet[i:i + need].all():
            return i * 0.02
    return None
