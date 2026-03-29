"""Backfill embeddings, sentiments, and tasks for all existing contacts.

Run once after deployment:
    uv run python manage.py backfill_embeddings

Options:
    --fc-id UUID    Process only this FC's contacts
    --dry-run       Show counts without processing
    --contacts-only Skip interaction sentiment/task processing
"""

import time

from django.core.management.base import BaseCommand

from common.embedding import get_embeddings_batch
from intelligence.models import ContactEmbedding
from intelligence.services import (
    classify_sentiments_batch,
    detect_tasks_batch,
    embed_contacts_batch,
)
from intelligence.services._references import get_sentiment_vectors, get_task_vectors


def chunked(iterable, size):
    for i in range(0, len(iterable), size):
        yield iterable[i : i + size]


class Command(BaseCommand):
    help = "Backfill embeddings, sentiments, and tasks for existing contacts"

    def add_arguments(self, parser):
        parser.add_argument("--fc-id", type=str, help="Process only this FC's contacts")
        parser.add_argument("--dry-run", action="store_true", help="Show counts only")
        parser.add_argument(
            "--contacts-only", action="store_true", help="Skip interaction processing"
        )

    def handle(self, *args, **options):
        from contacts.models import Contact, Interaction

        fc_id = options.get("fc_id")
        dry_run = options.get("dry_run")
        contacts_only = options.get("contacts_only")

        # Filter contacts
        contacts_qs = Contact.objects.all()
        interactions_qs = Interaction.objects.all()
        if fc_id:
            contacts_qs = contacts_qs.filter(fc_id=fc_id)
            interactions_qs = interactions_qs.filter(fc_id=fc_id)

        total_contacts = contacts_qs.count()
        existing_embeddings = ContactEmbedding.objects.filter(
            contact__in=contacts_qs
        ).count()
        needs_embedding = total_contacts - existing_embeddings

        total_interactions = interactions_qs.count()
        needs_sentiment = interactions_qs.filter(sentiment="").count()
        needs_task = interactions_qs.filter(task_checked=False).count()

        self.stdout.write("\n=== Backfill Summary ===")
        self.stdout.write(
            f"Contacts: {total_contacts} total, {existing_embeddings} embedded, {needs_embedding} remaining"
        )
        self.stdout.write(
            f"Interactions: {total_interactions} total, {needs_sentiment} need sentiment, {needs_task} need task check"
        )

        if dry_run:
            self.stdout.write("\n--dry-run: exiting without processing")
            return

        # Step 0: Ensure reference vectors exist
        self.stdout.write("\nInitializing reference vectors...")
        svecs = get_sentiment_vectors()
        tvecs = get_task_vectors()
        if not svecs or not tvecs:
            self.stderr.write(
                "ERROR: Reference vector initialization failed. Check Gemini API."
            )
            return

        self.stdout.write("  Sentiment refs: OK")
        self.stdout.write("  Task refs: OK")

        # Step 1: Contact embeddings
        contacts_to_embed = list(contacts_qs.order_by("created_at"))
        self.stdout.write(
            f"\nStep 1: Embedding {len(contacts_to_embed)} contacts (100/batch)..."
        )
        start = time.time()
        embedded_count = 0

        for chunk in chunked(contacts_to_embed, 100):
            results = embed_contacts_batch(chunk)
            embedded_count += len(results)
            self.stdout.write(
                f"  {embedded_count}/{len(contacts_to_embed)} contacts embedded"
            )

        elapsed = time.time() - start
        self.stdout.write(f"  Done in {elapsed:.1f}s — {embedded_count} embeddings")

        if contacts_only:
            self.stdout.write("\n--contacts-only: skipping interactions")
            self.stdout.write(self.style.SUCCESS("\nBackfill complete!"))
            return

        # Step 2: Interaction sentiments + tasks
        interactions_to_process = list(
            interactions_qs.filter(sentiment="")
            .union(interactions_qs.filter(task_checked=False))
            .order_by("created_at")
        )
        self.stdout.write(
            f"\nStep 2: Processing {len(interactions_to_process)} interactions (100/batch)..."
        )
        start = time.time()
        processed = 0
        sentiment_set = 0
        tasks_created = 0

        for chunk in chunked(interactions_to_process, 100):
            texts = [i.summary for i in chunk]
            embeddings = get_embeddings_batch(texts)

            # Sentiment
            sentiment_targets = [i for i in chunk if not i.sentiment]
            if sentiment_targets:
                sentiment_embs = [embeddings[chunk.index(i)] for i in sentiment_targets]
                classify_sentiments_batch(sentiment_targets, embeddings=sentiment_embs)
                sentiment_set += len([i for i in sentiment_targets if i.sentiment])

            # Tasks
            task_targets = [i for i in chunk if not i.task_checked]
            if task_targets:
                task_embs = [embeddings[chunk.index(i)] for i in task_targets]
                new_tasks = detect_tasks_batch(task_targets, embeddings=task_embs)
                tasks_created += len(new_tasks)

            processed += len(chunk)
            self.stdout.write(
                f"  {processed}/{len(interactions_to_process)} interactions processed"
            )

        elapsed = time.time() - start
        self.stdout.write(
            f"  Done in {elapsed:.1f}s — {sentiment_set} sentiments, {tasks_created} tasks"
        )

        self.stdout.write(self.style.SUCCESS("\nBackfill complete!"))
