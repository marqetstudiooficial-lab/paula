/**
 * Мост между ассистентом и Google Таблицами. Версия 4.
 * Устанавливается по инструкции: .claude/skills/google-tablicy/reference/nastroyka.md
 * Живёт внутри Google, на компьютере не запускается.
 */

// ── ЕДИНСТВЕННОЕ, ЧТО НУЖНО ПОМЕНЯТЬ ──────────────────────────────
// Меняйте пароль ТОЛЬКО в строке ниже. Не «заменить всё по файлу».
var TOKEN = 'ВСТАВЬТЕ_СЮДА_ПРИДУМАННЫЙ_ПАРОЛЬ';

// Таблица, которая берётся, если в запросе не указана другая.
// Вставьте сюда айди своей основной таблицы (из ссылки, между /d/ и /edit)
// или оставьте пустым и всегда указывайте таблицу в запросе.
var DEFAULT_SPREADSHEET = '';
// ──────────────────────────────────────────────────────────────────


function doGet() {
  return json({ ok: true, ping: 'скрипт работает', version: 4 });
}


function doPost(e) {
  try {
    if (!e || !e.postData) return json({ ok: false, error: 'пустой запрос' });

    var req = JSON.parse(e.postData.contents);

    // Проверка «пароль вписан». Намеренно ищет кусок заглушки, а не всю строку:
    // если заменить пароль по всему файлу, эта строка не пострадает и не начнёт
    // сравнивать TOKEN сам с собой.
    if (TOKEN.indexOf('ВСТАВЬТЕ') === 0 || TOKEN.length < 12) {
      return json({ ok: false, error: 'в скрипте не заменён TOKEN (или он короче 12 символов)' });
    }
    if (req.token !== TOKEN) return json({ ok: false, error: 'неверный пароль' });

    var ss = SpreadsheetApp.openById(resolveId(req.spreadsheetId || DEFAULT_SPREADSHEET));

    switch (req.action) {

      // ═══ ЧТЕНИЕ ═══════════════════════════════════════════════════

      case 'listSheets':
        return json({
          ok: true, title: ss.getName(),
          sheets: ss.getSheets().map(function (s) {
            return {
              name: s.getName(), gid: s.getSheetId(),
              rows: s.getLastRow(), cols: s.getLastColumn(),
              hidden: s.isSheetHidden(), index: s.getIndex()
            };
          })
        });

      // Значения. raw:true — сырые (даты числами), иначе как видно на экране.
      case 'read': {
        var sh = pickSheet(ss, req);
        var rg = req.range ? sh.getRange(req.range) : sh.getDataRange();
        return json({
          ok: true, sheet: sh.getName(), range: rg.getA1Notation(),
          values: req.raw ? rg.getValues() : rg.getDisplayValues()
        });
      }

      // Подробный осмотр диапазона. Что вернуть — включается флагами,
      // иначе ответ распухает: 30x30 фонов это уже 900 строк.
      case 'inspect': {
        var sh = pickSheet(ss, req);
        var rg = req.range ? sh.getRange(req.range) : sh.getDataRange();
        var out = { ok: true, sheet: sh.getName(), range: rg.getA1Notation() };

        if (req.values !== false)  out.values      = rg.getDisplayValues();
        if (req.formulas)          out.formulas    = rg.getFormulas();
        if (req.backgrounds)       out.backgrounds = rg.getBackgrounds();
        if (req.fontColors)        out.fontColors  = rg.getFontColors();
        if (req.fontWeights)       out.fontWeights = rg.getFontWeights();
        if (req.numberFormats)     out.numberFormats = rg.getNumberFormats();
        if (req.merges) {
          out.merges = rg.getMergedRanges().map(function (m) { return m.getA1Notation(); });
        }
        if (req.validations) {
          out.validations = rg.getDataValidations().map(function (row) {
            return row.map(function (dv) {
              if (!dv) return null;
              try {
                var v = dv.getCriteriaValues();
                if (v && v[0] && v[0].getA1Notation) return 'диапазон:' + v[0].getA1Notation();
                if (v && v[0] && v[0].join)          return v[0].join(' | ');
                return String(dv.getCriteriaType());
              } catch (x) { return 'нечитаемо'; }
            });
          });
        }
        return json(out);
      }

      // Правила условного форматирования листа — чтобы понять, красится ли
      // что-то автоматически, или все цвета проставлены руками.
      case 'condRules': {
        var sh = pickSheet(ss, req);
        return json({
          ok: true, sheet: sh.getName(),
          rules: sh.getConditionalFormatRules().map(function (rule) {
            var r = { ranges: rule.getRanges().map(function (x) { return x.getA1Notation(); }) };
            try {
              var b = rule.getBooleanCondition();
              if (b) {
                r.type = String(b.getCriteriaType());
                r.values = b.getCriteriaValues().map(String);
                r.background = b.getBackground();
              } else {
                r.gradient = true;
              }
            } catch (x) { r.note = 'правило не разобрано'; }
            return r;
          })
        });
      }

      case 'find': {
        var sh = pickSheet(ss, req);
        var needle = String(req.value == null ? '' : req.value).toLowerCase();
        var data = sh.getDataRange().getDisplayValues();
        var hits = [];
        for (var r = 0; r < data.length; r++) {
          for (var c = 0; c < data[r].length; c++) {
            if (String(data[r][c]).toLowerCase().indexOf(needle) !== -1) {
              hits.push({ cell: a1(r + 1, c + 1), value: data[r][c] });
              if (hits.length >= 200) { r = data.length; break; }
            }
          }
        }
        return json({ ok: true, sheet: sh.getName(), hits: hits });
      }

      // ═══ ЗАПИСЬ ЗНАЧЕНИЙ ══════════════════════════════════════════

      // values — массив строк: [["a","b"],["c","d"]].
      // range задаёт левый верхний угол, размер берётся из values.
      // В ответе before — что было до правки, для отката.
      case 'write': {
        var sh = pickSheet(ss, req);
        var v = req.values;
        if (!v || !v.length || !v[0].length) {
          return json({ ok: false, error: 'values пустые или не двумерный массив' });
        }
        var tg = blockAt(sh, req.range || 'A1', v.length, v[0].length);
        var before = tg.getDisplayValues();
        tg.setValues(v);
        SpreadsheetApp.flush();
        return json({
          ok: true, sheet: sh.getName(), range: tg.getA1Notation(),
          written: v.length * v[0].length, before: before
        });
      }

      // Формулы: [["=SUM(A1:A9)",""]]. Пустая строка — ячейку не трогаем.
      case 'setFormulas': {
        var sh = pickSheet(ss, req);
        var f = req.formulas;
        if (!f || !f.length) return json({ ok: false, error: 'нет formulas' });
        var tg = blockAt(sh, req.range || 'A1', f.length, f[0].length);
        var before = tg.getFormulas();
        tg.setFormulas(f);
        SpreadsheetApp.flush();
        return json({ ok: true, sheet: sh.getName(), range: tg.getA1Notation(), before: before });
      }

      case 'setCell': {
        var sh = pickSheet(ss, req);
        var c = sh.getRange(req.cell);
        var was = c.getDisplayValue();
        c.setValue(req.value);
        SpreadsheetApp.flush();
        return json({
          ok: true, sheet: sh.getName(), cell: c.getA1Notation(),
          before: was, after: c.getDisplayValue()
        });
      }

      case 'append': {
        var sh = pickSheet(ss, req);
        var rows = req.values || [];
        rows.forEach(function (r) { sh.appendRow(r); });
        SpreadsheetApp.flush();
        return json({ ok: true, sheet: sh.getName(), appended: rows.length });
      }

      // clearWhat: 'content' (по умолчанию) | 'format' | 'all'
      case 'clear': {
        var sh = pickSheet(ss, req);
        var rg = sh.getRange(req.range);
        var before = rg.getDisplayValues();
        var what = req.clearWhat || 'content';
        if (what === 'all')         rg.clear();
        else if (what === 'format') rg.clearFormat();
        else                        rg.clearContent();
        SpreadsheetApp.flush();
        return json({ ok: true, sheet: sh.getName(), range: rg.getA1Notation(), cleared: what, before: before });
      }

      // ═══ ОФОРМЛЕНИЕ ═══════════════════════════════════════════════

      // Всё сразу для одного диапазона. Любое поле можно опустить.
      // backgrounds (мн. ч.) — своя заливка для каждой ячейки: [["#fff","#eee"]].
      case 'format': {
        var sh = pickSheet(ss, req);
        var rg = sh.getRange(req.range);

        if (req.backgrounds)              rg.setBackgrounds(req.backgrounds);
        else if (req.background)          rg.setBackground(req.background === 'none' ? null : req.background);

        if (req.fontColors)               rg.setFontColors(req.fontColors);
        else if (req.fontColor)           rg.setFontColor(req.fontColor);

        if (req.fontWeights)              rg.setFontWeights(req.fontWeights);
        else if (req.bold !== undefined)  rg.setFontWeight(req.bold ? 'bold' : 'normal');
        if (req.italic !== undefined)     rg.setFontStyle(req.italic ? 'italic' : 'normal');
        if (req.fontSize)                 rg.setFontSize(req.fontSize);
        if (req.fontFamily)               rg.setFontFamily(req.fontFamily);
        if (req.align)                    rg.setHorizontalAlignment(req.align);
        if (req.valign)                   rg.setVerticalAlignment(req.valign);
        if (req.numberFormat)             rg.setNumberFormat(req.numberFormat);
        if (req.wrap !== undefined)       rg.setWrap(!!req.wrap);

        if (req.border) {
          var b = req.border;
          var style = SpreadsheetApp.BorderStyle[b.style || 'SOLID'];
          if (!style) return json({ ok: false, error: 'неизвестный стиль границы: ' + b.style });
          // all:true — рамка снаружи и сетка внутри
          var t = b.all ? true : nz(b.top),   l = b.all ? true : nz(b.left);
          var d = b.all ? true : nz(b.bottom), r = b.all ? true : nz(b.right);
          var vv = b.all ? true : nz(b.vertical), hh = b.all ? true : nz(b.horizontal);
          rg.setBorder(t, l, d, r, vv, hh, b.color || '#000000', style);
        }

        SpreadsheetApp.flush();
        return json({ ok: true, sheet: sh.getName(), range: rg.getA1Notation() });
      }

      // Скопировать ОФОРМЛЕНИЕ (цвета, границы, шрифты) из одного места в другое.
      // Значения при этом не трогаются. Источник может быть с другого листа.
      case 'copyFormat': {
        var src = req.fromGid !== undefined || req.fromSheet
          ? pickSheet(ss, { gid: req.fromGid, sheet: req.fromSheet })
          : pickSheet(ss, req);
        var dst = pickSheet(ss, req);
        var sr = src.getRange(req.from);
        var dr = dst.getRange(req.to);
        sr.copyTo(dr, SpreadsheetApp.CopyPasteType.PASTE_FORMAT, false);
        SpreadsheetApp.flush();
        return json({
          ok: true, from: src.getName() + '!' + sr.getA1Notation(),
          to: dst.getName() + '!' + dr.getA1Notation()
        });
      }

      case 'columnWidth': {
        var sh = pickSheet(ss, req);
        sh.setColumnWidths(req.column, req.count || 1, req.width);
        return json({ ok: true, sheet: sh.getName() });
      }

      case 'rowHeight': {
        var sh = pickSheet(ss, req);
        sh.setRowHeights(req.row, req.count || 1, req.height);
        return json({ ok: true, sheet: sh.getName() });
      }

      // ═══ ПРОВЕРКА ДАННЫХ (выпадающие списки) ══════════════════════

      case 'clearValidation': {
        var sh = pickSheet(ss, req);
        var rg = sh.getRange(req.range);
        rg.clearDataValidations();
        SpreadsheetApp.flush();
        return json({ ok: true, sheet: sh.getName(), range: rg.getA1Notation() });
      }

      // Либо list: ["Иванов","Петров"], либо fromRange: "AM3:AM120".
      case 'setValidation': {
        var sh = pickSheet(ss, req);
        var rg = sh.getRange(req.range);
        var b = SpreadsheetApp.newDataValidation();
        if (req.fromRange) {
          var src = (req.fromGid !== undefined || req.fromSheet)
            ? pickSheet(ss, { gid: req.fromGid, sheet: req.fromSheet })
            : sh;
          b = b.requireValueInRange(src.getRange(req.fromRange), req.dropdown !== false);
        } else if (req.list && req.list.length) {
          b = b.requireValueInList(req.list, req.dropdown !== false);
        } else {
          return json({ ok: false, error: 'нужен list или fromRange' });
        }
        // allowInvalid:true — список показывается, но чужое значение не блокируется
        b = b.setAllowInvalid(req.allowInvalid === true);
        if (req.help) b = b.setHelpText(req.help);
        rg.setDataValidation(b.build());
        SpreadsheetApp.flush();
        return json({ ok: true, sheet: sh.getName(), range: rg.getA1Notation() });
      }

      // Списки по маске: true — список, false — ячейка без выпадашки.
      case 'setValidationMask': {
        var sh = pickSheet(ss, req);
        var rg = sh.getRange(req.range);
        var mask = req.mask;
        if (!mask || !mask.length) return json({ ok: false, error: 'нет mask' });
        if (mask.length !== rg.getNumRows() || mask[0].length !== rg.getNumColumns()) {
          return json({ ok: false, error: 'размер mask ' + mask.length + 'x' + mask[0].length +
                        ' не совпадает с диапазоном ' + rg.getNumRows() + 'x' + rg.getNumColumns() });
        }
        var b = SpreadsheetApp.newDataValidation();
        if (req.fromRange) {
          var src2 = (req.fromGid !== undefined || req.fromSheet)
            ? pickSheet(ss, { gid: req.fromGid, sheet: req.fromSheet }) : sh;
          b = b.requireValueInRange(src2.getRange(req.fromRange), req.dropdown !== false);
        } else if (req.list && req.list.length) {
          b = b.requireValueInList(req.list, req.dropdown !== false);
        } else {
          return json({ ok: false, error: 'нужен list или fromRange' });
        }
        var pravilo = b.setAllowInvalid(req.allowInvalid === true).build();

        var vse = [], vklyucheno = 0;
        for (var r2 = 0; r2 < mask.length; r2++) {
          var stroka = [];
          for (var c2 = 0; c2 < mask[r2].length; c2++) {
            if (mask[r2][c2]) { stroka.push(pravilo); vklyucheno++; }
            else              { stroka.push(null); }
          }
          vse.push(stroka);
        }
        rg.setDataValidations(vse);
        SpreadsheetApp.flush();
        return json({ ok: true, sheet: sh.getName(), range: rg.getA1Notation(), сСписком: vklyucheno });
      }

      // Примечания к ячейкам (всплывающие заметки в углу).
      case 'setNotes': {
        var sh = pickSheet(ss, req);
        var n = req.notes;
        if (!n || !n.length) return json({ ok: false, error: 'нет notes' });
        var tg = blockAt(sh, req.range || 'A1', n.length, n[0].length);
        tg.setNotes(n);
        SpreadsheetApp.flush();
        return json({ ok: true, sheet: sh.getName(), range: tg.getA1Notation() });
      }

      // ═══ ОБЪЕДИНЕНИЕ ЯЧЕЕК ════════════════════════════════════════

      // how: 'all' (по умолчанию) | 'across' (по строкам) | 'vertically'
      case 'merge': {
        var sh = pickSheet(ss, req);
        var rg = sh.getRange(req.range);
        if (req.how === 'across')          rg.mergeAcross();
        else if (req.how === 'vertically') rg.mergeVertically();
        else                               rg.merge();
        SpreadsheetApp.flush();
        return json({ ok: true, sheet: sh.getName(), range: rg.getA1Notation() });
      }

      case 'unmerge': {
        var sh = pickSheet(ss, req);
        var rg = sh.getRange(req.range);
        var was = rg.getMergedRanges().map(function (m) { return m.getA1Notation(); });
        rg.breakApart();
        SpreadsheetApp.flush();
        return json({ ok: true, sheet: sh.getName(), range: rg.getA1Notation(), разъединено: was });
      }

      // ═══ ЛИСТЫ ════════════════════════════════════════════════════

      case 'addSheet': {
        if (ss.getSheetByName(req.name)) {
          return json({ ok: false, error: 'лист "' + req.name + '" уже существует' });
        }
        var s = req.index !== undefined ? ss.insertSheet(req.name, req.index) : ss.insertSheet(req.name);
        if (req.rows)  s.insertRows(1, req.rows);
        return json({ ok: true, name: s.getName(), gid: s.getSheetId(), index: s.getIndex() });
      }

      // Копия листа со всем оформлением и формулами.
      case 'duplicateSheet': {
        var src = pickSheet(ss, req);
        if (req.name && ss.getSheetByName(req.name)) {
          return json({ ok: false, error: 'лист "' + req.name + '" уже существует' });
        }
        var copy = src.copyTo(ss);
        if (req.name) copy.setName(req.name);
        if (req.index !== undefined) {
          ss.setActiveSheet(copy);
          ss.moveActiveSheet(req.index);
        }
        return json({
          ok: true, from: src.getName(),
          name: copy.getName(), gid: copy.getSheetId(), index: copy.getIndex()
        });
      }

      case 'renameSheet': {
        var sh = pickSheet(ss, req);
        var old = sh.getName();
        sh.setName(req.name);
        return json({ ok: true, before: old, name: sh.getName(), gid: sh.getSheetId() });
      }

      // Удаление необратимо, поэтому требуется явное confirm:true.
      case 'deleteSheet': {
        var sh = pickSheet(ss, req);
        if (req.confirm !== true) {
          return json({ ok: false, error: 'удаление требует "confirm": true. Лист: ' + sh.getName() });
        }
        var nm = sh.getName(), gd = sh.getSheetId();
        ss.deleteSheet(sh);
        return json({ ok: true, удалён: nm, gid: gd });
      }

      case 'hideSheet': {
        var sh = pickSheet(ss, req);
        if (req.show) sh.showSheet(); else sh.hideSheet();
        return json({ ok: true, sheet: sh.getName(), hidden: sh.isSheetHidden() });
      }

      default:
        return json({ ok: false, error: 'неизвестное действие: ' + req.action });
    }

  } catch (err) {
    return json({ ok: false, error: String(err && err.message ? err.message : err) });
  }
}


