from config import load_django
from datetime import date, timedelta
from collections import Counter
from constants.celery_constants import ForestTaskStatus
from constants.forest_constants import ForestTree
from database.models import ForestTask, Participant, Researcher, Study, SummaryStatisticDaily
from services.celery_forest import celery_run_forest

study = Study.objects.get(name="Sentinel Pilot")
admin = Researcher.objects.get(username="sentinel_admin")
start, end = date.today() - timedelta(days=13), date.today() - timedelta(days=1)
ForestTask.objects.filter(status=ForestTaskStatus.queued).delete()
tasks = []
for p in Participant.objects.filter(study=study, device_id__startswith="sim-"):
    trees = [ForestTree.jasmine] + ([ForestTree.willow] if p.os_type == "ANDROID" else [])
    for tree in trees:
        tasks.append(ForestTask.objects.create(participant=p, forest_tree=tree, data_date_start=start, data_date_end=end,
                                               status=ForestTaskStatus.queued, the_study=study, creator=admin))
tasks.append(ForestTask.objects.create(participant=None, forest_tree=ForestTree.sycamore, data_date_start=start, data_date_end=end,
                                       status=ForestTaskStatus.queued, the_study=study, creator=admin))
for t in tasks:
    celery_run_forest.an_function(t.id)
    t.refresh_from_db()
    print(t.forest_tree, t.participant.patient_id if t.participant else "study", t.status, (t.stacktrace or "")[-300:])
print(Counter(ForestTask.objects.values_list("status", flat=True)))
s = SummaryStatisticDaily.objects.filter(jasmine_home_duration__isnull=False).values_list("participant__patient_id", "date", "jasmine_home_duration", "jasmine_distance_traveled")[:8]
print(list(s))
