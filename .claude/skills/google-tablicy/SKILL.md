---
name: google-tablicy
description: Leer y editar Google Sheets directamente — valores, fórmulas, relleno de color, color de fuente, bordes, ancho de columnas, combinar celdas, listas desplegables, crear y duplicar hojas. Чтение и правка Google Таблиц напрямую. Usar cuando aparezcan: hoja de cálculo, Google Sheets, tabla, celda, rango, pinta, escribe en la tabla, informe, presupuesto, таблица, гугл-таблица, ячейка, лист, диапазон, покрась, впиши, отчёт, бюджет.
---

# Google Sheets (мост через Apps Script)

Штатный коннектор Google Drive умеет только читать. Правки идут через веб-приложение
Apps Script, установленное в аккаунте пользователя.

Вызов:

```
bash tools/gsheets.sh zapros.json          # Mac / Linux
powershell -ExecutionPolicy Bypass -File tools\gsheets.ps1 -PayloadFile zapros.json   # Windows
```

Проверка связи: `bash tools/gsheets.sh ping` → `{"ok":true,"ping":"скрипт работает","version":4}`

Адрес и пароль — в `.gsheets.json` в корне проекта (в git не коммитится).
Установка с нуля и починка, если сломалось — `reference/nastroyka.md`.
Полный список действий, примеры запросов и грабли — `reference/komandy.md`.
Код для Apps Script — `assets/gsheets-webapp.gs`.

## Если моста ещё нет

Нет `.gsheets.json` или `ping` не отвечает → открой `reference/nastroyka.md` и проведи
пользователя по шагам. Он делает это сам руками в браузере; файлы на диске создаёшь ты.

## Порядок работы

1. `listSheets` — узнать имена и gid листов. **Gid между сессиями не запоминать**,
   пользователь создаёт и удаляет листы.
2. Прочитать нужный кусок (`read`); если в деле цвета — `inspect` с `backgrounds`.
3. Показать пользователю «было → стало» до того, как править.
4. Внести правку, сохранив поле `before` из ответа — это единственный откат.
5. Перечитать диапазон и показать результат. `ok: true` = «запрос дошёл», а не «получилось».

## Правила

- Строки и людей искать по названию, а не по номеру строки: пользователь вставляет и
  удаляет строки прямо по ходу разговора.
- Оформление полем `before` не откатывается — перед большой переделкой цветов снять
  снимок через `inspect` с `backgrounds: true` и сохранить ответ.
- Кириллицу, испанские буквы и кавычки передавать **только через файл запроса**, не
  строкой в командной строке — оболочка их искажает.
- Одна запись блоком (`write`) лучше двадцати `setCell`: Google отвечает 404/500 на
  поток запросов.
- Большие ответы (весь лист, длинный `listSheets`) сразу класть в файл и разбирать
  оттуда, а не вываливать в разговор.
- Удаление листа необратимо и требует `"confirm": true` — не подставляй сам, спрашивай.

## Быстрая шпаргалка

Чтение: `listSheets` `read` `inspect` `condRules` `find`
Значения: `write` `setCell` `setFormulas` `append` `clear`
Оформление: `format` `copyFormat` `columnWidth` `rowHeight` `merge` `unmerge` `setNotes`
Списки: `setValidation` `setValidationMask` `clearValidation`
Листы: `addSheet` `duplicateSheet` `renameSheet` `deleteSheet` `hideSheet`

```json
{"action":"read","sheet":"Presupuesto","range":"A1:H40"}
{"action":"write","sheet":"Presupuesto","range":"B2","values":[["Publicidad",15000]]}
{"action":"format","sheet":"Informe","range":"A1:F1","background":"#4a86e8","fontColor":"#ffffff","bold":true,"align":"center"}
```

`range` в `write` — левый верхний угол, размер берётся из `values`.

## Знания о таблицах пользователя

Сюда дописывай то, что выясняется в работе: устройство конкретных таблиц, что означают
цвета, какие правила повторяются. Это экономит больше, чем список команд.

_(пока пусто)_
