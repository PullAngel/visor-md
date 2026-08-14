# Compila dist\VisorMD\ y el zip portable dist\VisorMD-portable.zip
#   powershell -ExecutionPolicy Bypass -File build\build.ps1
# Sin acentos a proposito: PowerShell 5.1 lee los .ps1 como ANSI.

$ErrorActionPreference = "Stop"
$root = Split-Path -Parent $PSScriptRoot
Set-Location $root

# Una instancia abierta bloquea los archivos y PyInstaller deja la version
# vieja en dist sin avisar.
$corriendo = @(Get-Process VisorMD -ErrorAction SilentlyContinue)
if ($corriendo.Count -gt 0) {
  Write-Host "Cerrando $($corriendo.Count) instancia(s) de VisorMD..."
  $corriendo | Stop-Process -Force
  Start-Sleep -Seconds 2
}
$inicio = Get-Date

Write-Host "== Dependencias =="
python -m pip install --quiet --upgrade pywebview pyinstaller pillow

Write-Host "== Icono =="
python build\make_icon.py

Write-Host "== PyInstaller =="
# --onedir en vez de --onefile: el modo de un solo archivo vuelve a extraer
# 14 MB en cada arranque y duplica el tiempo de apertura.
python -m PyInstaller --noconfirm --clean --onedir --windowed `
  --name VisorMD `
  --icon (Join-Path $root "assets\visormd.ico") `
  --add-data "$(Join-Path $root 'src\web');web" `
  --paths (Join-Path $root "src") `
  --hidden-import webview.platforms.edgechromium `
  --collect-all clr_loader `
  --collect-all pythonnet `
  --exclude-module tkinter `
  --exclude-module PIL `
  --exclude-module pygame `
  --distpath (Join-Path $root "dist") `
  --workpath (Join-Path $root "build\pyi-work") `
  --specpath (Join-Path $root "build") `
  (Join-Path $root "src\main.py")

$exe = Join-Path $root "dist\VisorMD\VisorMD.exe"
if (-not (Test-Path $exe)) { throw "No se genero $exe" }
if ((Get-Item $exe).LastWriteTime -lt $inicio) {
  throw "dist\VisorMD quedo con la version vieja: los archivos estaban bloqueados."
}

Write-Host "== Zip portable =="
$zip = Join-Path $root "dist\VisorMD-portable.zip"
if (Test-Path $zip) { Remove-Item $zip }
Compress-Archive -Path (Join-Path $root "dist\VisorMD\*") -DestinationPath $zip

$mb = (Get-ChildItem (Join-Path $root "dist\VisorMD") -Recurse -File | Measure-Object Length -Sum).Sum / 1MB
"{0}  (carpeta {1:N1} MB, zip {2:N1} MB)" -f $exe, $mb, ((Get-Item $zip).Length / 1MB)
Write-Host "Listo. Ejecutalo y usa el menu (...) -> Instalar en este equipo."
