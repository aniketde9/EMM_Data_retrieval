from celery import Celery

from app.config import settings


celery_app = Celery(
    "emm_pipeline",
    broker=settings.REDIS_URL,
    backend=settings.REDIS_URL,
)

celery_app.conf.update(
    task_serializer="json",
    result_serializer="json",
    accept_content=["json"],
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_time_limit=1200,
    task_soft_time_limit=1100,
)

celery_app.autodiscover_tasks(["app.worker"])