// ── вспомогательное ───────────────────────────────────────────────

/** Полная ссылка на таблицу или голый идентификатор -> идентификатор. */
function resolveId(s) {
  if (!s) throw new Error('не указана таблица: передайте ссылку в spreadsheetId');
  s = String(s).trim();
  var m = s.match(/\/spreadsheets\/d\/([a-zA-Z0-9_-]+)/);
  return m ? m[1] : s;
}

/** Выбор листа: по gid (номер из ссылки) или по имени. Иначе — первый. */
function pickSheet(ss, req) {
  if (req.gid !== undefined && req.gid !== null && req.gid !== '') {
    var want = String(req.gid), all = ss.getSheets();
    for (var i = 0; i < all.length; i++) {
      if (String(all[i].getSheetId()) === want) return all[i];
    }
    throw new Error('лист с gid=' + req.gid + ' не найден');
  }
  if (req.sheet) {
    var s = ss.getSheetByName(req.sheet);
    if (!s) throw new Error('лист "' + req.sheet + '" не найден');
    return s;
  }
  return ss.getSheets()[0];
}

/** Блок нужного размера с началом в левом верхнем углу указанного диапазона. */
function blockAt(sheet, a1ref, rows, cols) {
  var anchor = sheet.getRange(a1ref);
  return sheet.getRange(anchor.getRow(), anchor.getColumn(), rows, cols);
}

/** undefined -> null: setBorder понимает null как «не трогать эту грань». */
function nz(v) { return v === undefined ? null : v; }

/** Номер строки и столбца -> адрес вида "B7". */
function a1(row, col) {
  var letters = '';
  while (col > 0) {
    var rem = (col - 1) % 26;
    letters = String.fromCharCode(65 + rem) + letters;
    col = Math.floor((col - 1) / 26);
  }
  return letters + row;
}

function json(obj) {
  return ContentService
    .createTextOutput(JSON.stringify(obj))
    .setMimeType(ContentService.MimeType.JSON);
}
