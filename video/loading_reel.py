#!/usr/bin/env python3
"""Reel «Loading…»: montaje frenético de obra con barra de carga + revelación final.

Estructura copiada del reel de referencia (7,3 s, 1080x1920, 30 fps):

  fase A  0,13 → 3,30 s   un corte cada 5 fotogramas (~6 cortes/s)
  fase B  3,30 → 5,00 s   cortes cada 2-3 fotogramas, la barra sigue llenándose
  fase C  5,00 → 6,27 s   barra al 100 %, desaparece «Loading», cortes de 1-2 fotogramas
  reveal  6,27 → final    plano de las personas + créditos pequeños + título gigante rosa

La barra se llena de forma lineal (0 → 100 % en ~4,9 s), con independencia de los cortes.
Los planos de obra se repiten en bucle, igual que en la referencia.

Uso mínimo:
  python3 video/loading_reel.py --clips obra/*.mp4 --reveal reveal.mp4 \
      --title SON --credits "NOMBRE UNO" "NOMBRE DOS" --subtitle PRESENTAN \
      --music musica.mp3 --out reel.mp4

Necesita ffmpeg y Pillow.
"""
import argparse
import itertools
import os
import subprocess
import sys

from PIL import Image, ImageDraw, ImageFont

W, H, FPS = 1080, 1920, 30
HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")
PINK = (255, 71, 154)
BAR_FILL = (246, 242, 234)

# Etalonaje cálido y apagado de la referencia (sepia suave, poco contraste).
GRADE = ("eq=saturation=0.72:contrast=0.92:brightness=0.02:gamma=1.05,"
         "colorbalance=rs=0.07:gs=0.03:bs=-0.07:rm=0.05:gm=0.02:bm=-0.06")


def font(name, size):
    return ImageFont.truetype(os.path.join(FONTS, name), size)


def cut_lengths(a_end, b_end, c_end, start=4):
    """Duración en fotogramas de cada corte de obra, hasta el fotograma del reveal."""
    out, f = [], start
    patterns = [(a_end, itertools.cycle([5])),
                (b_end, itertools.cycle([3, 2])),
                (c_end, itertools.cycle([2, 1, 1]))]
    for end, pat in patterns:
        while f < end:
            n = min(next(pat), end - f)
            out.append(n)
            f += n
    return out


