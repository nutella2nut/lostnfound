from django.db import migrations


def backfill_item_approval(apps, schema_editor):
    """Backfill approved_by and approved_at for existing approved items."""
    from django.db.models import F

    Item = apps.get_model("inventory", "Item")
    Item.objects.filter(
        approval_status="APPROVED",
        approved_by__isnull=True,
    ).update(
        approved_by=F("created_by"),
        approved_at=F("created_at"),
    )


class Migration(migrations.Migration):

    dependencies = [
        ("inventory", "0011_add_item_audit_fields"),
    ]

    operations = [
        migrations.RunPython(
            backfill_item_approval,
            migrations.RunPython.noop,
        ),
    ]
