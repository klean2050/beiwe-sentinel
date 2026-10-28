#!/usr/bin/env bash
# Rebuilds the local Sentinel demo from scratch: empty database and storage, Sentinel study,
# simulated phones, data processing and Forest. See README.md for one-time setup.
DEMO="$(cd "$(dirname "$0")" && pwd)"
B="${BACKEND_DIR:?set BACKEND_DIR to your beiwe-backend checkout}"
PY="${PYTHON:-$B/.venv/bin/python}"
MOTO="${MOTO_SERVER:-$(dirname "$PY")/moto_server}"

pkill -f "manage.py runserver 127.0.0.1:8080" || true
pkill -f "moto_server -H 127.0.0.1 -p 9000" || true
sleep 2
psql -h 127.0.0.1 -U beiwe -d postgres -qc "drop database if exists beiwe with (force);" -c "create database beiwe;"
rm -rf /tmp/forest
(nohup "$MOTO" -H 127.0.0.1 -p 9000 > "$DEMO/moto.log" 2>&1 &)
sleep 3
"$PY" -c "import boto3; boto3.client('s3', endpoint_url='http://127.0.0.1:9000', aws_access_key_id='demo', aws_secret_access_key='demo', region_name='us-east-1').create_bucket(Bucket='sentinel-demo')"

cd "$B" && . "$DEMO/env.sh"
"$PY" manage.py migrate -v 0
(nohup "$PY" manage.py runserver 127.0.0.1:8080 > "$DEMO/django.log" 2>&1 &)
PYTHONPATH=. "$PY" "$DEMO/seed.py" "$DEMO/sentinel_study.json" "$DEMO/participants.json"
PYTHONPATH=. "$PY" - "$DEMO/server_surveys.json" <<'PY'
import json, sys
from config import load_django  # noqa: F401
from database.models import Study
s = Study.objects.get(name="Sentinel Pilot")
json.dump({"surveys": [dict(object_id=x.object_id, name=x.name, survey_type=x.survey_type,
                            content=json.loads(x.content), timings=x.weekly_timings())
                       for x in s.surveys.filter(deleted=False)]}, open(sys.argv[1], "w"))
PY
sleep 4
"$PY" "$DEMO/phone_sim.py" "$DEMO/participants.json" "$DEMO/server_surveys.json"
PYTHONPATH=. "$PY" - <<'PY'
from config import load_django  # noqa: F401
from database.models import ChunkRegistry, FileToProcess, Participant
from libs.file_processing.file_processing_core import easy_run
for p in Participant.objects.filter(device_id__startswith="sim-"):
    easy_run(p)
print("files left to process:", FileToProcess.objects.count(), "| hourly chunks:", ChunkRegistry.objects.count())
PY
PYTHONPATH=. "$PY" "$DEMO/run_forest.py"
echo "Open http://localhost:8080 and log in as sentinel_admin / Sentinel-Demo-Admin-2026!"
