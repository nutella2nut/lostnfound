"""Tests for the Super User Settings page and the behaviour each setting controls."""

from datetime import date, timedelta
from email.message import EmailMessage
from io import BytesIO, StringIO
from unittest.mock import MagicMock, patch

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.core.management import call_command
from django.test import TestCase, override_settings
from django.utils import timezone
from PIL import Image

from inventory.management.commands.check_emails import Command as CheckEmailsCommand
from inventory.models import (
    AccessAuditLog, BroadcastLog, Claim, EmailTemplate, Item, MicrosoftOAuthToken,
    StudentLostItem,
)
from inventory.site_settings import get_site_settings, render_email

User = get_user_model()


def make_item(**kwargs):
    defaults = dict(title="Blue Bottle", description="x", location_found="Gym", date_found=date.today())
    defaults.update(kwargs)
    return Item.objects.create(**defaults)


def png(name="a.png"):
    buf = BytesIO()
    Image.new("RGB", (4, 4)).save(buf, "PNG")
    return SimpleUploadedFile(name, buf.getvalue(), content_type="image/png")


def update_settings(**fields):
    site = get_site_settings()
    for k, v in fields.items():
        setattr(site, k, v)
    site.save()
    return site


def claim(client, item, email="jo@tisb.ac.in"):
    return client.post(f"/items/{item.pk}/claim/", {"name": "Jo Kid", "email": email, "attestation": "on"})


class SettingsPageTests(TestCase):
    def setUp(self):
        self.su = User.objects.create_superuser("su", "su@tisb.ac.in", "pw")
        self.client.force_login(self.su)

    def test_only_super_users(self):
        self.client.logout()
        self.assertEqual(self.client.get("/staff/settings/general/").status_code, 302)
        self.client.force_login(User.objects.create_user("st", "st@tisb.ac.in", "pw", is_staff=True))
        self.assertEqual(self.client.get("/staff/settings/general/").status_code, 403)
        self.assertEqual(self.client.post("/staff/settings/general/", {}).status_code, 403)

    def test_save_is_applied_and_logged(self):
        data = {
            "site_name": "TRACE", "school_name": "TISB", "email_signoff": "— Bye",
            "sender_display_name": "TRACE Lost & Found", "contact_email": "",
            "announcement_enabled": "on", "announcement_text": "Closed Friday",
        }
        self.client.post("/staff/settings/general/", data)
        self.assertEqual(get_site_settings().email_signoff, "— Bye")
        log = AccessAuditLog.objects.get(action="SETTINGS_CHANGE")
        self.assertEqual(log.details["section"], "general")
        self.assertEqual(log.details["changes"]["email_signoff"][1], "— Bye")
        self.assertContains(self.client.get("/"), "Closed Friday")

    def test_invalid_values_rejected(self):
        get_site_settings()
        r = self.client.post("/staff/settings/claims/", {
            "allowed_email_domain": "tisb.ac.in", "claimed_visibility_default_days": 1,
        })
        self.assertContains(r, "Enter a domain starting with @")
        r = self.client.post("/staff/settings/uploads/", {"max_staff_upload_images": 3, "ai_model": "x/../y"})
        self.assertContains(r, "lowercase letters")
        r = self.client.post("/staff/settings/broadcasts/", {
            "broadcast_recipients": "ok@tisb.ac.in\nnot-an-email", "broadcast_limit_count": 3,
            "broadcast_limit_hours": 24, "broadcast_max_attachment_mb": 20,
        })
        self.assertContains(r, "not-an-email")
        self.assertFalse(AccessAuditLog.objects.filter(action="SETTINGS_CHANGE").exists())

    @override_settings(GOOGLE_API_KEY="super-secret-key-123")
    def test_status_page_never_shows_secrets(self):
        r = self.client.get("/staff/settings/status/")
        self.assertContains(r, "✓ Set")
        self.assertNotContains(r, "super-secret-key-123")

    def test_oauth_disconnect_requires_confirmation(self):
        MicrosoftOAuthToken.objects.create(account_email="trace@tisb.ac.in", encrypted_refresh_token=b"x", scopes="s")
        self.client.post("/staff/settings/status/", {})
        self.assertTrue(MicrosoftOAuthToken.objects.exists())
        self.client.post("/staff/settings/status/", {"confirm": "disconnect"})
        self.assertFalse(MicrosoftOAuthToken.objects.exists())


