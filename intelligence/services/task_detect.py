import logging
from datetime import date

import numpy as np

from common.embedding import get_embedding, get_embeddings_batch
from common.llm import call_llm_json

from ._references import cosine_similarity, get_task_vectors

logger = logging.getLogger(__name__)

TASK_MARGIN = 0.05

TITLE_SYSTEM_PROMPT = (
    "보험설계사(FC)의 고객 접점 메모에서 FC가 해야 할 다음 액션을 추출합니다. "
    "반드시 아래 JSON 형식으로만 응답하세요."
)

TITLE_USER_TEMPLATE = """메모: {summary}
고객: {contact_name} / {company_name}

다음 JSON을 반환하세요:
{{"title": "FC가 해야 할 다음 액션 한 줄 요약 (20자 이내)", "due_date": "YYYY-MM-DD 또는 null (메모에 날짜 힌트가 있을 때만)"}}"""


def _extract_title_and_date(interaction) -> dict:
    """Call LLM to extract action title and due date from memo."""
    try:
        result = call_llm_json(
            TITLE_USER_TEMPLATE.format(
                summary=interaction.summary[:500],
                contact_name=interaction.contact.name if interaction.contact else "",
                company_name=interaction.contact.company_name
                if interaction.contact
                else "",
            ),
            system=TITLE_SYSTEM_PROMPT,
            timeout=30,
        )
        return {
            "title": str(result.get("title", ""))[:200],
            "due_date": result.get("due_date"),
        }
    except Exception:
        logger.exception("LLM title extraction failed")
        name = interaction.contact.name if interaction.contact else ""
        return {"title": f"{name} 팔로업", "due_date": None}


def _parse_due_date(date_str) -> date | None:
    if not date_str:
        return None
    try:
        return date.fromisoformat(str(date_str))
    except (ValueError, TypeError):
        return None


def detect_task(interaction, embedding=None):
    """Single interaction -> Task or None."""
    from contacts.models import Task

    refs = get_task_vectors()
    if refs is None:
        return None

    if embedding is None:
        embedding = get_embedding(interaction.summary)
    if embedding is None:
        return None

    vec = np.array(embedding)
    scores = {label: cosine_similarity(vec, ref_vec) for label, ref_vec in refs.items()}

    task_score = max(
        scores.get("task", 0), scores.get("followup", 0), scores.get("promise", 0)
    )
    waiting_score = scores.get("waiting", 0)
    not_task_score = scores.get("not_task", 0)

    status = None
    if waiting_score > task_score and waiting_score - not_task_score > TASK_MARGIN:
        status = Task.Status.WAITING
    elif task_score - not_task_score > TASK_MARGIN:
        status = Task.Status.PENDING

    result = None
    if status is not None:
        extracted = _extract_title_and_date(interaction)
        due_date = _parse_due_date(extracted.get("due_date"))

        task = Task.objects.create(
            fc=interaction.fc,
            contact=interaction.contact,
            title=extracted["title"],
            description=interaction.summary,
            due_date=due_date,
            status=status,
            source=Task.Source.AI_EXTRACTED,
        )
        task.source_interactions.add(interaction)
        result = task

    interaction.task_checked = True
    interaction.save(update_fields=["task_checked"])
    return result


def detect_tasks_batch(interactions, embeddings=None):
    """Batch detect tasks. Calls LLM per detected task."""
    from contacts.models import Interaction, Task

    if not interactions:
        return []

    refs = get_task_vectors()
    if refs is None:
        return []

    if embeddings is None:
        texts = [i.summary for i in interactions]
        emb_list = get_embeddings_batch(texts)
    else:
        emb_list = list(embeddings)

    tasks = []
    checked_interactions = []

    for interaction, emb in zip(interactions, emb_list):
        if emb is None:
            continue

        vec = np.array(emb)
        scores = {
            label: cosine_similarity(vec, ref_vec) for label, ref_vec in refs.items()
        }

        task_score = max(
            scores.get("task", 0), scores.get("followup", 0), scores.get("promise", 0)
        )
        waiting_score = scores.get("waiting", 0)
        not_task_score = scores.get("not_task", 0)

        status = None
        if waiting_score > task_score and waiting_score - not_task_score > TASK_MARGIN:
            status = Task.Status.WAITING
        elif task_score - not_task_score > TASK_MARGIN:
            status = Task.Status.PENDING

        if status is not None:
            extracted = _extract_title_and_date(interaction)
            due_date = _parse_due_date(extracted.get("due_date"))

            task = Task.objects.create(
                fc=interaction.fc,
                contact=interaction.contact,
                title=extracted["title"],
                description=interaction.summary,
                due_date=due_date,
                status=status,
                source=Task.Source.AI_EXTRACTED,
            )
            task.source_interactions.add(interaction)
            tasks.append(task)

        interaction.task_checked = True
        checked_interactions.append(interaction)

    if checked_interactions:
        Interaction.objects.bulk_update(checked_interactions, ["task_checked"])

    return tasks
