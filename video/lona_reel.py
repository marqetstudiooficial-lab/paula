#!/usr/bin/env python3
"""Reel «la lona viaja por Valencia» (N81): la lona real, siempre de frente y en el mismo
sitio, mientras el fondo y el suelo cambian a ritmo de música. Cierre en blanco con
Playfair Display.

  python3 video/lona_reel.py --lona lona_rect.png --backgrounds fondos/*.png \
      --music cancion.mp3 --line1 "De calle en calle," --line2 "hasta tu casa." --out n81.mp4

- `--lona`: la tela de la lona ya enderezada (rectángulo frontal). La estructura (postes,
  barras y pies de hormigón verdes) se dibuja aquí, igual que la real.
- Cada fondo se recorta a 9:16 y se le ajusta la lona (luz y color) para que se integre.
- Con `--music` los cambios caen en los golpes graves (bombo) de la canción; sin música,
  un cambio cada `--beat` segundos.
"""
import argparse
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFilter

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import editorial  # noqa: E402

W, H, FPS = 1080, 1920, 30
FONTS = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fonts")

# Geometría fija de la lona en el encuadre (px de 1080x1920)
LONA_W = 788             # 73 % del ancho, como en la foto de referencia
GROUND_Y = 1286          # pies al 67 % de la altura (tela del 45 % al 63 %)
FEET_H = 46
POST_W = 18


def font(name, size, weight=None):
    from PIL import ImageFont
    f = ImageFont.truetype(os.path.join(FONTS, name), size)
    if weight is not None:
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
    return f


def cover(img):
    s = max(W / img.width, H / img.height)
    img = img.resize((round(img.width * s), round(img.height * s)), Image.LANCZOS)
    x, y = (img.width - W) // 2, (img.height - H) // 2
    return img.crop((x, y, x + W, y + H))


