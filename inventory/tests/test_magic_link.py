from datetime import timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.core.signing import TimestampSigner
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from inventory.models import Claim, Item, MagicLinkRequest, StudentLostItem

User = get_user_model()


@override_settings(
    MAGIC_LINK_SECRET="test-secret-key-for-tests",
    EMAIL_HOST="smtp.test",
    EMAIL_HOST_USER="trace@tisb.ac.in",
)
class MagicLinkTests(TestCase):
    def setUp(self):
        self.client = Client()

    def test_signin_page_renders(self):
        resp = self.client.get(reverse("inventory:my_reports"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Sign in to view your reports")

    def test_non_tisb_email_rejected(self):
        resp = self.client.post(
            reverse("inventory:request_magic_link"),
            {"email": "user@gmail.com"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Only @tisb.ac.in email addresses are accepted")

    @patch("inventory.views.send_system_email")
    def test_valid_email_sends_link(self, mock_email):
        resp = self.client.post(
            reverse("inventory:request_magic_link"),
            {"email": "student@tisb.ac.in"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "sign-in link has been sent")
        self.assertEqual(MagicLinkRequest.objects.count(), 1)
        mock_email.assert_called_once()

    @patch("inventory.views.send_system_email")
    def test_rate_limit_at_4th_request(self, mock_email):
        email = "student@tisb.ac.in"
        url = reverse("inventory:request_magic_link")
        for _ in range(3):
            self.client.post(url, {"email": email})
        # 4th should be rate-limited
        resp = self.client.post(url, {"email": email})
        self.assertContains(resp, "too many sign-in links")
        self.assertEqual(MagicLinkRequest.objects.count(), 3)

    @patch("inventory.views.send_system_email")
    def test_token_signin_sets_session(self, mock_email):
        # Request a link
        self.client.post(
            reverse("inventory:request_magic_link"),
            {"email": "student@tisb.ac.in"},
        )
        mlr = MagicLinkRequest.objects.first()

        # Build token manually
        signer = TimestampSigner(key="test-secret-key-for-tests", salt="magic-link")
        token = signer.sign_object({"email": "student@tisb.ac.in", "req_id": mlr.pk})

        resp = self.client.get(
            reverse("inventory:magic_link_signin", args=[token]),
            follow=True,
        )
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(self.client.session["magic_link_email"], "student@tisb.ac.in")

    @patch("inventory.views.send_system_email")
    def test_token_single_use(self, mock_email):
        self.client.post(
            reverse("inventory:request_magic_link"),
            {"email": "student@tisb.ac.in"},
        )
        mlr = MagicLinkRequest.objects.first()
        signer = TimestampSigner(key="test-secret-key-for-tests", salt="magic-link")
        token = signer.sign_object({"email": "student@tisb.ac.in", "req_id": mlr.pk})

        # First use
        self.client.get(reverse("inventory:magic_link_signin", args=[token]))
        mlr.refresh_from_db()
        self.assertIsNotNone(mlr.consumed_at)

        # Second use
        resp = self.client.get(reverse("inventory:magic_link_signin", args=[token]))
        self.assertContains(resp, "already been used")

    def test_invalid_token_shows_error(self):
        resp = self.client.get(
            reverse("inventory:magic_link_signin", args=["invalid-token"])
        )
        self.assertContains(resp, "invalid or has expired")

    def test_dashboard_shows_reports_and_claims(self):
        email = "student@tisb.ac.in"
        # Create test data
        report = StudentLostItem.objects.create(
            title="My Lost Book",
            description="A blue book",
            email_subject="My Lost Book",
            email_from=email,
            approval_status=StudentLostItem.ApprovalStatus.APPROVED,
        )
        item = Item.objects.create(
            title="Found Pen",
            description="Black pen",
            location_found="Library",
            date_found=timezone.now().date(),
            approval_status=Item.ApprovalStatus.APPROVED,
        )
        claim = Claim.objects.create(
            item=item,
            claimant_name="Student Name",
            claimant_email=email,
        )

        # Set session directly
        session = self.client.session
        session["magic_link_email"] = email
        session.save()

        resp = self.client.get(reverse("inventory:my_reports"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "My Lost Book")
        self.assertContains(resp, "Found Pen")

    def test_dashboard_only_shows_own_data(self):
        # Create data for a different email
        StudentLostItem.objects.create(
            title="Other Student Book",
            description="Test",
            email_subject="Test",
            email_from="other@tisb.ac.in",
        )

        session = self.client.session
        session["magic_link_email"] = "me@tisb.ac.in"
        session.save()

        resp = self.client.get(reverse("inventory:my_reports"))
        self.assertNotContains(resp, "Other Student Book")

    def test_signout_clears_session(self):
        session = self.client.session
        session["magic_link_email"] = "student@tisb.ac.in"
        session["magic_link_signed_in_at"] = timezone.now().isoformat()
        session.save()

        resp = self.client.post(reverse("inventory:my_reports_signout"), follow=True)
        self.assertNotIn("magic_link_email", self.client.session)

    def test_magic_link_does_not_grant_staff_access(self):
        session = self.client.session
        session["magic_link_email"] = "student@tisb.ac.in"
        session.save()

        resp = self.client.get(reverse("inventory:admin_dashboard"))
        # Should redirect to login (not authenticated as staff)
        self.assertNotEqual(resp.status_code, 200)
