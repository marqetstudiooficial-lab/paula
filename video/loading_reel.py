#!/usr/bin/env python3
"""Reel «Loading…»: montaje frenético de obra con barra de carga + revelación final.

Estructura copiada del reel de referencia (1080x1920, 30 fps):

  fase A  0,13 → 3,30 s   un corte cada 5 fotogramas (~6 cortes/s)
  fase B  3,30 → 5,00 s   cortes cada 2-3 fotogramas, la barra sigue llenándose
  fase C  5,00 → 6,27 s   barra al 100 %, desaparece «Loading», cortes de 1-2 fotogramas
  reveal  6,27 → final    vídeo final + título (Playfair Display)

La barra se llena de forma lineal (0 → 100 % en ~4,9 s), con independencia de los cortes.
Los planos de obra se repiten en bucle, igual que en la referencia.

Todo el material (fotos y vídeo final) pasa por el mismo «look» editorial:
  1. recorte centrado a 9:16,
  2. igualado por archivo: balance de blancos (gray world) y exposición media común,
     para que fotos hechas con luces distintas queden con la misma tonalidad,
  3. look común: negros levantados (mate), altas suaves, color apagado y cálido,
     virado crema en altas / marrón en sombras, viñeta suave y grano fino.

Uso:
  python3 video/loading_reel.py --clips para_editar/*.jpg --reveal para_editar/final.mp4 \
      --title "L'aixeta" --title2 "Reformas" --out reel.mp4 [--export-stills fotos_9x16/]

Necesita ffmpeg, Pillow y numpy. El look editorial está en video/editorial.py.
"""
import argparse
import itertools
import os
import subprocess
import sys

import numpy as np
from PIL import Image, ImageDraw, ImageFont

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import editorial  # noqa: E402

W, H, FPS = 1080, 1920, 30
HERE = os.path.dirname(os.path.abspath(__file__))
FONTS = os.path.join(HERE, "fonts")
CREAM = (247, 242, 232)
STILL_EXT = (".jpg", ".jpeg", ".png", ".webp", ".heic", ".tif", ".tiff")

def font(name, size, weight=None):
    f = ImageFont.truetype(os.path.join(FONTS, name), size)
    if weight is not None:
        try:
            f.set_variation_by_axes([weight])
        except Exception:
            pass
    return f


def is_still(path):
    return path.lower().endswith(STILL_EXT)


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


CROP = f"scale={W}:{H}:force_original_aspect_ratio=increase,crop={W}:{H}"


def grab(path, offset, n):
    """Devuelve n fotogramas 1080x1920 (numpy uint8) de un clip o foto, recortados a 9:16."""
    cmd = ["ffmpeg", "-v", "error"]
    cmd += ["-i", path] if is_still(path) else ["-ss", f"{offset:.3f}", "-i", path]
    cmd += ["-vf", f"fps={FPS},{CROP},format=rgb24",
            "-frames:v", str(1 if is_still(path) else n), "-f", "rawvideo", "-"]
    raw = subprocess.run(cmd, capture_output=True, check=True).stdout
    size = W * H * 3
    frames = [np.frombuffer(raw[i:i + size], np.uint8).reshape(H, W, 3)
              for i in range(0, len(raw) - size + 1, size)]
    if not frames:
        raise SystemExit(f"No he podido leer fotogramas de {path} en {offset:.2f}s")
    while len(frames) < n:  # foto, o clip más corto de lo pedido: repite el último
        frames.append(frames[-1])
    return frames


class Shot:
    """Un plano con su igualado medido una sola vez (así no parpadea)."""

    def __init__(self, path, start=0.0, span=1.0):
        self.path, self.still = path, is_still(path)
        self.dur = 0.0 if self.still else duration(path)
        ref = grab(path, start + (0 if self.still else min(span, self.dur) / 2), 1)[0]
        self.params = editorial.measure(ref)
        self.cache = editorial.grade(ref, self.params) if self.still else None

    def frames(self, offset, n):
        if self.still:
            return [self.cache] * n
        return [editorial.grade(f, self.params) for f in grab(self.path, offset, n)]


def duration(path):
    out = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "format=duration",
                          "-of", "csv=p=0", path], capture_output=True, text=True).stdout
    try:
        return float(out.strip())
    except ValueError:
        return 0.0