class ClaimSettingsTests(TestCase):
    def test_domain_change_applies_to_claims(self):
        update_settings(allowed_email_domain="@school.edu")
        item = make_item()
        claim(self.client, item, "jo@tisb.ac.in")
        self.assertFalse(Claim.objects.exists())
        claim(self.client, item, "jo@school.edu")
        self.assertTrue(Claim.objects.exists())
        self.assertContains(self.client.get(f"/items/{item.pk}/"), "@school\\.edu")

    def test_claims_paused(self):
        update_settings(claims_enabled=False)
        item = make_item()
        claim(self.client, item)
        self.assertFalse(Claim.objects.exists())
        log = AccessAuditLog.objects.get(action="CLAIM_FAILED")
        self.assertEqual(log.details, {"reason": "claims_disabled"})

    def test_single_claim_only(self):
        update_settings(allow_multiple_claims=False)
        item = make_item()
        claim(self.client, item)
        claim(self.client, item, "other@tisb.ac.in")
        self.assertEqual(Claim.objects.count(), 1)

    def test_claimed_visibility_window(self):
        item = make_item(category=Item.Category.ELECTRONICS, status=Item.Status.CLAIMED,
                         claimed_at=timezone.now() - timedelta(days=5))
        self.assertIn(item, self.client.get("/browse/").context["items"])
        update_settings(claimed_visibility_days={"ELECTRONICS": 2})
        self.assertNotIn(item, self.client.get("/browse/").context["items"])


class UploadSettingsTests(TestCase):
    def setUp(self):
        self.staff = User.objects.create_user("st", "st@tisb.ac.in", "pw", is_staff=True)
        self.client.force_login(self.staff)

    def upload(self, n_images=1):
        data = {
            "title": "Umbrella", "description": "d", "location_found": "Lobby",
            "date_found": date.today(), "status": "FOUND", "category": "OTHER_MISC", "item_type": "SENIOR",
            "images-TOTAL_FORMS": str(n_images), "images-INITIAL_FORMS": "0",
            "images-MIN_NUM_FORMS": "0", "images-MAX_NUM_FORMS": "10",
        }
        for i in range(n_images):
            data[f"images-{i}-image"] = png(f"{i}.png")
        return self.client.post("/staff/items/upload/", data)

    def test_staff_upload_auto_approved_when_approval_off(self):
        update_settings(staff_uploads_require_approval=False)
        self.upload()
        self.assertEqual(Item.objects.get().approval_status, "APPROVED")

    def test_max_images_enforced_on_server(self):
        update_settings(max_staff_upload_images=1)
        r = self.upload(n_images=2)
        self.assertContains(r, "at most 1 images")
        self.assertFalse(Item.objects.exists())

    @patch("inventory.services.requests.post")
    def test_ai_disabled_makes_no_api_call(self, post):
        from inventory.services import analyze_item_images
        update_settings(ai_enabled=False)
        with override_settings(GOOGLE_API_KEY="k"):
            self.assertEqual(analyze_item_images([png()]), {})
        post.assert_not_called()


class IntakeSettingsTests(TestCase):
    def process(self, n_images):
        msg = EmailMessage()
        msg["From"] = "Jo Kid <jo@tisb.ac.in>"
        msg["Subject"] = "Lost hat"
        msg["Message-ID"] = f"<{n_images}@tisb.ac.in>"
        msg.set_content("Red hat")
        for i in range(n_images):
            msg.add_attachment(png().read(), maintype="image", subtype="png", filename=f"{i}.png")
        mail = MagicMock()
        mail.fetch.return_value = ("OK", [(b"1", msg.as_bytes())])
        with patch.object(CheckEmailsCommand, "_send_acknowledgment"):
            CheckEmailsCommand()._process_message(mail, b"1", get_site_settings().allowed_email_domain)
        return StudentLostItem.objects.latest("pk")

    def test_max_images_from_settings(self):
        update_settings(intake_max_images=2)
        item = self.process(n_images=3)
        self.assertEqual(item.images.count(), 2)
        self.assertIn("More than 2 images", item.needs_review_reason)

    @patch("inventory.management.commands.check_emails.connect_imap")
    def test_intake_paused_skips_mailbox(self, connect):
        update_settings(email_reports_enabled=False)
        CheckEmailsCommand()._run_cycle()
        connect.assert_not_called()


