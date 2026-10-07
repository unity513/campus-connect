"""Cross-cutting services: audit logging, notifications, analytics."""
from django.core.mail import send_mail
from django.conf import settings

from .models import (
    AnalyticsEvent, AuditLog, Notification, NotificationTemplate, StoreSetting,
)


def audit(user, action, obj=None, **metadata):
    """Record an administrative action."""
    object_type = object_id = ""
    if obj is not None:
        object_type = obj.__class__.__name__
        object_id = str(getattr(obj, "pk", ""))
    return AuditLog.objects.create(
        user=user if (user and user.is_authenticated) else None,
        action=action,
        object_type=object_type,
        object_id=object_id,
        metadata=metadata,
    )


def track(name, request=None, **properties):
    """Record a first-party analytics event. Avoids storing PII."""
    session_key = ""
    if request is not None and request.session.session_key:
        session_key = request.session.session_key
    return AnalyticsEvent.objects.create(
        name=name, properties=properties, session_key=session_key
    )


def notify(event, recipient=None, order_number="", context=None):
    """Dispatch a notification using the configured template + provider.

    The provider is configurable (StoreSetting 'notifications.provider').
    Default renders to the console email backend and stores an in-app record.
    """
    context = context or {}
    try:
        tpl = NotificationTemplate.objects.get(event=event, is_active=True)
        subject = tpl.subject.format(**_safe(context))
        body = tpl.body.format(**_safe(context))
    except NotificationTemplate.DoesNotExist:
        subject = context.get("subject", f"Campus Connect: {event}")
        body = context.get("body", "")

    provider = StoreSetting.get("notifications.provider", "console")
    note = Notification.objects.create(
        recipient=recipient, event=event, subject=subject, body=body,
        order_number=order_number, provider=provider,
    )
    # Email dispatch via the configurable backend.
    to_email = getattr(recipient, "email", "") if recipient else ""
    if to_email:
        try:
            send_mail(
                subject, body, settings.DEFAULT_FROM_EMAIL, [to_email],
                fail_silently=True,
            )
        except Exception:  # noqa: BLE001 - never block the order flow
            pass
    return note


def _safe(context):
    class _D(dict):
        def __missing__(self, key):
            return ""
    return _D(context)