def draw_bar(img, fill, frame_idx, text):
    """Barra redondeada con borde fino + texto con puntos animados."""
    x0, y0, x1, y1 = 150, 926, 893, 970
    r = (y1 - y0) // 2
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    d.rounded_rectangle((x0, y0, x1, y1), r, fill=(255, 255, 255, 38),
                        outline=(255, 255, 255, 210), width=3)
    if fill > 0:
        fx = x0 + max(2 * r, int((x1 - x0) * fill))
        d.rounded_rectangle((x0, y0, fx, y1), r, fill=CREAM + (255,))
    if text:
        from PIL import ImageFilter
        dots = "." * ((frame_idx // 6) % 4)
        f = font("PlayfairDisplay-Italic[wght].ttf", 34, 600)
        tw = d.textlength(text, font=f)
        tx, ty = (W - tw) / 2, 976
        glow = Image.new("RGBA", (W, H), (0, 0, 0, 0))
        ImageDraw.Draw(glow).text((tx, ty + 1), text + dots, font=f, fill=(40, 30, 20, 190))
        layer = Image.alpha_composite(layer, glow.filter(ImageFilter.GaussianBlur(5)))
        ImageDraw.Draw(layer).text((tx, ty), text + dots, font=f, fill=(255, 255, 255, 255))
    img.paste(Image.alpha_composite(img.convert("RGBA"), layer).convert("RGB"))


def title_layer(title, title2):
    """«L'aixeta» grande en Playfair Display + «Reformas» en cursiva debajo, en crema."""
    layer = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    d = ImageDraw.Draw(layer)
    lines = []
    if title:
        size = 210
        f = font("PlayfairDisplay[wght].ttf", size, 500)
        while d.textlength(title, font=f) > W * 0.82 and size > 60:
            size -= 6
            f = font("PlayfairDisplay[wght].ttf", size, 500)
        lines.append((title, f))
    if title2:
        lines.append((title2, font("PlayfairDisplay-Italic[wght].ttf", 104, 400)))
    boxes = [d.textbbox((0, 0), t, font=f) for t, f in lines]
    gap = 10
    total = sum(b[3] - b[1] for b in boxes) + gap * (len(lines) - 1)
    y = 1150 - total / 2
    text = Image.new("RGBA", (W, H), (0, 0, 0, 0))
    td = ImageDraw.Draw(text)
    for (t, f), b in zip(lines, boxes):
        x = (W - (b[2] - b[0])) / 2 - b[0]
        td.text((x, y - b[1]), t, font=f, fill=CREAM + (255,))
        y += (b[3] - b[1]) + gap
    # sombra suave para que se lea sobre cualquier fondo
    from PIL import ImageFilter
    shadow = text.split()[3].filter(ImageFilter.GaussianBlur(18)).point(lambda v: int(v * 0.45))
    layer.paste((0, 0, 0, 255), (0, 0), shadow)
    return Image.alpha_composite(layer, text)


def detail_score(arr):
    """Cantidad de detalle (bordes) de una zona: sirve para elegir encuadres interesantes."""
    import numpy as np
    g = arr.astype(np.float32)
    return float(np.abs(np.diff(g, axis=0)).mean() + np.abs(np.diff(g, axis=1)).mean())


def prepare_stills(paths, tmp_dir, details):
    """Endereza las fotos (EXIF) y añade `details` encuadres de detalle 9:16 por foto.

    Devuelve la lista de archivos ya orientados, intercalando los detalles para que
    no salgan seguidos los recortes de la misma foto.
    """
    import numpy as np
    from PIL import ImageOps
    os.makedirs(tmp_dir, exist_ok=True)
    per_photo = []
    for p in paths:
        if not is_still(p):
            per_photo.append([p])
            continue
        im = ImageOps.exif_transpose(Image.open(p)).convert("RGB")
        base = os.path.splitext(os.path.basename(p))[0]
        # encuadre principal 9:16 centrado
        cw = min(im.width, im.height * 9 / 16)
        ch = cw * 16 / 9
        x0, y0 = (im.width - cw) / 2, (im.height - ch) / 2
        main = im.crop((int(x0), int(y0), int(x0 + cw), int(y0 + ch))).resize((W, H), Image.LANCZOS)
        out = [os.path.join(tmp_dir, f"{base}_0.png")]
        main.save(out[0])
        # detalles: zoom 1,8-2,4x en las zonas con más textura, sin solaparse demasiado
        small = np.asarray(im.convert("L").resize((im.width // 8, im.height // 8)))
        cands = []
        for zoom in (1.8, 2.4):
            dw, dh = cw / zoom, ch / zoom
            for fx in np.linspace(0, 1, 5):
                for fy in np.linspace(0, 1, 6):
                    x = (im.width - dw) * fx
                    y = (im.height - dh) * fy
                    sub = small[int(y / 8):int((y + dh) / 8), int(x / 8):int((x + dw) / 8)]
                    cands.append((detail_score(sub), x, y, dw, dh))
        cands.sort(reverse=True)
        chosen = []
        for sc, x, y, dw, dh in cands:
            cx, cy = x + dw / 2, y + dh / 2
            if all(abs(cx - (c[1] + c[3] / 2)) > c[3] * 0.6 or abs(cy - (c[2] + c[4] / 2)) > c[4] * 0.6
                   for c in chosen):
                chosen.append((sc, x, y, dw, dh))
            if len(chosen) == details:
                break
        for i, (_, x, y, dw, dh) in enumerate(chosen, 1):
            crop = im.crop((int(x), int(y), int(x + dw), int(y + dh))).resize((W, H), Image.LANCZOS)
            path = os.path.join(tmp_dir, f"{base}_{i}.png")
            crop.save(path)
            out.append(path)
        per_photo.append(out)
    # intercalado: principal de cada foto, luego primer detalle de cada una, etc.
    result = []
    for i in range(max(len(x) for x in per_photo)):
        result += [x[i] for x in per_photo if i < len(x)]
    return result


def export_stills(paths, out_dir):
    os.makedirs(out_dir, exist_ok=True)
    rng = np.random.default_rng(7)
    for p in paths:
        if not is_still(p):
            continue
        img = editorial.add_grain(Shot(p).cache, rng, 3.0)
        out = os.path.join(out_dir, os.path.splitext(os.path.basename(p))[0] + "_9x16.jpg")
        Image.fromarray(img).save(out, quality=94)
        print("foto", out)


def main():
    ap = argparse.ArgumentParser(description=__doc__,
                                 formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--clips", nargs="+", required=True,
                    help="planos de obra (fotos o vídeos), en el orden en que se repetirán")
    ap.add_argument("--reveal", required=True, help="vídeo (o foto) final")
    ap.add_argument("--reveal-start", type=float, default=0.0,
                    help="segundo del clip final desde el que empezar")
    ap.add_argument("--reveal-dur", type=float, default=2.5,
                    help="duración del plano final (la referencia usa 1,03 s)")
    ap.add_argument("--title", default="L'aixeta")
    ap.add_argument("--title2", default="Reformas")
    ap.add_argument("--loading-text", default="Loading")
    ap.add_argument("--speed", type=float, default=1.0,
                    help=">1 alarga las fases de obra (1,5 = 50 %% más de metraje)")
    ap.add_argument("--music", help="audio para el reel (se recorta a la duración)")
    ap.add_argument("--music-start", type=float, default=0.0)
    ap.add_argument("--details", type=int, default=2,
                    help="encuadres de detalle extra que se sacan de cada foto (0 = ninguno)")
    ap.add_argument("--work-dir", default="/tmp/loading_reel",
                    help="carpeta para los encuadres intermedios")
    ap.add_argument("--export-stills", metavar="DIR",
                    help="guarda también cada foto con el look editorial a 9:16 en DIR")
    ap.add_argument("--out", required=True)
    a = ap.parse_args()

    shots = prepare_stills(a.clips, a.work_dir, a.details)
    if a.export_stills:
        export_stills(shots, a.export_stills)
    if is_still(a.reveal):
        a.reveal = prepare_stills([a.reveal], a.work_dir, 0)[0]

    s = a.speed
    bar_start, bar_full = 4, round(150 * s)          # fotogramas
    a_end, b_end, c_end = round(99 * s), bar_full, round(188 * s)
    lengths = cut_lengths(a_end, b_end, c_end, start=bar_start)
    reveal_n = round(a.reveal_dur * FPS)
    total = c_end + reveal_n

    clips = [Shot(p) for p in shots]
    offsets = {id(c): 0.0 for c in clips}
    rng = np.random.default_rng(1)
    enc = ["ffmpeg", "-v", "error", "-y", "-f", "rawvideo", "-pix_fmt", "rgb24",
           "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
    if a.music:
        enc += ["-ss", str(a.music_start), "-i", a.music, "-map", "0:v", "-map", "1:a",
                "-c:a", "aac", "-b:a", "192k",
                "-af", f"afade=t=out:st={total / FPS - 0.4:.2f}:d=0.4"]
    enc += ["-t", f"{total / FPS:.3f}", "-c:v", "libx264", "-preset", "medium", "-crf", "16",
            "-pix_fmt", "yuv420p", "-movflags", "+faststart", a.out]
    proc = subprocess.Popen(enc, stdin=subprocess.PIPE)

    def emit(arr):
        proc.stdin.write(editorial.add_grain(arr, rng).tobytes())

    frame = 0
    for arr in clips[0].frames(0, bar_start):  # arranque sin barra
        emit(arr)
        frame += 1

    cycle = itertools.cycle(clips)
    for n in lengths:
        shot = next(cycle)
        off = offsets[id(shot)]
        if shot.dur and off + n / FPS > shot.dur - 0.05:
            off = 0.0
        offsets[id(shot)] = off + 0.6  # la próxima vez que salga, otro momento del clip
        for arr in shot.frames(off, n):
            img = Image.fromarray(arr)
            fill = min(1.0, (frame - bar_start) / (bar_full - bar_start))
            draw_bar(img, fill, frame, a.loading_text if fill < 1.0 else "")
            emit(np.asarray(img))
            frame += 1

    overlay = title_layer(a.title, a.title2)
    fade = 6  # el título entra en 0,2 s
    reveal = Shot(a.reveal, a.reveal_start, a.reveal_dur)
    for i, arr in enumerate(reveal.frames(a.reveal_start, reveal_n)):
        ov = overlay
        if i < fade:
            ov = overlay.copy()
            ov.putalpha(overlay.split()[3].point(lambda v, k=(i + 1) / fade: int(v * k)))
        out = Image.alpha_composite(Image.fromarray(arr).convert("RGBA"), ov).convert("RGB")
        emit(np.asarray(out))
        frame += 1

    proc.stdin.close()
    if proc.wait() != 0:
        sys.exit("ffmpeg ha fallado al codificar")
    print(f"OK {a.out}: {frame} fotogramas, {frame / FPS:.2f} s, {len(lengths)} cortes")


if __name__ == "__main__":
    main()
