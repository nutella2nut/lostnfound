from datetime import date, timedelta
from unittest.mock import patch

from django.contrib.auth import get_user_model
from django.test import Client, TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from inventory.models import BroadcastLog, Item, StudentLostItem

User = get_user_model()


@override_settings(
    LF_BROADCAST_RECIPIENTS_LIST=["test1@tisb.ac.in", "test2@tisb.ac.in"],
    LF_EMAIL_ADDRESS="trace@tisb.ac.in",
    LF_EMAIL_DISPLAY_NAME="TRACE Lost & Found",
    EMAIL_HOST="smtp.test",
    EMAIL_HOST_USER="trace@tisb.ac.in",
)
class BroadcastViewTests(TestCase):
    def setUp(self):
        self.superuser = User.objects.create_superuser(
            "superadmin", "super@tisb.ac.in", "pass1234"
        )
        self.admin = User.objects.create_user(
            "staffadmin", "staff@tisb.ac.in", "pass1234", is_staff=True
        )
        self.student_item = StudentLostItem.objects.create(
            title="Lost Notebook",
            description="Blue notebook",
            email_subject="Lost Notebook",
            email_from="student@tisb.ac.in",
            approval_status=StudentLostItem.ApprovalStatus.APPROVED,
        )
        self.found_item = Item.objects.create(
            title="Found Pen",
            description="Black pen",
            location_found="Library",
            date_found=date.today(),
            approval_status=Item.ApprovalStatus.APPROVED,
        )
        self.client = Client()

    def test_superuser_can_access_broadcast_confirm(self):
        self.client.force_login(self.superuser)
        url = reverse("inventory:broadcast_item", args=["student-lost", self.student_item.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 200)

    def test_admin_cannot_access_broadcast(self):
        self.client.force_login(self.admin)
        url = reverse("inventory:broadcast_item", args=["student-lost", self.student_item.pk])
        resp = self.client.get(url)
        self.assertNotEqual(resp.status_code, 200)

    def test_unapproved_item_returns_404(self):
        self.client.force_login(self.superuser)
        pending = StudentLostItem.objects.create(
            title="Pending Item",
            description="Test",
            email_subject="Test",
            email_from="s@tisb.ac.in",
            approval_status=StudentLostItem.ApprovalStatus.PENDING,
        )
        url = reverse("inventory:broadcast_item", args=["student-lost", pending.pk])
        resp = self.client.get(url)
        self.assertEqual(resp.status_code, 404)

    @patch("inventory.views.EmailMessage.send")
    def test_broadcast_creates_log(self, mock_send):
        mock_send.return_value = 1
        self.client.force_login(self.superuser)
        url = reverse("inventory:broadcast_item", args=["student-lost", self.student_item.pk])
        resp = self.client.post(url)
        self.assertEqual(BroadcastLog.objects.count(), 1)
        log = BroadcastLog.objects.first()
        self.assertTrue(log.succeeded)
        self.assertEqual(log.kind, "STUDENT_LOST")
        self.assertEqual(log.sent_by, self.superuser)

    @patch("inventory.views.EmailMessage.send")
    def test_broadcast_rate_limit(self, mock_send):
        mock_send.return_value = 1
        self.client.force_login(self.superuser)
        url = reverse("inventory:broadcast_item", args=["student-lost", self.student_item.pk])
        # Send 3 broadcasts
        for _ in range(3):
            self.client.post(url)
        self.assertEqual(BroadcastLog.objects.count(), 3)
        # 4th should be rate-limited
        resp = self.client.post(url)
        self.assertEqual(BroadcastLog.objects.count(), 3)

    @patch("inventory.views.EmailMessage.send")
    def test_broadcast_found_item(self, mock_send):
        mock_send.return_value = 1
        self.client.force_login(self.superuser)
        url = reverse("inventory:broadcast_item", args=["found", self.found_item.pk])
        resp = self.client.post(url)
        log = BroadcastLog.objects.first()
        self.assertEqual(log.kind, "FOUND_ITEM")
        self.assertTrue(log.succeeded)

    def test_broadcast_history_access(self):
        self.client.force_login(self.superuser)
        resp = self.client.get(reverse("inventory:broadcast_history"))
        self.assertEqual(resp.status_code, 200)

    def test_broadcast_history_filter(self):
        self.client.force_login(self.superuser)
        BroadcastLog.objects.create(
            kind="STUDENT_LOST",
            student_lost_item=self.student_item,
            sent_by=self.superuser,
            recipients="test@tisb.ac.in",
            subject="Test",
            body_preview="Test",
            succeeded=True,
        )
        resp = self.client.get(reverse("inventory:broadcast_history"), {"kind": "STUDENT_LOST"})
        self.assertEqual(resp.status_code, 200)
        self.assertEqual(len(resp.context["broadcasts"]), 1)
