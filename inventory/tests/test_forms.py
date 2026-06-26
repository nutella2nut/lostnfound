from datetime import date

from django.test import TestCase

from inventory.forms import ItemForm, ItemImageFormSet


class ItemFormTests(TestCase):
    def test_item_form_valid(self):
        form = ItemForm(
            data={
                "title": "Wallet",
                "description": "Brown leather wallet.",
                "location_found": "Cafeteria",
                "date_found": date.today(),
                "status": "FOUND",
                "category": "OTHER_MISC",
                "item_type": "SENIOR",
            }
        )
        self.assertTrue(form.is_valid(), form.errors)


class ItemImageFormSetTests(TestCase):
    def test_image_formset_management_fields_required(self):
        # No actual images here; just assert management form validation behaviour.
        formset = ItemImageFormSet(
            data={
                "images-TOTAL_FORMS": "1",
                "images-INITIAL_FORMS": "0",
                "images-MIN_NUM_FORMS": "0",
                "images-MAX_NUM_FORMS": "3",
                "images-0-image": "",
            }
        )
        self.assertTrue(formset.is_valid())