@override_settings(LF_BROADCAST_RECIPIENTS_LIST=["seed@tisb.ac.in"], EMAIL_HOST="smtp.test",
                   EMAIL_HOST_USER="trace@tisb.ac.in", LF_EMAIL_ADDRESS="trace@tisb.ac.in")
class BroadcastSettingsTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser("su", "su@tisb.ac.in", "pw"))
        self.item = make_item()

    def test_recipients_seeded_from_env_then_editable(self):
        self.assertEqual(get_site_settings().broadcast_recipient_list, ["seed@tisb.ac.in"])
        update_settings(broadcast_recipients="a@tisb.ac.in\nb@tisb.ac.in")
        self.client.post(f"/staff/broadcast/found/{self.item.pk}/")
        self.assertEqual(BroadcastLog.objects.get().recipients, "a@tisb.ac.in, b@tisb.ac.in")

    def test_rate_limit_from_settings(self):
        update_settings(broadcast_limit_count=1)
        self.client.post(f"/staff/broadcast/found/{self.item.pk}/")
        self.client.post(f"/staff/broadcast/found/{self.item.pk}/")
        self.assertEqual(BroadcastLog.objects.count(), 1)


class PrivacySettingsTests(TestCase):
    def test_page_view_logging_off(self):
        update_settings(log_page_views=False)
        self.client.get("/")
        self.assertFalse(AccessAuditLog.objects.filter(action="PAGE_VIEW").exists())

    def test_fingerprint_off_removes_field(self):
        item = make_item()
        self.assertContains(self.client.get(f"/items/{item.pk}/"), 'name="client_metadata"')
        update_settings(collect_fingerprint=False)
        self.assertNotContains(self.client.get(f"/items/{item.pk}/"), 'name="client_metadata"')

    def test_purge_uses_retention_setting(self):
        update_settings(audit_retention_days=10)
        old = AccessAuditLog.objects.create(action="LOGIN")
        AccessAuditLog.objects.filter(pk=old.pk).update(created_at=timezone.now() - timedelta(days=11))
        AccessAuditLog.objects.create(action="LOGIN")
        call_command("purge_access_logs", stdout=StringIO())
        self.assertEqual(AccessAuditLog.objects.count(), 1)
        self.assertIsNotNone(get_site_settings().last_audit_purge_at)


class EmailTemplateTests(TestCase):
    def setUp(self):
        self.client.force_login(User.objects.create_superuser("su", "su@tisb.ac.in", "pw"))

    def test_default_matches_original_text(self):
        subject, body, _ = render_email("report_approved", first_name="Jo", item_title="Hat")
        self.assertEqual(subject, 'Your lost item report has been approved — "Hat"')
        self.assertTrue(body.startswith("Hi Jo,\n\nYour lost item report has been reviewed"))
        self.assertTrue(body.endswith("— TRACE, TISB Lost & Found"))

    def test_edit_is_used_when_sending(self):
        self.client.post("/staff/settings/emails/claim_confirmation/", {
            "subject": "Claimed: {item_title}", "body": "Hello {name} from {school_name}",
        })
        with patch("inventory.views.send_system_email") as send:
            claim(self.client, make_item(title="Hat"))
        kwargs = send.call_args.kwargs
        self.assertEqual(kwargs["subject"], "Claimed: Hat")
        self.assertEqual(kwargs["message"], "Hello Jo Kid from TISB")
        self.assertTrue(AccessAuditLog.objects.filter(action="SETTINGS_CHANGE").exists())

    def test_unsafe_or_unknown_placeholders_rejected(self):
        for body in ("Hi {nmae}", "Hi {name.__class__}", "Hi {name!r}", "Hi {"):
            r = self.client.post("/staff/settings/emails/claim_confirmation/", {"subject": "s", "body": body})
            self.assertEqual(r.status_code, 200, body)
        self.assertFalse(EmailTemplate.objects.exists())

    def test_reset_restores_default(self):
        EmailTemplate.objects.create(key="report_approved", subject="x", body="y")
        self.client.post("/staff/settings/emails/report_approved/", {"reset": "1"})
        self.assertFalse(EmailTemplate.objects.exists())
