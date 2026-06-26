import logging
import os
from io import BytesIO

from django.db.models.signals import pre_save
from django.dispatch import receiver
from PIL import Image

from .models import ItemImage, StudentLostItemImage

logger = logging.getLogger(__name__)

# Register HEIF opener with Pillow if pillow-heif is available
try:
    from pillow_heif import register_heif_opener

    register_heif_opener()
    HEIF_AVAILABLE = True
except ImportError:
    HEIF_AVAILABLE = False
    logger.warning("pillow-heif not available. HEIC files will not be converted.")


def is_heic_file(filename):
    """Check if a file is HEIC/HEIF format."""
    if not filename:
        return False
    filename_lower = filename.lower()
    return filename_lower.endswith((".heic", ".heif"))


@receiver(pre_save, sender=ItemImage)
@receiver(pre_save, sender=StudentLostItemImage)
def convert_heic_image(sender, instance, **kwargs):
    """
    Signal handler to convert HEIC/HEIF files to JPEG before saving.
    """
    # Check if HEIF support is available
    if not HEIF_AVAILABLE:
        return

    # Only process if image field exists
    if not instance.image:
        return

    image_field = instance.image

    # Check if the file is HEIC/HEIF by filename
    filename = getattr(image_field, "name", None) or ""
    if not is_heic_file(filename):
        return

    logger.info(f"Converting HEIC file to JPEG: {filename}")

    try:
        # Read the file content
        image_field.seek(0)
        file_content = image_field.read()
        image_field.seek(0)

        # Open with Pillow (which now supports HEIC via pillow-heif)
        img = Image.open(BytesIO(file_content))

        # Convert to RGB if necessary
        if img.mode in ("RGBA", "LA", "P"):
            rgb_img = Image.new("RGB", img.size, (255, 255, 255))
            if img.mode == "P":
                img = img.convert("RGBA")
            rgb_img.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)
            img = rgb_img
        elif img.mode != "RGB":
            img = img.convert("RGB")

        # Save to JPEG format in memory
        output = BytesIO()
        img.save(output, format="JPEG", quality=95, optimize=True)
        output.seek(0)

        # Update the filename to .jpg
        base_name = os.path.splitext(filename)[0]
        new_filename = f"{base_name}.jpg"

        # Replace the file content
        from django.core.files.base import ContentFile

        instance.image.save(
            new_filename,
            ContentFile(output.read()),
            save=False,  # Don't save yet, let Django handle it
        )
        logger.info(f"Successfully converted HEIC to JPEG: {new_filename}")
    except Exception as e:
        logger.error(f"Error converting HEIC to JPEG: {e}", exc_info=True)
        # Don't raise - allow the original file to be saved if conversion fails

