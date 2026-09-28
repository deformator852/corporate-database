from celery import Celery

from extensions import task_modules
from settings import rabbitmq_url

celery = Celery(
    "corporate",
    broker=rabbitmq_url(),
    backend="rpc://",
    include=["tasks.document", *task_modules()],
)
celery.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    task_track_started=True,
    task_acks_late=True,
    task_reject_on_worker_lost=True,
    worker_concurrency=1,
    worker_prefetch_multiplier=1,
)
