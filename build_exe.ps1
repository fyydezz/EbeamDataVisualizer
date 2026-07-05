$ErrorActionPreference = "Stop"

python -m pip install -r requirements.txt
python -m PyInstaller `
  --noconfirm `
  --clean `
  --windowed `
  --name EbeamDataVisualizer `
  --collect-all duckdb `
  --collect-all matplotlib `
  ui_app.py

Write-Host "Done. EXE path: $PWD\dist\EbeamDataVisualizer\EbeamDataVisualizer.exe"
