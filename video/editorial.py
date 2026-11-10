"""Look editorial común para fotos y vídeo (numpy).

Cada archivo se iguala primero por separado y después recibe el mismo look, para que
fotos hechas con luces distintas (ventana, fluorescente, día nublado…) queden con la
misma tonalidad:

  1. igualado por archivo (parámetros medidos una sola vez por archivo → sin parpadeo):
     - balance de blancos gray-world sobre los tonos medios (ignora ventanas quemadas),
     - luminancia media y contraste llevados a una referencia común;
  2. look común:
     - color apagado (saturación al 62 %),
     - altas suaves (no queman), negros levantados (acabado mate),
     - virado cálido: sombras marrón, altas crema,
     - viñeta muy suave y grano fino distinto en cada fotograma.
"""
import numpy as np

LUMA = np.array([0.299, 0.587, 0.114], np.float32)
TARGET_MEAN, TARGET_STD = 0.50, 0.20
SATURATION = 0.62
SHADOW_TINT = np.array([0.040, 0.016, -0.025], np.float32)
HIGHLIGHT_TINT = np.array([0.030, 0.012, -0.040], np.float32)
GLOBAL_WARM = np.array([0.028, 0.010, -0.032], np.float32)
BLACK, WHITE = 0.075, 0.93

_vignette_cache = {}


def _vignette(h, w, strength=0.16):
    key = (h, w, strength)
    if key not in _vignette_cache:
        y, x = np.ogrid[-1:1:h * 1j, -1:1:w * 1j]
        r = np.sqrt((x * 0.9) ** 2 + (y * 0.75) ** 2) / np.sqrt(0.81 + 0.5625)
        _vignette_cache[key] = (1 - strength * r ** 2.2).astype(np.float32)[..., None]
    return _vignette_cache[key]


def measure(arr):
    """Parámetros de igualado de una imagen (uint8 HxWx3)."""
    f = arr[::4, ::4].astype(np.float32) / 255
    lum = f @ LUMA
    mid = (lum > 0.12) & (lum < 0.90)
    means = f[mid].mean(0) if mid.sum() > 500 else f.reshape(-1, 3).mean(0)
    gains = np.clip(means.mean() / np.maximum(means, 1e-3), 0.75, 1.35).astype(np.float32)
    lum = np.clip(f * gains, 0, 1) @ LUMA
    return {"gains": gains, "mean": float(lum.mean()), "std": float(lum.std())}


def grade(arr, p):
    """Aplica igualado + look. arr uint8 HxWx3 → uint8 HxWx3."""
    f = arr.astype(np.float32) / 255
    f *= p["gains"]
    lum = f @ LUMA
    k = float(np.clip(TARGET_STD / max(p["std"], 1e-3), 0.75, 1.45))
    new = (lum - p["mean"]) * k + TARGET_MEAN
    f += (new - lum)[..., None]
    lum = new
    f = lum[..., None] + (f - lum[..., None]) * SATURATION
    # altas suaves: todo lo que pasa de 0,75 se comprime hacia ~0,97
    d = np.maximum(f - 0.75, 0)
    f = np.where(f > 0.75, 0.75 + d / (1 + d / 0.22), f)
    lum = f @ LUMA
    sh = np.clip(1 - lum / 0.5, 0, 1)[..., None]
    hl = np.clip((lum - 0.5) / 0.5, 0, 1)[..., None]
    f += sh * SHADOW_TINT + hl * HIGHLIGHT_TINT + GLOBAL_WARM
    f = BLACK + np.clip(f, 0, 1) * (WHITE - BLACK)
    f *= _vignette(*arr.shape[:2])
    return (np.clip(f, 0, 1) * 255 + 0.5).astype(np.uint8)


def add_grain(arr, rng, amount=4.0):
    """Grano monocromo fino (distinto en cada llamada)."""
    h, w = arr.shape[:2]
    n = rng.normal(0, amount, (h // 2, w // 2)).astype(np.float32)
    n = np.repeat(np.repeat(n, 2, 0), 2, 1)[:h, :w, None]
    return np.clip(arr.astype(np.float32) + n, 0, 255).astype(np.uint8)
