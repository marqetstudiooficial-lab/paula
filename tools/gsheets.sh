#!/usr/bin/env bash
# Обращение к Google Таблицам через веб-приложение Apps Script.
#
#   bash tools/gsheets.sh ping
#   bash tools/gsheets.sh zapros.json          # запрос из файла
#   echo '{"action":"listSheets"}' | bash tools/gsheets.sh -
set -euo pipefail

KATALOG="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${GSHEETS_CONFIG:-$KATALOG/.gsheets.json}"

[ -f "$CONFIG" ] || { echo "Не найден файл настроек: $CONFIG" >&2; exit 1; }

URL="$(jq -r '.url'   "$CONFIG")"
TOKEN="$(jq -r '.token' "$CONFIG")"
[ -n "$URL" ] && [ "$URL" != "null" ]     || { echo "В настройках не заполнен url" >&2; exit 1; }
[ -n "$TOKEN" ] && [ "$TOKEN" != "null" ] || { echo "В настройках не заполнен token" >&2; exit 1; }

if [ "${1:-}" = "ping" ]; then
  curl -sS -L "$URL"
  echo
  exit 0
fi

ISTOCHNIK="${1:-}"
[ -n "$ISTOCHNIK" ] || { echo "Укажите файл запроса, '-' для stdin или 'ping'" >&2; exit 1; }

if [ "$ISTOCHNIK" = "-" ]; then ZAPROS="$(cat)"; else ZAPROS="$(cat "$ISTOCHNIK")"; fi

# Короткое имя таблицы из раздела tables -> ссылка.
ALIAS="$(printf '%s' "$ZAPROS" | jq -r '.table // empty')"
if [ -n "$ALIAS" ]; then
  SSYLKA="$(jq -r --arg a "$ALIAS" '.tables[$a] // empty' "$CONFIG")"
  [ -n "$SSYLKA" ] || { echo "Таблица '$ALIAS' не описана в разделе tables" >&2; exit 1; }
  ZAPROS="$(printf '%s' "$ZAPROS" | jq --arg s "$SSYLKA" 'del(.table) | .spreadsheetId = $s')"
fi

# Пароль подставляется здесь, чтобы не лежать в файлах запросов.
TELO="$(printf '%s' "$ZAPROS" | jq --arg t "$TOKEN" '. + {token: $t}')"

# Google периодически отвечает 404/500 на поток запросов — повторяем с паузой.
#
# Без -X POST намеренно: Apps Script отвечает на POST редиректом 302 на
# script.googleusercontent.com, и результат оттуда забирается уже методом GET.
# --data-binary сам включает POST для первого запроса, а curl при 302 корректно
# переключается на GET. Флаг -X POST это ломает: он навязывает POST и редиректу,
# на что Google отвечает 405 и HTML-страницей «Page Not Found».
for POPYTKA in 1 2 3 4; do
  if OTVET="$(curl -sS -L --fail-with-body \
       -H 'Content-Type: application/json; charset=utf-8' \
       --data-binary "$TELO" "$URL" 2>/dev/null)"; then
    printf '%s\n' "$OTVET"
    exit 0
  fi
  [ "$POPYTKA" -lt 4 ] && sleep $((2 * POPYTKA))
done

echo "Запрос не прошёл после 4 попыток" >&2
exit 1
