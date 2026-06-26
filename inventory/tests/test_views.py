from datetime import date
from io import BytesIO

from django.contrib.auth import get_user_model
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase
from django.urls import reverse
from PIL import Image
from unittest.mock import patch

from inventory.models import Item, ItemImage


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



