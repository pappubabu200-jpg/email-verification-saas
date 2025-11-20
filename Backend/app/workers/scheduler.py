from backend.app.celery_app import celery_app
from backend.app.workers.job_watcher import job_watcher


@celery_app.on_after_configure.connect
def setup_periodic_tasks(sender, **kwargs):
    # Run job watcher every 15 seconds
    sender.add_periodic_task(15.0, run_job_watcher.s(), name="job watcher")


@celery_app.task
def run_job_watcher():
    job_watcher()
    return "ok"
