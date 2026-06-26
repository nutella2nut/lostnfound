"""Tests for check_emails management command — email parsing per §1.3."""

from email.message import EmailMessage

from django.test import TestCase

from inventory.management.commands.check_emails import (
    decode_mime_header,
    strip_exif_gps,
    strip_html_tags,
    strip_quoted_and_signature,
    strip_subject_prefixes,
)
from inventory.models import StudentLostItem


class SubjectPrefixTests(TestCase):
    def test_strips_re(self):
        self.assertEqual(strip_subject_prefixes("Re: Lost water bottle"), "Lost water bottle")

    def test_strips_fwd(self):
        self.assertEqual(strip_subject_prefixes("Fwd: Lost water bottle"), "Lost water bottle")

    def test_strips_repeated(self):
        self.assertEqual(strip_subject_prefixes("Re: Fwd: Re: Lost item"), "Lost item")

    def test_strips_case_insensitive(self):
        self.assertEqual(strip_subject_prefixes("FW: RE: Something"), "Something")

    def test_no_prefix(self):
        self.assertEqual(strip_subject_prefixes("Lost water bottle"), "Lost water bottle")

    def test_empty(self):
        self.assertEqual(strip_subject_prefixes(""), "")


class BodyStrippingTests(TestCase):
    def test_strip_quoted_lines(self):
        text = "My item\n> Previous text\n> More quoted"
        result = strip_quoted_and_signature(text)
        self.assertEqual(result.strip(), "My item")

    def test_strip_signature_separator(self):
        text = "My description\n-- \nJohn Doe"
        result = strip_quoted_and_signature(text)
        self.assertEqual(result.strip(), "My description")

    def test_strip_sent_from(self):
        text = "My item details\nSent from my iPhone"
        result = strip_quoted_and_signature(text)
        self.assertEqual(result.strip(), "My item details")

    def test_strip_on_wrote(self):
        text = "My text\nOn Mon, Jun 23, 2026, John wrote:\nSome quoted text"
        result = strip_quoted_and_signature(text)
        self.assertEqual(result.strip(), "My text")

    def test_preserves_normal_text(self):
        text = "Line one\nLine two\nLine three"
        result = strip_quoted_and_signature(text)
        self.assertEqual(result, text)


class HtmlStrippingTests(TestCase):
    def test_strips_tags(self):
        self.assertEqual(strip_html_tags("<p>Hello <b>world</b></p>"), "Hello world")

    def test_plain_text_passthrough(self):
        self.assertEqual(strip_html_tags("Just text"), "Just text")


class DecodeMimeHeaderTests(TestCase):
    def test_plain_ascii(self):
        self.assertEqual(decode_mime_header("Hello"), "Hello")

    def test_none(self):
        self.assertEqual(decode_mime_header(None), "")

    def test_empty(self):
        self.assertEqual(decode_mime_header(""), "")


class ExifStripTests(TestCase):
    def test_returns_bytes_for_non_image(self):
        raw = b"not an image"
        result, ok = strip_exif_gps(raw)
        # Should fail gracefully
        self.assertFalse(ok)
        self.assertEqual(result, raw)

    def test_strips_from_valid_jpeg(self):
        from io import BytesIO
        from PIL import Image

        img = Image.new("RGB", (10, 10), "red")
        buf = BytesIO()
        img.save(buf, format="JPEG")
        raw = buf.getvalue()

        result, ok = strip_exif_gps(raw)
        self.assertTrue(len(result) > 0)
