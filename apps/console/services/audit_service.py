from apps.core.http import client_ip

from ..models import AuditLog


def record(request, *, action: str, target_type: str, target_id, target_label: str = '', changes=None) -> AuditLog:
    return AuditLog.objects.create(
        actor=request.user if request.user.is_authenticated else None,
        action=action,
        target_type=target_type,
        target_id=str(target_id),
        target_label=target_label[:255],
        changes=changes or {},
        ip_address=client_ip(request),
    )
