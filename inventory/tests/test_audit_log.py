"""Tests for the audit log: request capture, event hooks, and the Super User page."""

import json
from datetime import date
from email.message import EmailMessage
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.test import Client, RequestFactory, TestCase

from inventory.audit import get_client_ip
from inventory.management.commands.check_emails import Command as CheckEmailsCommand
from inventory.models import AccessAuditLog, Item, StudentLostItem

User = get_user_model()


def make_item(**kwargs):
    defaults = dict(
        title="Blue Bottle", description="x", location_found="Library",
        date_found=date.today(),
    )
    defaults.update(kwargs)
    return Item.objects.create(**defaults)


class ClientIpTests(TestCase):
    def test_uses_rightmost_forwarded_entry(self):
        # Left entries are client-supplied and forgeable; the proxy appends the real one.
        request = RequestFactory().get("/", HTTP_X_FORWARDED_FOR="1.2.3.4, 203.0.113.5")
        self.assertEqual(get_client_ip(request), "203.0.113.5")

    def test_falls_back_to_remote_addr(self):
        request = RequestFactory().get("/", REMOTE_ADDR="198.51.100.7")
        self.assertEqual(get_client_ip(request), "198.51.100.7")


class ClaimAuditTests(TestCase):
    def setUp(self):
        self.item = make_item()
        self.client = Client(HTTP_USER_AGENT="TestUA", HTTP_X_FORWARDED_FOR="203.0.113.5")

    def test_successful_claim_logged_with_metadata(self):
        self.client.post(f"/items/{self.item.pk}/claim/", {
            "name": "Jo Kid", "email": "jo@tisb.ac.in", "attestation": "on",
            "client_metadata": json.dumps({"fingerprint": "abc"}),
        })
        log = AccessAuditLog.objects.get(action="CLAIM")
        self.assertEqual(log.subject_email, "jo@tisb.ac.in")
        self.assertEqual(log.ip_address, "203.0.113.5")
        self.assertEqual(log.user_agent, "TestUA")
        self.assertEqual(log.client_metadata, {"fingerprint": "abc"})
        self.assertEqual(log.item_title_snapshot, "Blue Bottle")

    def test_failed_claim_logged(self):
        self.client.post(f"/items/{self.item.pk}/claim/", {
            "name": "Jo Kid", "email": "jo@gmail.com",
        })
        log = AccessAuditLog.objects.get(action="CLAIM_FAILED")
        self.assertEqual(log.subject_email, "jo@gmail.com")
        self.assertIn("email", log.details["errors"])
        self.assertIn("attestation", log.details["errors"])


class MiddlewareTests(TestCase):
    def test_page_visit_logged_and_linked_to_item(self):
        item = make_item()
        self.client.get(f"/items/{item.pk}/")
        log = AccessAuditLog.objects.get(action="PAGE_VIEW", request_path=f"/items/{item.pk}/")
        self.assertEqual(log.item, item)
        self.assertEqual(log.details["status_code"], 200)

    def test_form_submit_logged(self):
        item = make_item()
        self.client.post(f"/items/{item.pk}/claim/", {})
        self.assertTrue(AccessAuditLog.objects.filter(action="FORM_SUBMIT").exists())

    def test_static_requests_skipped(self):
        self.client.get("/static/does-not-exist.css")
        self.assertFalse(AccessAuditLog.objects.filter(request_path__startswith="/static/").exists())


class AuthAuditTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("teacher", "t@tisb.ac.in", "pw12345!")

    def test_login_and_logout_logged(self):
        self.client.post("/accounts/login/", {"username": "teacher", "password": "pw12345!"})
        self.assertEqual(AccessAuditLog.objects.get(action="LOGIN").actor, self.user)
        self.client.post("/accounts/logout/")
        self.assertEqual(AccessAuditLog.objects.get(action="LOGOUT").actor, self.user)

    def test_failed_login_logged_without_password(self):
        self.client.post("/accounts/login/", {"username": "teacher", "password": "wrong"})
        log = AccessAuditLog.objects.get(action="LOGIN_FAILED")
        self.assertEqual(log.details, {"attempted_username": "teacher"})


class StaffActionAuditTests(TestCase):
    def setUp(self):
        self.su = User.objects.create_superuser("su", "su@tisb.ac.in", "pw")
        self.client.force_login(self.su)

    def test_approve_and_reject_logged(self):
        pending = make_item(approval_status=Item.ApprovalStatus.PENDING)
        self.client.post(f"/staff/approve/admin/{pending.pk}/")
        self.assertEqual(AccessAuditLog.objects.get(action="ITEM_APPROVE").item, pending)

        student = StudentLostItem.objects.create(title="Lost Notebook", email_from="")
        self.client.post(f"/staff/reject/student/{student.pk}/", {"rejection_reason": "dup"})
        log = AccessAuditLog.objects.get(action="ITEM_REJECT")
        self.assertEqual(log.student_item, student)
        self.assertEqual(log.details, {"reason": "dup"})

    def test_delete_keeps_title_snapshot(self):
        item = make_item(title="Red Scarf")
        self.client.post(
            "/staff/dashboard/", json.dumps({"action": "delete_item", "item_id": item.pk}),
            content_type="application/json",
        )
        log = AccessAuditLog.objects.get(action="ITEM_DELETE")
        self.assertIsNone(log.item)
        self.assertEqual(log.item_title_snapshot, "Red Scarf")
        self.assertEqual(log.actor, self.su)


class StudentEmailReportAuditTests(TestCase):
    def test_emailed_report_logged_with_headers(self):
        msg = EmailMessage()
        msg["From"] = "Jo Kid <jo@tisb.ac.in>"
        msg["Subject"] = "Lost water bottle"
        msg["Message-ID"] = "<abc@tisb.ac.in>"
        msg["X-Originating-IP"] = "[203.0.113.9]"
        msg.set_content("Blue, steel.")
        mail = MagicMock()
        mail.fetch.return_value = ("OK", [(b"1", msg.as_bytes())])

        with patch.object(CheckEmailsCommand, "_send_acknowledgment"):
            CheckEmailsCommand()._process_message(mail, b"1", "@tisb.ac.in")

        log = AccessAuditLog.objects.get(action="STUDENT_REPORT")
        self.assertEqual(log.subject_email, "jo@tisb.ac.in")
        self.assertEqual(log.details["headers"]["X-Originating-IP"], ["[203.0.113.9]"])
        self.assertIsNotNone(log.student_item)


class AuditLogPageTests(TestCase):
    def test_super_user_only(self):
        staff = User.objects.create_user("staff", "s@tisb.ac.in", "pw", is_staff=True)
        self.client.force_login(staff)
        self.assertEqual(self.client.get("/staff/audit-logs/").status_code, 403)

        self.client.force_login(User.objects.create_superuser("su", "su@tisb.ac.in", "pw"))
        self.assertEqual(self.client.get("/staff/audit-logs/").status_code, 200)

    def test_events_filter_hides_page_visits(self):
        su = User.objects.create_superuser("su", "su@tisb.ac.in", "pw")
        self.client.force_login(su)
        self.client.get("/")
        AccessAuditLog.objects.create(action="ITEM_UPLOAD", item_title_snapshot="Hat")
        logs = self.client.get("/staff/audit-logs/?action=EVENTS").context["logs"]
        self.assertTrue(logs)
        self.assertTrue(all(log.action not in ("PAGE_VIEW", "FORM_SUBMIT") for log in logs))
