# paula — puente a Google Sheets

Skill que permite a Claude **leer y editar** Google Sheets directamente: valores, fórmulas,
colores de relleno y fuente, bordes, ancho de columnas, combinar celdas, listas
desplegables, crear y duplicar hojas.

Los conectores estándar de Google Drive sólo saben leer. Aquí el camino es otro: dentro de
Google se instala un pequeño programa (Apps Script) con su propia dirección web. Claude le
manda un JSON con una contraseña, el programa hace lo pedido y responde en JSON. Funciona
con los permisos de quien lo instaló: puede exactamente lo mismo que esa persona a mano.

```
Claude  ->  tools/gsheets.sh|ps1  ->  dirección web de Apps Script  ->  Google Sheets
```

## Qué hay aquí

| Archivo | Para qué |
|---|---|
| `.claude/skills/google-tablicy/SKILL.md` | el skill: cómo trabajar, reglas, chuleta de comandos |
| `.claude/skills/google-tablicy/reference/nastroyka.md` | instalación paso a paso y qué hacer si se rompe |
| `.claude/skills/google-tablicy/reference/komandy.md` | todas las acciones, ejemplos de peticiones y errores típicos |
| `.claude/skills/google-tablicy/assets/gsheets-webapp.gs` | el código que se pega en Apps Script |
| `tools/gsheets.sh` | puente para Mac / Linux (necesita `jq`) |
| `tools/gsheets.ps1` | puente para Windows (UTF-8 con BOM) |
| `.gsheets.json.example` | plantilla de la configuración |

## Puesta en marcha (una sola vez, ~10 minutos)

Dile a Claude: **«configura el puente a Google Sheets»**. Él te dictará los pasos uno a uno.
La parte del navegador la haces tú; los archivos los crea él.

Resumen de lo que harás en el navegador:

1. https://script.google.com → **Nuevo proyecto** (con la misma cuenta que edita la hoja).
2. Pegar el código de `assets/gsheets-webapp.gs` y poner la contraseña generada en `TOKEN`.
3. **Implementar → Nueva implementación → Aplicación web**, ejecutar como **yo**, acceso
   para **cualquier usuario**.
4. Pasar la pantalla de aviso de Google y copiar la dirección `.../exec`.
5. Claude guarda dirección y contraseña en `.gsheets.json` (ignorado por git).

Comprobación:

```bash
bash tools/gsheets.sh ping
# {"ok":true,"ping":"скрипт работает","version":4}
```

## Uso

```bash
echo '{"action":"listSheets","table":"presupuesto"}' > zapros.json
bash tools/gsheets.sh zapros.json
```

En Windows: `powershell -ExecutionPolicy Bypass -File tools\gsheets.ps1 -PayloadFile zapros.json`

Con `GSHEETS_CONFIG` se puede apuntar a otro archivo de configuración.

## Seguridad

- **Dirección web + contraseña = acceso completo a todas las hojas de esa cuenta.** No las
  reenvíes a nadie, no las subas a git, no las pegues en un chat. `.gsheets.json` está en
  `.gitignore`.
- Si la contraseña se filtra: cambia `TOKEN` en Apps Script, vuelve a implementar con
  **Nueva versión** y actualiza `.gsheets.json`. La dirección no cambia.
- Borrar una hoja es irreversible y exige `"confirm": true` explícito.

## Vídeo: reel «Loading…»

`video/loading_reel.py` monta un reel vertical (1080x1920, 30 fps) con la estructura de un
reel de referencia: planos de obra cortados cada vez más rápido, barra de carga que se llena
en ~5 s y, al llegar al 100 %, el vídeo final con «L'aixeta / Reformas» en Playfair Display.

- Las fotos se enderezan (EXIF), se recortan a 9:16 y de cada una salen además 2 encuadres
  de detalle (`--details`), para que haya variedad aunque haya pocas fotos.
- Todo (fotos y vídeo final) pasa por el look editorial de `video/editorial.py`: igualado de
  balance de blancos, exposición y contraste por archivo, y después color apagado, negros
  mate, virado cálido crema/marrón, viñeta suave y grano.
- Necesita `ffmpeg`, Pillow y numpy. Fuentes (licencia OFL) en `video/fonts/`.

```bash
python3 video/loading_reel.py --clips fotos/*.JPG --reveal final.MOV --reveal-dur 3 \
  --export-stills fotos_9x16/ --out reel.mp4
```

Con `--music audio.mp4` las fotos cambian **en cada golpe de la música** (`video/audio_sync.py`
detecta los cambios de sonido) y el vídeo final entra cuando el audio se corta a silencio; el
reel dura lo mismo que el audio. `--no-sync` vuelve a los tiempos fijos de la referencia y
`--reveal-at 6.2` fuerza el momento del final.

Otras opciones: `--music-start 12`, `--speed 1.5` (más metraje de obra),
`--reveal-start 1.2` (desde qué segundo del vídeo final), `--title` / `--title2`.
