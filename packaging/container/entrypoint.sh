#!/usr/bin/env sh
# Bootstrap only missing safe defaults, then hand lifecycle signals to Gunicorn.
set -eu

data_root=${JOB_RADAR_DATA_DIR:-/var/lib/junior}
settings_path="$data_root/config/settings.yaml"

if [ ! -f "$settings_path" ]; then
    job-radar bootstrap-user-data --destination "$data_root"
fi

exec gunicorn \
    --bind "${JUNIOR_HOST:-0.0.0.0}:${JUNIOR_PORT:-8000}" \
    --workers 1 \
    --threads 4 \
    --timeout 120 \
    --access-logfile - \
    --error-logfile - \
    "job_radar.web_app:create_app()"
