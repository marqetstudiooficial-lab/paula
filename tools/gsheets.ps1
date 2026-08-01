# Обращение к Google Таблицам через веб-приложение Apps Script.
# Запускать с -ExecutionPolicy Bypass, иначе Windows не разрешит запуск.
#
#   powershell -ExecutionPolicy Bypass -File tools\gsheets.ps1 -Ping
#   powershell -ExecutionPolicy Bypass -File tools\gsheets.ps1 -Action listSheets
#   powershell -ExecutionPolicy Bypass -File tools\gsheets.ps1 -Action read -Sheet "Январь" -Range A1:D20
#   powershell -ExecutionPolicy Bypass -File tools\gsheets.ps1 -PayloadFile zapros.json
#
# Адрес и пароль берутся из .gsheets.json либо из переменных окружения
# GSHEETS_URL и GSHEETS_TOKEN (переменные имеют приоритет).

param(
    [string]$Action,
    [string]$Table,
    [string]$SpreadsheetId,
    [string]$Sheet,
    [string]$Gid,
    [string]$Range,
    [string]$Cell,
    [string]$Value,
    [switch]$Raw,
    [string]$Payload,
    [string]$PayloadFile,
    [switch]$Ping,
    [string]$OutFile,
    [string]$ConfigPath
)

$ErrorActionPreference = 'Stop'

# PowerShell 5.1 по умолчанию пытается в TLS 1.0, Google такое не принимает.
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12

$koren = Split-Path $PSScriptRoot -Parent
if (-not $ConfigPath) { $ConfigPath = Join-Path $koren '.gsheets.json' }
$AliasPath = Join-Path $koren '.gsheets-tables.json'

# Адрес и пароль: сначала переменные окружения, потом файл настроек. Переменные
# нужны там, где файла нет и не может быть, — в облачных сессиях репозиторий
# клонируется заново, а .gsheets.json в git не хранится.
$Url   = $env:GSHEETS_URL
$Token = $env:GSHEETS_TOKEN

$cfg = $null
if (Test-Path $ConfigPath) {
    $cfg = Get-Content $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if (-not $Url)   { $Url   = $cfg.url }
    if (-not $Token) { $Token = $cfg.token }
}
elseif (-not $Url -or -not $Token) {
    throw "Нет ни переменных GSHEETS_URL/GSHEETS_TOKEN, ни файла настроек: $ConfigPath"
}

if (-not $Url)   { throw "Не задан url (GSHEETS_URL или поле url в $ConfigPath)" }
if (-not $Token) { throw "Не задан token (GSHEETS_TOKEN или поле token в $ConfigPath)" }

# Ссылки на таблицы не секрет, поэтому лежат в .gsheets-tables.json и хранятся
# в git; раздел tables из .gsheets.json их перекрывает при совпадении имени.
$tablicy = @{}
if (Test-Path $AliasPath) {
    $a = Get-Content $AliasPath -Raw -Encoding UTF8 | ConvertFrom-Json
    if ($a.tables) { $a.tables.PSObject.Properties | ForEach-Object { $tablicy[$_.Name] = $_.Value } }
}
if ($cfg -and $cfg.tables) {
    $cfg.tables.PSObject.Properties | ForEach-Object { $tablicy[$_.Name] = $_.Value }
}

# Проверка связи: обычный GET, без пароля.
if ($Ping) {
    $r = Invoke-RestMethod -Uri $Url -Method Get -TimeoutSec 60
    $r | ConvertTo-Json -Depth 20
    return
}

if ($PayloadFile) {
    if (-not (Test-Path $PayloadFile)) { throw "Файл запроса не найден: $PayloadFile" }
    $Payload = Get-Content $PayloadFile -Raw -Encoding UTF8
}
elseif (-not $Payload -and $Action) {
    $h = @{ action = $Action }
    if ($Table)         { $h.table         = $Table }
    if ($SpreadsheetId) { $h.spreadsheetId = $SpreadsheetId }
    if ($Sheet)         { $h.sheet         = $Sheet }
    if ($Gid)           { $h.gid           = $Gid }
    if ($Range)         { $h.range         = $Range }
    if ($Cell)          { $h.cell          = $Cell }
    if ($Raw)           { $h.raw           = $true }
    if ($PSBoundParameters.ContainsKey('Value')) { $h.value = $Value }
    $Payload = $h | ConvertTo-Json -Depth 5 -Compress
}

if (-not $Payload) { throw "Нужен -Action, -Payload, -PayloadFile или -Ping" }

$req = $Payload | ConvertFrom-Json

# Короткое имя таблицы заменяем на ссылку.
if ($req.PSObject.Properties.Name -contains 'table' -and $req.table) {
    if (-not $tablicy.ContainsKey($req.table)) {
        $known = if ($tablicy.Count) { ($tablicy.Keys | Sort-Object) -join ', ' } else { 'нет ни одной' }
        throw "Таблица '$($req.table)' не описана. Известные: $known"
    }
    $req | Add-Member -NotePropertyName spreadsheetId -NotePropertyValue $tablicy[$req.table] -Force
    $req.PSObject.Properties.Remove('table')
}

# Пароль подставляется здесь, чтобы не лежать в файлах запросов.
$req | Add-Member -NotePropertyName token -NotePropertyValue $Token -Force

$body  = $req | ConvertTo-Json -Depth 20 -Compress
$bytes = [Text.Encoding]::UTF8.GetBytes($body)

# Google периодически отвечает 404 или 500 на поток запросов — это защита от
# нагрузки, а не ошибка запроса. Повторяем с нарастающей паузой.
$popytok = 4
for ($i = 1; $i -le $popytok; $i++) {
    try {
        $resp = Invoke-RestMethod -Uri $Url -Method Post -Body $bytes `
            -ContentType 'application/json; charset=utf-8' -TimeoutSec 120
        # Изредка Google перебрасывает POST обратно на /exec, и приходит ответ doGet —
        # «пинг» с ok:true, не имеющий никакого отношения к запросу. Принять его за
        # результат опаснее всего при записи: выглядит как успех, а не сделано ничего.
        if ($resp.PSObject.Properties.Name -contains 'ping') {
            if ($i -eq $popytok) { throw "Google вернул ответ-пинг вместо результата запроса, $popytok попыток подряд" }
            Start-Sleep -Seconds (2 * $i)
            continue
        }
        break
    }
    catch {
        if ($i -eq $popytok) { throw "Запрос не прошёл после $popytok попыток: $($_.Exception.Message)" }
        Start-Sleep -Seconds (2 * $i)
    }
}

$out = $resp | ConvertTo-Json -Depth 20

if ($OutFile) {
    $out | Out-File -FilePath $OutFile -Encoding utf8
    Write-Output "Ответ сохранён: $OutFile"
    if ($resp.ok -ne $true) { Write-Output $out }
} else {
    Write-Output $out
}
