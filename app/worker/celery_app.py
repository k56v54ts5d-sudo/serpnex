from celery import Celery

from app.config import settings

celery_app = Celery(
    "serpnex",
    broker=settings.redis_url,
    backend=settings.redis_url,
    include=[],  # task modules registered here as sprints add them
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    result_expires=86400,  # 24 hours
)
