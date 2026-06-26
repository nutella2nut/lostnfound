from datetime import datetime

from django import template
from django.utils import timezone

register = template.Library()

IST = timezone.get_fixed_timezone(330)  # UTC+5:30


@register.filter
def to_ist(value):
    """Convert a datetime to Indian Standard Time (UTC+5:30).

    Returns the datetime object in IST. Use with Django's ``date``
    filter for formatting, e.g. ``{{ obj.created_at|to_ist|date:"d M Y, h:i A" }}``.
    """
    if not isinstance(value, datetime):
        return value
    if timezone.is_naive(value):
        value = timezone.make_aware(value, timezone.utc)
    return value.astimezone(IST)
