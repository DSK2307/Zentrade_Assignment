# reset_for_video.ps1
# ─────────────────────────────────────────────────────────
# Clears all generated outputs so you can run a fresh demo
# from scratch for recording.
#
# Run: .\reset_for_video.ps1
# ─────────────────────────────────────────────────────────

Write-Host ""
Write-Host "╔══════════════════════════════════════════╗" -ForegroundColor Cyan
Write-Host "║   Clara Pipeline – Reset for Video Demo   ║" -ForegroundColor Cyan
Write-Host "╚══════════════════════════════════════════╝" -ForegroundColor Cyan
Write-Host ""

# 1. Delete all generated account outputs
$accountsDir = "outputs\accounts"
if (Test-Path $accountsDir) {
    Remove-Item -Recurse -Force $accountsDir
    Write-Host "✅ Cleared outputs\accounts\" -ForegroundColor Green
}

# 2. Delete summary report
$summary = "outputs\summary_report.json"
if (Test-Path $summary) {
    Remove-Item -Force $summary
    Write-Host "✅ Cleared outputs\summary_report.json" -ForegroundColor Green
}

# 3. Clear the log file (keep the file, empty its contents)
$logFile = "logs\pipeline.log"
if (Test-Path $logFile) {
    Clear-Content $logFile
    Write-Host "✅ Cleared logs\pipeline.log" -ForegroundColor Green
}

# 4. Delete normalized transcript temp files
Get-ChildItem -Recurse -Filter "*_normalized.txt" | Remove-Item -Force
Write-Host "✅ Cleared all *_normalized.txt temp files" -ForegroundColor Green

# 5. Recreate empty directories
New-Item -ItemType Directory -Force -Path "outputs\accounts" | Out-Null
New-Item -ItemType Directory -Force -Path "logs" | Out-Null

Write-Host ""
Write-Host "🎬 Reset complete! Ready for fresh demo recording." -ForegroundColor Yellow
Write-Host ""
Write-Host "New demo transcripts available:" -ForegroundColor White
Write-Host "  📄 dataset\demo_calls\gm_pressure_washing_demo.txt" -ForegroundColor Gray
Write-Host "  📄 dataset\demo_calls\bens_electric_solutions_demo.txt" -ForegroundColor Gray
Write-Host "  📄 dataset\onboarding_calls\gm_pressure_washing_onboarding.txt" -ForegroundColor Gray
Write-Host ""
Write-Host "Start recording, then run: python scripts/batch_process.py --dataset_dir dataset/demo_calls --output_dir outputs/accounts" -ForegroundColor Cyan
Write-Host ""
