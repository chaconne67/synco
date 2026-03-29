# Step 1: Add new fields (import_batch, task_checked, source_interactions M2M)
# FK removal comes after data migration in 0005.

import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("contacts", "0003_contact_business_urgency_score_and_more"),
        ("intelligence", "0003_alter_fortunateinsight_unique_together_and_more"),
    ]

    operations = [
        migrations.AddField(
            model_name="interaction",
            name="import_batch",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="interactions",
                to="intelligence.importbatch",
            ),
        ),
        migrations.AddField(
            model_name="interaction",
            name="task_checked",
            field=models.BooleanField(default=False),
        ),
        migrations.AddField(
            model_name="task",
            name="source_interactions",
            field=models.ManyToManyField(
                blank=True, related_name="detected_tasks", to="contacts.interaction"
            ),
        ),
    ]
