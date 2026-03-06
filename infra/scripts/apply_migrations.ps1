param(
  [string]$DatabaseUrl = "postgresql://trading:trading@localhost:5432/trading_analyst"
)

$ErrorActionPreference = "Stop"

Write-Host "Applying SQL migrations to $DatabaseUrl"
$migrationFiles = Get-ChildItem -Path "$PSScriptRoot/../../db/migrations" -Filter "*.sql" | Sort-Object Name

foreach ($file in $migrationFiles) {
  Write-Host "Running $($file.Name)"
  psql $DatabaseUrl -f $file.FullName
}

Write-Host "Migrations complete."
