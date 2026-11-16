from celery import shared_task

from .services import notify_service


@shared_task(ignore_result=True)
def send_push_task(notification_ids: list[str]) -> int:
    return notify_service.send_push(notification_ids)
