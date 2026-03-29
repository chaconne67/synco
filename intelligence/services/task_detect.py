import logging

import numpy as np

from common.embedding import get_embedding, get_embeddings_batch

from ._references import cosine_similarity, get_task_vectors

logger = logging.getLogger(__name__)

# Margin threshold: max(task_scores) - not_task_score must exceed this
TASK_MARGIN = 0.05


def detect_task(interaction, embedding: list[float] | None = None):
    """Single interaction → Task or None.

    If caller already got None from get_embedding(), do NOT call this — skip instead.
    Sets interaction.task_checked=True after processing (regardless of Task creation).
    """
    from contacts.models import Task

    refs = get_task_vectors()
    if refs is None:
        return None

    if embedding is None:
        embedding = get_embedding(interaction.summary)
    if embedding is None:
        return None  # task_checked stays False → retry next time

    vec = np.array(embedding)
    scores = {label: cosine_similarity(vec, ref_vec) for label, ref_vec in refs.items()}

    task_score = max(scores.get("task", 0), scores.get("followup", 0), scores.get("promise", 0))
    not_task_score = scores.get("not_task", 0)

    result = None
    if task_score - not_task_score > TASK_MARGIN:
        task, _ = Task.objects.get_or_create(
            fc=interaction.fc,
            contact=interaction.contact,
            title=interaction.summary[:80],
            defaults={
                "source": Task.Source.AI_EXTRACTED,
                "due_date": None,
                "is_completed": False,
            },
        )
        task.source_interactions.add(interaction)
        result = task

    # Mark as checked regardless of whether a task was created
    interaction.task_checked = True
    interaction.save(update_fields=["task_checked"])
    return result


def detect_tasks_batch(
    interactions: list,
    embeddings: list[list[float]] | None = None,
) -> list:
    """Batch detect tasks for N interactions.

    If embeddings provided, reuses them. Otherwise generates via API.
    Only marks task_checked=True for interactions where embedding succeeded.
    """
    from contacts.models import Interaction, Task

    if not interactions:
        return []

    refs = get_task_vectors()
    if refs is None:
        return []

    # Get embeddings
    if embeddings is None:
        texts = [i.summary for i in interactions]
        emb_list = get_embeddings_batch(texts)
    else:
        emb_list = list(embeddings)

    tasks = []
    checked_interactions = []

    for interaction, emb in zip(interactions, emb_list):
        if emb is None:
            continue  # task_checked stays False → retry next time

        vec = np.array(emb)
        scores = {label: cosine_similarity(vec, ref_vec) for label, ref_vec in refs.items()}

        task_score = max(scores.get("task", 0), scores.get("followup", 0), scores.get("promise", 0))
        not_task_score = scores.get("not_task", 0)

        if task_score - not_task_score > TASK_MARGIN:
            task, _ = Task.objects.get_or_create(
                fc=interaction.fc,
                contact=interaction.contact,
                title=interaction.summary[:80],
                defaults={
                    "source": Task.Source.AI_EXTRACTED,
                    "due_date": None,
                    "is_completed": False,
                },
            )
            task.source_interactions.add(interaction)
            tasks.append(task)

        # Mark as checked (embedding succeeded = detection logic ran)
        interaction.task_checked = True
        checked_interactions.append(interaction)

    if checked_interactions:
        Interaction.objects.bulk_update(checked_interactions, ["task_checked"])

    return tasks
