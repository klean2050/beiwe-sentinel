""" Creates the Sentinel demo study inside a local beiwe-backend, using the backend's own import and
participant-creation code paths. Run from the beiwe-backend root with the demo environment loaded. """
import json
import secrets
import sys
from datetime import date, timedelta

from config import load_django  # noqa: F401  (sets up django)

from database.models import (Intervention, InterventionDate, Participant, ParticipantFieldValue,
    Researcher, Study, StudyField, StudyRelation)
from constants.user_constants import ResearcherRole
from libs.endpoint_helpers.copy_study_helpers import copy_study_from_json
from libs.rsa import create_participant_key_pair
from libs.s3 import s3_upload
from libs.schedules import repopulate_all_survey_scheduled_events

study_json_path, out_path = sys.argv[1], sys.argv[2]
cfg = json.load(open(study_json_path))

ADMIN_USER, ADMIN_PW = "sentinel_admin", "Sentinel-Demo-Admin-2026!"
RA_USER, RA_PW = "sentinel_ra", "Sentinel-RA-2026!"

admin = Researcher.objects.filter(username=ADMIN_USER).first() or Researcher.create_with_password(ADMIN_USER, ADMIN_PW)
admin.update(password_force_reset=False, site_admin=True)
ra = Researcher.objects.filter(username=RA_USER).first() or Researcher.create_with_password(RA_USER, RA_PW)
ra.update(password_force_reset=False)

study = Study.objects.filter(name="Sentinel Pilot").first()
if study is None:
    study = Study.create_with_object_id(
        name="Sentinel Pilot", encryption_key=secrets.token_urlsafe(24)[:32], forest_enabled=True,
    )
    study.update(timezone_name="America/Los_Angeles")
    valid = {f.name for f in study.device_settings._meta.fields}
    device_settings = {k: v for k, v in cfg["device_settings"].items() if k in valid}
    skipped = sorted(set(cfg["device_settings"]) - valid)
    if skipped:
        print("device settings not in this backend version:", skipped)
    copy_study_from_json(study, device_settings, cfg["surveys"], cfg["interventions"])

for r, role in ((admin, ResearcherRole.study_admin), (ra, ResearcherRole.researcher)):
    StudyRelation.objects.get_or_create(study=study, researcher=r, defaults={"relationship": role})

site_field, _ = StudyField.objects.get_or_create(study=study, field_name="Site")
cohort_field, _ = StudyField.objects.get_or_create(study=study, field_name="Cohort")
baseline = Intervention.objects.get(study=study, name="Baseline visit")

# Six example participants: four will get simulated phones, two stay unregistered.
plan = [
    ("ios", "USC Keck", "A", 13), ("android", "USC Keck", "A", 12), ("ios", "USC Keck", "B", 10),
    ("android", "Community clinic", "B", 9), (None, "Community clinic", "A", 3), (None, "USC Keck", "B", 1),
]
out = []
if not study.participants.exists():
    for os_name, site, cohort, days_ago in plan:
        patient_id, password = Participant.create_with_password(study_id=study.id)
        p = Participant.objects.get(patient_id=patient_id)
        s3_upload(patient_id, b"", study.object_id)
        create_participant_key_pair(patient_id, study.object_id)
        InterventionDate.objects.create(participant=p, intervention=baseline, date=date.today() - timedelta(days=days_ago))
        ParticipantFieldValue.objects.create(participant=p, field=site_field, value=site)
        ParticipantFieldValue.objects.create(participant=p, field=cohort_field, value=cohort)
        repopulate_all_survey_scheduled_events(study, p)
        out.append({"patient_id": patient_id, "password": password, "os": os_name, "days_ago": days_ago})
    json.dump({"study_id": study.id, "study_object_id": study.object_id, "participants": out}, open(out_path, "w"), indent=1)

print("study", study.id, study.object_id, "surveys", study.surveys.count(), "participants", study.participants.count())
