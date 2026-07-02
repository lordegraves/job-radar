$ErrorActionPreference = "Stop"

Set-Location "C:\dev\job-radar"

.\.venv\Scripts\Activate.ps1

python -m job_radar scan `
    --config config/target-companies.yaml `
    --settings config/local-gmail-settings.yaml `
    --scoring config/scoring.yaml `
    --report reports/target-scan.md `
    --email-preview reports/target-email-preview.txt `
    --send-email