def build_stand(lona):
    """Devuelve (RGBA de la lona con estructura, posición x,y) a tamaño final."""
    lh = round(LONA_W * lona.height / lona.width)
    fab = lona.convert("RGB").resize((LONA_W, lh), Image.LANCZOS)
    fab_bottom = GROUND_Y - FEET_H - 22
    fab_top = fab_bottom - lh
    pad = 40
    sw, sh = LONA_W + 2 * pad, GROUND_Y - fab_top + 40
    stand = Image.new("RGBA", (sw, sh), (0, 0, 0, 0))
    d = ImageDraw.Draw(stand)
    fy = 20                                  # tela empieza aquí dentro del stand
    gy = fy + (GROUND_Y - fab_top)           # suelo dentro del stand
    lx, rx = pad - POST_W + 2, pad + LONA_W - 2
    dark, hi = (24, 24, 24, 255), (70, 70, 70, 255)
    # barras superior e inferior
    d.rounded_rectangle((lx, fy - 14, rx + POST_W, fy - 2), 5, fill=dark)
    d.rounded_rectangle((lx, fy + lh + 2, rx + POST_W, fy + lh + 13), 5, fill=dark)
    # postes
    for x in (lx, rx):
        d.rounded_rectangle((x, fy - 22, x + POST_W, gy - 8), 6, fill=dark)
        d.line((x + 4, fy - 18, x + 4, gy - 12), fill=hi, width=2)
    stand.paste(fab, (pad, fy))
    # pies de hormigón verdes (bloques con sombreado)
    for x in (lx, rx):
        cx = x + POST_W // 2
        x0, x1 = cx - 78, cx + 78
        d.polygon([(x0, gy), (x1, gy), (x1 - 8, gy - FEET_H + 10), (x0 + 8, gy - FEET_H + 10)],
                  fill=(104, 184, 78, 255))
        d.rectangle((x0 + 8, gy - FEET_H + 10, x1 - 8, gy - FEET_H + 22), fill=(126, 205, 96, 255))
        d.rectangle((cx - 30, gy - FEET_H, cx + 30, gy - FEET_H + 12), fill=(116, 196, 88, 255))
        d.line((x0, gy - 1, x1, gy - 1), fill=(70, 130, 52, 255), width=3)
    return stand, ((W - sw) // 2, fab_top - fy)


def shadow_layer(stand, pos):
    """Sombra de contacto bajo los pies y oscurecido suave bajo la lona."""
    sh = Image.new("L", (W, H), 0)
    d = ImageDraw.Draw(sh)
    x0, y0 = pos
    sw = stand.width
    d.ellipse((x0 + 10, GROUND_Y - 22, x0 + sw - 10, GROUND_Y + 26), fill=95)
    for cx in (x0 + 40, x0 + sw - 40):
        d.ellipse((cx - 95, GROUND_Y - 10, cx + 95, GROUND_Y + 16), fill=150)
    return sh.filter(ImageFilter.GaussianBlur(14))


def match_light(stand, bg_arr, strength=0.35):
    """Acerca la luz/color de la lona a la del fondo (parcial, para no desvirtuar la marca)."""
    a = np.asarray(stand).astype(np.float32)
    rgb, alpha = a[..., :3], a[..., 3:]
    ref = bg_arr[int(H * 0.35):int(H * 0.85)].reshape(-1, 3).astype(np.float32).mean(0)
    gain = (ref / ref.mean()) ** strength            # dominante de color
    lum = (ref.mean() / 128.0) ** (strength * 0.8)   # luz general
    rgb = np.clip(rgb * gain * lum, 0, 255)
    return Image.fromarray(np.concatenate([rgb, alpha], -1).astype(np.uint8), "RGBA")


def compose(bg, stand, pos):
    bg = cover(bg.convert("RGB"))
    arr = np.asarray(bg).astype(np.float32)
    sh = np.asarray(shadow_layer(stand, pos)).astype(np.float32)[..., None] / 255
    arr = arr * (1 - 0.55 * sh)
    out = Image.fromarray(arr.astype(np.uint8)).convert("RGBA")
    st = match_light(stand, np.asarray(bg))
    out.alpha_composite(st, pos)
    return out.convert("RGB")


def end_card(line1, line2, brand, progress):
    """Pantalla blanca, letras negras en Playfair Display; progress 0..1 para el fundido."""
    img = Image.new("RGB", (W, H), (255, 255, 255))
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    f1 = font("PlayfairDisplay-Italic[wght].ttf", 76, 400)
    f2 = font("PlayfairDisplay[wght].ttf", 76, 400)
    fb = font("PlayfairDisplay[wght].ttf", 26, 400)

    def centered(y, text, f, alpha, tracking=0):
        if tracking:
            ws = [d.textlength(c, font=f) for c in text]
            x = (W - sum(ws) - tracking * (len(text) - 1)) / 2
            for c, w in zip(text, ws):
                d.text((x, y), c, font=f, fill=(17, 17, 17, alpha))
                x += w + tracking
        else:
            d.text(((W - d.textlength(text, font=f)) / 2, y), text, font=f,
                   fill=(17, 17, 17, alpha))

    def a(t0, t1):
        return int(255 * min(1, max(0, (progress - t0) / (t1 - t0))))
    centered(820, line1, f1, a(0.00, 0.25))
    centered(915, line2, f2, a(0.20, 0.45))
    if brand:
        d.line((W / 2 - 30, 1075, W / 2 + 30, 1075), fill=(17, 17, 17, a(0.40, 0.6)), width=1)
        centered(1100, brand, fb, a(0.45, 0.70), tracking=6)
    img.paste(layer, (0, 0), layer)
    return img


def beat_times(music, min_gap):
    import audio_sync
    hits = audio_sync.onsets(music, lo=30, hi=180, min_gap=min_gap, sensitivity=0.2)
    return hits, audio_sync.duration(music)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--lona", required=True)
    ap.add_argument("--backgrounds", nargs="+", required=True)
    ap.add_argument("--music")
    ap.add_argument("--music-start", type=float, default=0.0)
    ap.add_argument("--beat", type=float, default=0.5, help="sin música: segundos por fondo")
    ap.add_argument("--min-gap", type=float, default=0.35,
                    help="con música: tiempo mínimo entre cambios de fondo")
    ap.add_argument("--montage", type=float, default=7.0, help="duración del montaje (s)")
    ap.add_argument("--end", type=float, default=3.2, help="duración del cierre en blanco (s)")
    ap.add_argument("--line1", default="De calle en calle,")
    ap.add_argument("--line2", default="hasta tu casa.")
    ap.add_argument("--brand", default="l'aixeta · proyectos & reformas")
    ap.add_argument("--grade", action="store_true", help="aplica el look editorial a los fondos")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    stand, pos = build_stand(Image.open(a.lona))
    frames_bg = []
    for p in a.backgrounds:
        bg = Image.open(p)
        if a.grade:
            arr = np.asarray(cover(bg.convert("RGB")))
            bg = Image.fromarray(editorial.grade(arr, editorial.measure(arr)))
        frames_bg.append(compose(bg, stand, pos))
        print("fondo", os.path.basename(p))

    if a.music:
        hits, dur = beat_times(a.music, a.min_gap)
        hits = [t - a.music_start for t in hits if a.music_start <= t < a.music_start + a.montage]
        cuts = sorted({0} | {round(t * FPS) for t in hits})
    else:
        cuts = list(range(0, round(a.montage * FPS), round(a.beat * FPS)))
    mont_n = round(a.montage * FPS)
    end_n = round(a.end * FPS)
    total = mont_n + end_n

    enc = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    if a.music:
        enc += ["-ss", str(a.music_start), "-i", a.music, "-map", "0:v", "-map", "1:a",
                "-c:a", "aac", "-b:a", "192k",
                "-af", f"afade=t=out:st={total / FPS - 1.2:.2f}:d=1.2"]
    enc += ["-t", f"{total / FPS:.3f}", "-c:v", "libx264", "-preset", "slow", "-crf", "19",
            "-maxrate", "20M", "-bufsize", "40M", "-pix_fmt", "yuv420p",
            "-movflags", "+faststart", a.out]
    proc = subprocess.Popen(enc, stdin=subprocess.PIPE)
    rng = np.random.default_rng(3)
    idx = -1
    for f in range(mont_n):
        if f in cuts:
            idx = (idx + 1) % len(frames_bg)
        arr = editorial.add_grain(np.asarray(frames_bg[idx]), rng, 2.5)
        proc.stdin.write(arr.tobytes())
    for i in range(end_n):
        proc.stdin.write(end_card(a.line1, a.line2, a.brand, i / (end_n * 0.75)).tobytes())
    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit("ffmpeg ha fallado")
    print(f"OK {a.out}: {total / FPS:.2f}s, {len(cuts)} cambios de fondo")


if __name__ == "__main__":
    main()
