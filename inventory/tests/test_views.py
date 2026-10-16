from datetime import date
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from PIL import Image
from unittest.mock import patch

from inventory.models import Item, ItemImage, StudentLostItem


def _create_test_image(name="test.png"):
    buffer = BytesIO()
    image = Image.new("RGB", (10, 10), "black")
    image.save(buffer, format="PNG")
    buffer.seek(0)
    return SimpleUploadedFile(name, buffer.getvalue(), content_type="image/png")


class PublicViewsTests(TestCase):
    def setUp(self):
        self.client = Client()
        self.item1 = Item.objects.create(
            title="Blue Backpack",
            description="Blue backpack with laptop compartment.",
            location_found="Library",
            date_found=date.today(),
            status=Item.Status.FOUND,
        )
        self.item2 = Item.objects.create(
            title="Red Scarf",
            description="Wool scarf.",
            location_found="Cafeteria",
            date_found=date.today(),
            status=Item.Status.CLAIMED,
        )

    def test_item_list_shows_only_found_items(self):
        response = self.client.get(reverse("inventory:item_list"))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Blue Backpack")
        self.assertNotContains(response, "Red Scarf")

    def test_item_list_search_by_query(self):
        response = self.client.get(reverse("inventory:item_list"), {"q": "backpack"})
        self.assertContains(response, "Blue Backpack")

    def test_item_detail_view(self):
        response = self.client.get(reverse("inventory:item_detail", args=[self.item1.pk]))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, "Blue Backpack")


class StaffUploadViewsTests(TestCase):
    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.staff = User.objects.create_user(
            username="staff",
            password="pw",
            is_staff=True,
        )

    def test_upload_requires_authentication(self):
        response = self.client.get(reverse("inventory:item_upload"))
        self.assertEqual(response.status_code, 302)
        self.assertIn("/accounts/login/", response["Location"])

    def test_upload_saves_item_and_redirects(self):
        self.client.login(username="staff", password="pw")
        image = _create_test_image()

        post_data = {
            "title": "Black Umbrella",
            "description": "Compact umbrella.",
            "location_found": "Lobby",
            "date_found": date.today(),
            "status": Item.Status.FOUND,
            "category": "OTHER_MISC",
            "item_type": "SENIOR",
            "images-TOTAL_FORMS": "1",
            "images-INITIAL_FORMS": "0",
            "images-MIN_NUM_FORMS": "0",
            "images-MAX_NUM_FORMS": "3",
        }

        response = self.client.post(
            reverse("inventory:item_upload"),
            data={**post_data, "images-0-image": image},
        )

        # Should redirect to browse page after successful upload.
        self.assertEqual(response.status_code, 302)
        self.assertIn("/browse/", response["Location"])

        item = Item.objects.get(title="Black Umbrella")
        self.assertEqual(item.created_by, self.staff)
        self.assertEqual(item.approval_status, "PENDING")
        self.assertEqual(ItemImage.objects.filter(item=item).count(), 1)


class ApproveStudentItemInlineEditTests(TestCase):
    """Super Users can clean up a student submission's title/description at approval time."""

    def setUp(self):
        self.client = Client()
        User = get_user_model()
        self.superuser = User.objects.create_user(
            username="super", password="pw", is_staff=True, is_superuser=True
        )
        self.client.login(username="super", password="pw")
        self.item = StudentLostItem.objects.create(
            title="Re: fwd HELP???",
            description="i lost my thing",
            email_from="student@tisb.ac.in",
            approval_status=StudentLostItem.ApprovalStatus.PENDING,
        )

    def _approve_url(self):
        return reverse("inventory:approve_item", args=["student", self.item.pk])

    @patch("inventory.views.send_system_email")
    def test_quick_approve_without_edit_keeps_original(self, _mock_email):
        response = self.client.post(self._approve_url())
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.approval_status, "APPROVED")
        self.assertEqual(self.item.title, "Re: fwd HELP???")
        self.assertEqual(self.item.description, "i lost my thing")

    @patch("inventory.views.send_system_email")
    def test_approve_with_edit_updates_fields(self, _mock_email):
        response = self.client.post(self._approve_url(), {
            "title": "Blue water bottle",
            "description": "Lost near the library on Tuesday.",
        })
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        self.assertEqual(self.item.approval_status, "APPROVED")
        self.assertEqual(self.item.title, "Blue water bottle")
        self.assertEqual(self.item.description, "Lost near the library on Tuesday.")

    @patch("inventory.views.send_system_email")
    def test_approve_with_empty_title_is_rejected(self, _mock_email):
        response = self.client.post(self._approve_url(), {
            "title": "   ",
            "description": "whatever",
        })
        self.assertEqual(response.status_code, 302)
        self.item.refresh_from_db()
        # Still pending, unchanged — an empty title must not publish.
        self.assertEqual(self.item.approval_status, "PENDING")
        self.assertEqual(self.item.title, "Re: fwd HELP???")

    @patch("inventory.views.send_system_email")
    def test_edited_title_is_truncated_to_200(self, _mock_email):
        long_title = "x" * 250
        self.client.post(self._approve_url(), {"title": long_title, "description": "d"})
        self.item.refresh_from_db()
        self.assertEqual(len(self.item.title), 200)

    def test_approval_queue_renders_editable_modal(self):
        response = self.client.get(reverse("inventory:approval_queue"), {"view": "pending"})
        self.assertEqual(response.status_code, 200)
        body = response.content.decode()
        # The editable modal wiring is present for student items.
        self.assertIn("editTitleInput", body)
        self.assertIn("Save &amp; Approve", body)
        self.assertIn("var csrfToken", body)





class CheckEmailsCronTests(TestCase):
    url = "/internal/check-emails/"

    @patch("inventory.views.call_command")
    def test_runs_check_emails_with_valid_secret(self, mock_call):
        with self.settings(CRON_SECRET="s3cret"):
            response = self.client.post(self.url, HTTP_AUTHORIZATION="Bearer s3cret")
        self.assertEqual(response.status_code, 200)
        mock_call.assert_called_once_with("check_emails")

    @patch("inventory.views.call_command")
    def test_rejects_wrong_secret(self, mock_call):
        with self.settings(CRON_SECRET="s3cret"):
            response = self.client.post(self.url, HTTP_AUTHORIZATION="Bearer nope")
        self.assertEqual(response.status_code, 403)
        mock_call.assert_not_called()

    @patch("inventory.views.call_command")
    def test_rejects_when_secret_not_configured(self, mock_call):
        with self.settings(CRON_SECRET=""):
            response = self.client.post(self.url, HTTP_AUTHORIZATION="Bearer ")
        self.assertEqual(response.status_code, 403)
        mock_call.assert_not_called()