def grab(path, offset, n, still):
    """Devuelve n fotogramas RGB 1080x1920 de un clip (o de una foto)."""
    vf = (f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H},"
          f"fps={FPS},{GRADE},format=rgb24")
    cmd = ["ffmpeg", "-v", "error"]
    cmd += ["-loop", "1", "-i", path] if still else ["-ss", f"{offset:.3f}", "-i", path]
    cmd += ["-vf", vf, "-frames:v", str(n), "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    size = W * H * 3
    frames = [Image.frombuffer("RGB", (W, H), raw[i:i + size])
              for i in range(0, len(raw) - size + 1, size)]
    if not frames:
        raise SystemExit(f"No he podido leer fotogramas de {path} en {offset:.2f}s")
    while len(frames) < n:  # clip más corto de lo pedido: congela el último
        frames.append(frames[-1])
    return frames


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    try:
        return float(out.strip())
    except ValueError:
        return 0.0


def draw_bar(img, fill, frame_idx, text):
    """Barra redondeada con borde fino + «Loading» con puntos animados."""
    x0, y0, x1, y1 = 150, 926, 893, 970
    r = (y1 - y0) // 2
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((x0, y0, x1, y1), r, fill=(255, 255, 255, 38),
                        outline=(255, 255, 255, 200), width=3)
    if fill > 0:
        fx = x0 + max(2 * r, int((x1 - x0) * fill))
        d.rounded_rectangle((x0, y0, fx, y1), r, fill=BAR_FILL + (255,))
    if text:
        dots = "." * ((frame_idx // 6) % 4)
        f = font("Poppins-SemiBold.ttf", 25)
        tw = d.textlength(text, font=f)
        tx, ty = (W - tw) / 2, 978
        d.text((tx + 1, ty + 2), text + dots, font=f, fill=(0, 0, 0, 70))
        d.text((tx, ty), text + dots, font=f, fill=(255, 255, 255, 240))
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"))


def spaced(d, xy_center, text, f, fill, tracking):
    """Texto centrado con espaciado entre letras."""
    widths = [d.textlength(c, font=f) for c in text]
    total = sum(widths) + tracking * (len(text) - 1)
    x, y = xy_center[0] - total / 2, xy_center[1]
    for c, w in zip(text, widths):
        d.text((x, y), c, font=f, fill=fill)
        x += w + tracking


def title_layer(title, credits, subtitle, title_font, shear=0.0):
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    small = font("Poppins-Regular.ttf", 30)
    for i, line in enumerate(credits):
        spaced(d, (W / 2, 545 + i * 34), line.upper(), small, PINK + (255,), 3)
    if subtitle:
        spaced(d, (W / 2, 748), subtitle.upper(), small, PINK + (255,), 3)
    if title:
        # Título gigante: se ajusta para ocupar ~78 % del ancho (shear>0 lo inclina).
        size = 300
        f = font(title_font, size)
        while d.textlength(title, font=f) > W * 0.78 and size > 60:
            size -= 6
            f = font(title_font, size)
        txt = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        td = ImageDraw.Draw(txt)
        bbox = td.textbbox((0, 0), title, font=f)
        tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
        td.text(((W - tw) / 2 - bbox[0], 1170 - th / 2 - bbox[1]), title, font=f,
                fill=PINK + (255,))
        if shear:
            txt = txt.transform((W, H), Image.AFFINE, (1, shear, -shear * 1170, 0, 1, 0),
                                resample=Image.BICUBIC)
        layer = Image.alpha_composite(layer, txt)
    return layer


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clips", nargs="+", required=True,
                    help="planos de obra (vídeos o fotos), en el orden en que se repetirán")
    ap.add_argument("--reveal", required=True, help="plano final (vídeo o foto)")
    ap.add_argument("--reveal-start", type=float, default=0.0,
                    help="segundo del clip final desde el que empezar")
    ap.add_argument("--reveal-dur", type=float, default=1.03,
                    help="duración del plano final en segundos (referencia: 1,03)")
    ap.add_argument("--title", default="", help="título gigante rosa")
    ap.add_argument("--title-font", default="RubikMonoOne-Regular.ttf")
    ap.add_argument("--title-shear", type=float, default=0.0,
                    help="inclinación del título (0,12 = cursiva marcada)")
    ap.add_argument("--credits", nargs="*", default=[], help="líneas pequeñas de arriba")
    ap.add_argument("--subtitle", default="", help="palabra pequeña del medio (p. ej. PRESENTAN)")
    ap.add_argument("--loading-text", default="Loading")
    ap.add_argument("--speed", type=float, default=1.0,
                    help=">1 alarga las fases de obra (1,5 = 50 %% más de metraje)")
    ap.add_argument("--music", help="audio para el reel (se recorta a la duración)")
    ap.add_argument("--music-start", type=float, default=0.0)
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    s = a.speed
    bar_start, bar_full = 4, round(150 * s)          # fotogramas
    a_end, b_end, c_end = round(99 * s), bar_full, round(188 * s)
    lengths = cut_lengths(a_end, b_end, c_end, start=bar_start)
    reveal_n = round(a.reveal_dur * FPS)
    total = c_end + reveal_n

    exts_still = (".jpg", ".jpeg", ".png", ".webp", ".heic")
    clips = [(p, p.lower().endswith(exts_still), duration(p)) for p in a.clips]
    offsets = {p: 0.0 for p, _, _ in clips}

    enc = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    if a.music:
        enc += ["-ss", str(a.music_start), "-i", a.music, "-map", "0:v", "-map", "1:a",
                "-c:a", "aac", "-b:a", "192k", "-af", f"afade=t=out:st={total / FPS - 0.25}:d=0.25"]
    enc += ["-t", f"{total / FPS:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "17",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", a.out]
    proc = subprocess.Popen(enc, stdin=subprocess.PIPE)

    frame = 0
    first = grab(clips[0][0], 0, 1, clips[0][1])[0]
    for _ in range(bar_start):  # arranque: primer plano sin barra (como la referencia)
        proc.stdin.write(first.tobytes())
        frame += 1

    cycle = itertools.cycle(clips)
    for n in lengths:
        path, still, dur = next(cycle)
        off = offsets[path]
        if not still and dur and off + n / FPS > dur - 0.05:
            off = 0.0
        frames = grab(path, off, n, still)
        offsets[path] = off + 0.6  # la próxima vez que salga, otro momento del clip
        for img in frames:
            fill = min(1.0, (frame - bar_start) / (bar_full - bar_start))
            draw_bar(img, fill, frame, a.loading_text if fill < 1.0 else "")
            proc.stdin.write(img.tobytes())
            frame += 1

    overlay = title_layer(a.title, a.credits, a.subtitle, a.title_font, a.title_shear)
    rpath = a.reveal
    for img in grab(rpath, a.reveal_start, reveal_n, rpath.lower().endswith(exts_still)):
        out = Image.alpha_composite(img.convert("RGBA"), overlay).convert("RGB")
        proc.stdin.write(out.tobytes())
        frame += 1

    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit("ffmpeg ha fallado al codificar")
    print(f"OK {a.out}: {frame} fotogramas, {frame / FPS:.2f} s, {len(lengths)} cortes")


if __name__ == "__main__":
    main()
