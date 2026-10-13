"""Forensic request-metadata capture for sensitive actions.

Centralizes building an AccessAuditLog row from an HTTP request so the views stay
thin. Nothing here may raise into the caller's happy path — record_access logs and
swallows its own errors.
"""
import ipaddress
import json
import logging

from django.db import transaction

from .models import AccessAuditLog

logger = logging.getLogger(__name__)

# Reject client blobs larger than this (bytes) — a normal payload is <2 KB.
MAX_CLIENT_METADATA_BYTES = 8192


def get_client_ip(request):
    """Return the best-guess client IP.

    Behind Railway's proxy, REMOTE_ADDR is only the proxy. The proxy *appends*
    the address it saw to X-Forwarded-For, so the right-most entry is the one we
    can trust — anything to its left was supplied by the client and can be
    forged (the full chain is still stored in forwarded_for). Returns None if
    nothing parses as a valid IP.
    """
    forwarded = request.META.get("HTTP_X_FORWARDED_FOR", "")
    candidates = [p.strip() for p in forwarded.split(",") if p.strip()][-1:]
    candidates.append(request.META.get("REMOTE_ADDR", "").strip())
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return str(ipaddress.ip_address(candidate))
        except ValueError:
            continue
    return None


def parse_client_metadata(raw):
    """Safely parse the client_metadata hidden-field JSON. Never raises."""
    if not raw:
        return {}
    if len(raw) > MAX_CLIENT_METADATA_BYTES:
        return {}
    try:
        data = json.loads(raw)
    except (ValueError, TypeError):
        return {}
    return data if isinstance(data, dict) else {}


def record_access(request, action, *, item=None, student_item=None, claim=None,
                  actor=None, subject_name="", subject_email="", details=None):
    """Persist an AccessAuditLog row for a sensitive action. Never raises.

    ``request`` may be None for actions with no HTTP request (e.g. emailed
    reports); request metadata is then left blank. ``actor`` defaults to the
    request's authenticated user.
    """
    try:
        if actor is None and request is not None:
            user = getattr(request, "user", None)
            if user is not None and user.is_authenticated:
                actor = user

        if claim is not None:
            subject_name = subject_name or claim.claimant_name
            subject_email = subject_email or claim.claimant_email

        target = item or student_item
        meta = request.META if request is not None else {}

        # Savepoint: a failed insert must not poison the caller's transaction.
        with transaction.atomic():
            AccessAuditLog.objects.create(
                action=action,
                actor=actor,
                actor_username_snapshot=(actor.get_username() if actor else ""),
                item=item,
                student_item=student_item,
                claim=claim,
                item_title_snapshot=(target.title[:255] if target else ""),
                subject_name=subject_name[:255],
                subject_email=subject_email[:254],
                ip_address=(get_client_ip(request) if request is not None else None),
                forwarded_for=meta.get("HTTP_X_FORWARDED_FOR", ""),
                user_agent=meta.get("HTTP_USER_AGENT", ""),
                accept_language=meta.get("HTTP_ACCEPT_LANGUAGE", "")[:255],
                referer=meta.get("HTTP_REFERER", ""),
                request_path=(request.path[:255] if request is not None else ""),
                request_method=((request.method or "") if request is not None else ""),
                client_metadata=(
                    parse_client_metadata(request.POST.get("client_metadata"))
                    if request is not None and request.method == "POST" else {}
                ),
                details=details or {},
            )
    except Exception:
        logger.exception("Failed to record access audit log (%s)", action)
