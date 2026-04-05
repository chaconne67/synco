"""Initial migration for data_extraction — includes batch models.

Replaces the previous empty 0001 + state-only 0002 + batch_extract.0001/0002 chain.
On existing DBs: tables already exist, nothing to do (faked).
On fresh DBs: creates gemini_batch_jobs and gemini_batch_items tables.
"""

import django.db.models.deletion
import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    initial = True

    dependencies = [
        ("candidates", "0019_add_skills_and_etc_fields"),
    ]

    operations = [
        migrations.CreateModel(
            name="GeminiBatchJob",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("display_name", models.CharField(max_length=200)),
                ("source", models.CharField(default="drive_resume_import", max_length=50)),
                ("model_name", models.CharField(default="gemini-3.1-flash-lite-preview", max_length=100)),
                ("status", models.CharField(choices=[("preparing", "Preparing"), ("prepared", "Prepared"), ("submitted", "Submitted"), ("running", "Running"), ("succeeded", "Succeeded"), ("failed", "Failed"), ("ingested", "Ingested")], default="preparing", max_length=20)),
                ("category_filter", models.CharField(blank=True, max_length=100)),
                ("parent_folder_id", models.CharField(blank=True, max_length=100)),
                ("request_file_path", models.CharField(blank=True, max_length=500)),
                ("result_file_path", models.CharField(blank=True, max_length=500)),
                ("gemini_file_name", models.CharField(blank=True, max_length=200)),
                ("gemini_batch_name", models.CharField(blank=True, max_length=200)),
                ("total_requests", models.PositiveIntegerField(default=0)),
                ("successful_requests", models.PositiveIntegerField(default=0)),
                ("failed_requests", models.PositiveIntegerField(default=0)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True)),
            ],
            options={
                "db_table": "gemini_batch_jobs",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="GeminiBatchItem",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("request_key", models.CharField(max_length=100)),
                ("drive_file_id", models.CharField(max_length=100)),
                ("file_name", models.CharField(max_length=300)),
                ("category_name", models.CharField(max_length=100)),
                ("status", models.CharField(choices=[("failed", "Failed"), ("prepared", "Prepared"), ("submitted", "Submitted"), ("succeeded", "Succeeded"), ("ingested", "Ingested")], default="prepared", max_length=20)),
                ("raw_text_path", models.CharField(blank=True, max_length=500)),
                ("primary_file", models.JSONField(blank=True, default=dict)),
                ("other_files", models.JSONField(blank=True, default=list)),
                ("filename_meta", models.JSONField(blank=True, default=dict)),
                ("response_json", models.JSONField(blank=True, default=dict)),
                ("error_message", models.TextField(blank=True)),
                ("metadata", models.JSONField(blank=True, default=dict)),
                ("candidate", models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name="gemini_batch_items", to="candidates.candidate")),
                ("job", models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, related_name="items", to="data_extraction.geminibatchjob")),
            ],
            options={
                "db_table": "gemini_batch_items",
                "ordering": ["created_at"],
                "unique_together": {("job", "request_key")},
            },
        ),
    ]
