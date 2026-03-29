# Step 2: Migrate source_interaction FK data to source_interactions M2M,
# then remove the FK column.

from django.db import migrations


def migrate_fk_to_m2m(apps, schema_editor):
    """Copy source_interaction FK to source_interactions M2M."""
    Task = apps.get_model("contacts", "Task")
    for task in Task.objects.filter(source_interaction__isnull=False).select_related(
        "source_interaction"
    ):
        task.source_interactions.add(task.source_interaction)


def migrate_m2m_to_fk(apps, schema_editor):
    """Reverse: copy first M2M entry back to FK. Data loss for multi-link tasks is expected."""
    Task = apps.get_model("contacts", "Task")
    for task in Task.objects.all():
        first_interaction = task.source_interactions.first()
        if first_interaction:
            task.source_interaction = first_interaction
            task.save(update_fields=["source_interaction"])


class Migration(migrations.Migration):
    dependencies = [
        ("contacts", "0004_add_fields_before_fk_removal"),
    ]

    operations = [
        migrations.RunPython(migrate_fk_to_m2m, migrate_m2m_to_fk),
        migrations.RemoveField(
            model_name="task",
            name="source_interaction",
        ),
    ]
