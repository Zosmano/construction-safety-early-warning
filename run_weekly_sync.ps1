# Weekly programme sync for every active project (schedule with Task Scheduler, e.g. Sundays 22:00).
# Needs SSEW_DB and SSEW_SCHEDULE_SOURCES set for the account the task runs as.
Set-Location $PSScriptRoot
python -m service.schedule_sync --all
exit $LASTEXITCODE
