import logging

from common.claude import call_claude_json

logger = logging.getLogger(__name__)


def generate_summary(contact) -> str:
    """One-paragraph relationship summary via LLM. Timeout 60s.
    Returns empty string on failure."""
    interactions = list(
        contact.interactions.order_by("-created_at")[:30].values(
            "type", "summary", "sentiment", "created_at"
        )
    )
    from meetings.models import Meeting

    meetings_data = list(
        Meeting.objects.filter(contact=contact, fc=contact.fc)
        .order_by("-scheduled_at")[:10]
        .values("title", "scheduled_at", "status")
    )

    interaction_lines = []
    for i in interactions:
        date_str = i["created_at"].strftime("%Y-%m-%d")
        sentiment_str = f" [{i['sentiment']}]" if i["sentiment"] else ""
        interaction_lines.append(f"- {date_str} ({i['type']}{sentiment_str}): {i['summary'][:150]}")

    meeting_lines = []
    for m in meetings_data:
        date_str = m["scheduled_at"].strftime("%Y-%m-%d")
        meeting_lines.append(f"- {date_str} [{m['status']}]: {m['title']}")

    prompt = f"""아래 고객과 FC(보험설계사)의 관계를 한 문단으로 요약해.

**고객:** {contact.name} ({contact.company_name}, {contact.industry or '업종미상'}, {contact.region or '지역미상'})
**메모:** {(contact.memo or '')[:200]}

**인터랙션 ({len(interactions)}건):**
{chr(10).join(interaction_lines) or '없음'}

**미팅 ({len(meetings_data)}건):**
{chr(10).join(meeting_lines) or '없음'}

JSON으로 응답: {{"summary": "한 문단 요약"}}"""

    try:
        result = call_claude_json(prompt, timeout=60)
        return result.get("summary", "")
    except Exception:
        logger.exception("generate_summary failed for contact %s", contact.pk)
        return ""


def generate_insights(contact) -> list[dict]:
    """Extract fortunate insights via LLM. Timeout 60s.
    Returns list of {"reason": "...", "type": "..."} or empty list on failure."""
    interactions = list(
        contact.interactions.order_by("-created_at")[:20].values(
            "type", "summary", "created_at"
        )
    )

    interaction_lines = []
    for i in interactions:
        date_str = i["created_at"].strftime("%Y-%m-%d")
        interaction_lines.append(f"- {date_str} ({i['type']}): {i['summary'][:150]}")

    prompt = f"""아래 고객 정보에서 FC(보험설계사)가 활용할 수 있는 기회 신호를 추출해.

**고객:** {contact.name} ({contact.company_name}, {contact.industry or '업종미상'})
**메모:** {(contact.memo or '')[:200]}

**인터랙션:**
{chr(10).join(interaction_lines) or '없음'}

기회 신호 예시: 승진, 경조사, 사업 확장, 신규 프로젝트, 계약 갱신 시기

JSON으로 응답:
[{{"reason": "유망한 이유", "type": "personal_event/promotion/business_opportunity"}}]

신호가 없으면 빈 배열 []을 반환."""

    try:
        result = call_claude_json(prompt, timeout=60)
        if isinstance(result, list):
            return result
        return []
    except Exception:
        logger.exception("generate_insights failed for contact %s", contact.pk)
        return []
