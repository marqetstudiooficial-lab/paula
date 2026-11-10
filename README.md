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

`video/loading_reel.py` monta un reel vertical (1080x1920, 30 fps, ~7,3 s) con la estructura
de un reel de referencia: planos de obra cortados cada vez más rápido, barra de carga que se
llena en ~5 s, y al llegar al 100 % un plano final con créditos pequeños y un título gigante
rosa. Necesita `ffmpeg` y Pillow; las fuentes (licencia OFL) están en `video/fonts/`.

```bash
python3 video/loading_reel.py --clips obra/*.mp4 --reveal final.mp4 \
  --title SON --credits "Nombre Uno" "Nombre Dos" --subtitle presentan \
  --music musica.mp3 --out reel.mp4
```

Opciones útiles: `--speed 1.5` (más metraje de obra), `--reveal-dur 2` (plano final más
largo), `--reveal-start 3.2` (desde qué segundo del clip final), `--music-start 12`.
