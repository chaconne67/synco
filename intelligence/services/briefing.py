from common.claude import call_claude_json


def generate_dashboard_briefing(fc, meetings, attention_contacts):
    """Generate personal-secretary style AI briefing for FC dashboard.

    Returns a Brief object or None on failure.
    """
    from intelligence.models import Brief

    if not meetings and not attention_contacts:
        return None

    # Build context
    meeting_lines = []
    meeting_contact = None
    for m in meetings:
        c = m.contact
        if meeting_contact is None:
            meeting_contact = c
        meeting_lines.append(
            f"- {m.scheduled_at.strftime('%H:%M')} {c.name} ({c.company_name}) "
            f"업종:{c.industry or '미상'} 매출:{c.revenue_range or '미상'}"
        )

    attention_lines = []
    for c in attention_contacts[:5]:
        attention_lines.append(
            f"- {c.tier_emoji} {c.name} ({c.company_name}) — {c.health_detail}"
        )

    prompt = f"""당신은 보험설계사(FC)의 개인 비서입니다. 오늘의 브리핑을 작성해주세요.

**오늘 미팅:**
{chr(10).join(meeting_lines) or "없음"}

**주의 필요 고객:**
{chr(10).join(attention_lines) or "없음"}

다음 JSON 형식으로 브리핑을 작성해:
{{
  "company_analysis": "첫 번째 미팅 고객 기업에 대한 핵심 분석 (2-3문장, 비서가 브리핑하듯 자연스러운 말투)",
  "action_suggestion": "오늘 해야 할 핵심 행동 제안 (구체적으로)",
  "insights": {{
    "type": "기회/새 소식/리마인드 중 하나",
    "news": [{{"company": "회사명", "contact_name": "이름", "summary": "소식 요약"}}],
    "reminders": [{{"contact_name": "이름", "company": "회사명", "message": "리마인드 내용"}}]
  }}
}}

원칙:
- 비서가 아침에 일정 브리핑하는 톤 (존대, 간결)
- 미팅 고객 기업 정보를 미리 알려주는 느낌
- 주의 필요 고객 중 중요한 것 리마인드에 포함

JSON으로만 응답."""

    try:
        result = call_claude_json(prompt, timeout=60)
    except Exception:
        return None

    if not meeting_contact and attention_contacts:
        meeting_contact = attention_contacts[0]

    if not meeting_contact:
        return None

    brief = Brief.objects.create(
        contact=meeting_contact,
        fc=fc,
        company_analysis=result.get("company_analysis", ""),
        action_suggestion=result.get("action_suggestion", ""),
        insights=result.get("insights", {}),
    )

    return brief
