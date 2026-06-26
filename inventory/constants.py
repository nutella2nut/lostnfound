"""Shared constants for the inventory app."""

NEEDS_REVIEW_REASONS = {
    "TITLE_MISSING": "Title was missing from subject line",
    "BODY_EMPTY": "Email body was empty",
    "ATTACHMENT_OVERSIZED": "Some attachments exceeded the 15 MB per-image limit",
    "TOTAL_OVERSIZED": "Combined attachment size exceeded 40 MB — submission stored without images",
    "TOO_MANY_IMAGES": "More than 8 images attached — only the first 8 were retained",
    "HEIC_CONVERSION_FAILED": "One or more HEIC attachments could not be converted to JPEG",
    "EXIF_STRIP_FAILED": "EXIF metadata stripping failed on one or more images",
}
