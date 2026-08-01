#!/usr/bin/env bash
# Обращение к Google Таблицам через веб-приложение Apps Script.
#
#   bash tools/gsheets.sh ping
#   bash tools/gsheets.sh zapros.json          # запрос из файла
#   echo '{"action":"listSheets"}' | bash tools/gsheets.sh -
set -euo pipefail

KATALOG="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
CONFIG="${GSHEETS_CONFIG:-$KATALOG/.gsheets.json}"
ALIASY="$KATALOG/.gsheets-tables.json"

# Адрес и пароль: сначала переменные окружения, потом файл настроек. Переменные
# нужны там, где файла нет и не может быть, — в облачных сессиях репозиторий
# клонируется заново, а .gsheets.json в git не хранится.
URL="${GSHEETS_URL:-}"
TOKEN="${GSHEETS_TOKEN:-}"

if [ -z "$URL" ] || [ -z "$TOKEN" ]; then
  if [ -f "$CONFIG" ]; then
    [ -n "$URL" ]   || URL="$(jq -r '.url   // empty' "$CONFIG")"
    [ -n "$TOKEN" ] || TOKEN="$(jq -r '.token // empty' "$CONFIG")"
  else
    echo "Нет ни переменных GSHEETS_URL/GSHEETS_TOKEN, ни файла настроек: $CONFIG" >&2
    exit 1
  fi
fi

[ -n "$URL" ]   || { echo "Не задан url (GSHEETS_URL или поле url в $CONFIG)" >&2; exit 1; }
[ -n "$TOKEN" ] || { echo "Не задан token (GSHEETS_TOKEN или поле token в $CONFIG)" >&2; exit 1; }

if [ "${1:-}" = "ping" ]; then
  curl -sS -L "$URL"
  echo
  exit 0
fi

ISTOCHNIK="${1:-}"
[ -n "$ISTOCHNIK" ] || { echo "Укажите файл запроса, '-' для stdin или 'ping'" >&2; exit 1; }

if [ "$ISTOCHNIK" = "-" ]; then ZAPROS="$(cat)"; else ZAPROS="$(cat "$ISTOCHNIK")"; fi

# Короткое имя таблицы -> ссылка. Ссылки на таблицы не секрет, поэтому они лежат
# в .gsheets-tables.json и хранятся в git; раздел tables из .gsheets.json их
# перекрывает, если там то же имя.
ALIAS="$(printf '%s' "$ZAPROS" | jq -r '.table // empty')"
if [ -n "$ALIAS" ]; then
  TABLICY='{}'
  [ -f "$ALIASY" ] && TABLICY="$(jq -c '.tables // {}' "$ALIASY")"
  [ -f "$CONFIG" ] && TABLICY="$(jq -c -n --argjson a "$TABLICY" \
      --argjson b "$(jq -c '.tables // {}' "$CONFIG")" '$a + $b')"
  SSYLKA="$(printf '%s' "$TABLICY" | jq -r --arg a "$ALIAS" '.[$a] // empty')"
  if [ -z "$SSYLKA" ]; then
    IZVESTNY="$(printf '%s' "$TABLICY" | jq -r 'keys | join(", ")')"
    echo "Таблица '$ALIAS' не описана. Известные: ${IZVESTNY:-нет ни одной}" >&2
    exit 1
  fi
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
    # Изредка Google перебрасывает POST обратно на /exec, и приходит ответ doGet —
    # «пинг» с ok:true, не имеющий никакого отношения к запросу. Принять его за
    # результат опаснее всего при записи: выглядит как успех, а не сделано ничего.
    if printf '%s' "$OTVET" | jq -e 'type == "object" and has("ping")' >/dev/null 2>&1; then
      if [ "$POPYTKA" -lt 4 ]; then sleep $((2 * POPYTKA)); continue; fi
      echo "Google вернул ответ-пинг вместо результата запроса, 4 попытки подряд" >&2
      exit 1
    fi
    printf '%s\n' "$OTVET"
    exit 0
  fi
  [ "$POPYTKA" -lt 4 ] && sleep $((2 * POPYTKA))
done

echo "Запрос не прошёл после 4 попыток" >&2
exit 1
