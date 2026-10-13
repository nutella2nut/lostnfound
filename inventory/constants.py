"""Shared constants for the inventory app."""

# Limits in {braces} are filled from SiteSettings when the reason is recorded.
NEEDS_REVIEW_REASONS = {
    "TITLE_MISSING": "Title was missing from subject line",
    "BODY_EMPTY": "Email body was empty",
    "ATTACHMENT_OVERSIZED": "Some attachments exceeded the {max_image_mb} MB per-image limit",
    "TOTAL_OVERSIZED": "Combined attachment size exceeded {max_total_mb} MB — submission stored without images",
    "TOO_MANY_IMAGES": "More than {max_images} images attached — only the first {max_images} were retained",
    "HEIC_CONVERSION_FAILED": "One or more HEIC attachments could not be converted to JPEG",
    "EXIF_STRIP_FAILED": "EXIF metadata stripping failed on one or more images",
}
