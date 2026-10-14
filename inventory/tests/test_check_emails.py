"""Tests for check_emails management command — email parsing per §1.3."""

import base64
from email.message import EmailMessage
from io import BytesIO
from unittest import mock

from django.test import TestCase
from PIL import Image

from inventory.management.commands.check_emails import (
    Command,
    decode_mime_header,
    iter_email_images,
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


def _png_bytes(size=(400, 300)):
    buf = BytesIO()
    Image.new("RGB", size, "blue").save(buf, format="PNG")
    return buf.getvalue()


class InlineImageTests(TestCase):
    def test_attachment_detected(self):
        msg = EmailMessage()
        msg.set_content("see attached")
        msg.add_attachment(_png_bytes(), maintype="image", subtype="png", filename="bottle.png")
        self.assertEqual([name for name, _ in iter_email_images(msg)], ["bottle.png"])

    def test_cid_inline_image_detected(self):
        msg = EmailMessage()
        msg.set_content("see pic")
        msg.add_alternative('<p>see</p><img src="cid:img1">', subtype="html")
        msg.get_payload()[1].add_related(_png_bytes(), "image", "png", cid="<img1>")
        images = list(iter_email_images(msg))
        self.assertEqual(len(images), 1)
        self.assertEqual(images[0][0], "inline-1.png")
        self.assertEqual(images[0][1], _png_bytes())

    def test_data_uri_inline_image_detected(self):
        b64 = base64.b64encode(_png_bytes()).decode()
        # Wrapped across lines the way some mail clients emit it
        wrapped = "\n".join(b64[i:i + 20] for i in range(0, len(b64), 20))
        msg = EmailMessage()
        msg.set_content(f'<p>lost this</p><img src="data:image/png;base64,{wrapped}">', subtype="html")
        images = list(iter_email_images(msg))
        self.assertEqual(images, [("inline-1.png", _png_bytes())])

    def test_plain_text_email_has_no_images(self):
        msg = EmailMessage()
        msg.set_content("no pictures here, data:image/png;base64 mentioned in text")
        self.assertEqual(list(iter_email_images(msg)), [])

    def test_small_inline_signature_logo_skipped(self):
        logo = _png_bytes((150, 60))
        b64 = base64.b64encode(logo).decode()
        msg = EmailMessage()
        msg.set_content("see pic")
        msg.add_alternative(
            f'<img src="cid:photo"><p>--</p><img src="cid:logo"><img src="data:image/png;base64,{b64}">',
            subtype="html",
        )
        msg.get_payload()[1].add_related(_png_bytes(), "image", "png", cid="<photo>")
        msg.get_payload()[1].add_related(logo, "image", "png", cid="<logo>", filename="image001.png", disposition="inline")
        self.assertEqual([name for name, _ in iter_email_images(msg)], ["inline-1.png"])

    def test_small_explicit_attachment_kept(self):
        msg = EmailMessage()
        msg.set_content("see attached")
        msg.add_attachment(_png_bytes((100, 100)), maintype="image", subtype="png", filename="tag.png")
        self.assertEqual([name for name, _ in iter_email_images(msg)], ["tag.png"])

    def test_process_message_saves_inline_images(self):
        msg = EmailMessage()
        msg["From"] = "Student <student@tisb.ac.in>"
        msg["Subject"] = "Lost blue bottle"
        msg["Message-ID"] = "<inline-test@tisb.ac.in>"
        b64 = base64.b64encode(_png_bytes()).decode()
        msg.set_content("Lost my bottle")
        msg.add_alternative(
            f'<p>Lost my bottle</p><img src="cid:img1"><img src="data:image/png;base64,{b64}">',
            subtype="html",
        )
        msg.get_payload()[1].add_related(_png_bytes(), "image", "png", cid="<img1>")

        mail = mock.Mock()
        mail.fetch.return_value = ("OK", [(b"1", msg.as_bytes())])
        created = Command()._process_message(mail, b"1", "tisb.ac.in")

        self.assertTrue(created)
        item = StudentLostItem.objects.get(source_message_id="<inline-test@tisb.ac.in>")
        self.assertEqual(item.images.count(), 2)

