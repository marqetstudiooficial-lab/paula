# Обращение к Google Таблицам через веб-приложение Apps Script.
# Запускать с -ExecutionPolicy Bypass, иначе Windows не разрешит запуск.
#
#   powershell -ExecutionPolicy Bypass -File tools\gsheets.ps1 -Ping
#   powershell -ExecutionPolicy Bypass -File tools\gsheets.ps1 -Action listSheets
#   powershell -ExecutionPolicy Bypass -File tools\gsheets.ps1 -Action read -Sheet "Январь" -Range A1:D20
#   powershell -ExecutionPolicy Bypass -File tools\gsheets.ps1 -PayloadFile zapros.json

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

if (-not $ConfigPath) { $ConfigPath = Join-Path (Split-Path $PSScriptRoot -Parent) '.gsheets.json' }
if (-not (Test-Path $ConfigPath)) { throw "Не найден файл настроек: $ConfigPath" }

$cfg = Get-Content $ConfigPath -Raw -Encoding UTF8 | ConvertFrom-Json
if (-not $cfg.url)   { throw "В $ConfigPath не заполнено поле url" }
if (-not $cfg.token) { throw "В $ConfigPath не заполнено поле token" }

# Проверка связи: обычный GET, без пароля.
if ($Ping) {
    $r = Invoke-RestMethod -Uri $cfg.url -Method Get -TimeoutSec 60
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

# Короткое имя таблицы из раздела tables заменяем на ссылку.
if ($req.PSObject.Properties.Name -contains 'table' -and $req.table) {
    if (-not $cfg.tables) { throw "В запросе есть table='$($req.table)', но в настройках нет раздела tables" }
    $alias = $cfg.tables.PSObject.Properties | Where-Object { $_.Name -eq $req.table }
    if (-not $alias) {
        $known = ($cfg.tables.PSObject.Properties.Name) -join ', '
        throw "Таблица '$($req.table)' не описана. Известные: $known"
    }
    $req | Add-Member -NotePropertyName spreadsheetId -NotePropertyValue $alias.Value -Force
    $req.PSObject.Properties.Remove('table')
}

# Пароль подставляется здесь, чтобы не лежать в файлах запросов.
$req | Add-Member -NotePropertyName token -NotePropertyValue $cfg.token -Force

$body  = $req | ConvertTo-Json -Depth 20 -Compress
$bytes = [Text.Encoding]::UTF8.GetBytes($body)

# Google периодически отвечает 404 или 500 на поток запросов — это защита от
# нагрузки, а не ошибка запроса. Повторяем с нарастающей паузой.
$popytok = 4
for ($i = 1; $i -le $popytok; $i++) {
    try {
        $resp = Invoke-RestMethod -Uri $cfg.url -Method Post -Body $bytes `
            -ContentType 'application/json; charset=utf-8' -TimeoutSec 120
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
