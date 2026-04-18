from projects.models import CARD_STAGES_ORDER, STAGES_ORDER


def test_card_stages_excludes_sourcing():
    card_ids = [s for s, _ in CARD_STAGES_ORDER]
    assert "sourcing" not in card_ids
    assert len(card_ids) == 7


def test_card_stages_order():
    expected = [
        "contact",
        "resume",
        "pre_meeting",
        "prep_submission",
        "client_submit",
        "interview",
        "hired",
    ]
    assert [s for s, _ in CARD_STAGES_ORDER] == expected


def test_card_stages_labels_match_project_stages():
    """라벨은 프로젝트 레벨 STAGES_ORDER와 동일 (중복 정의 방지)."""
    project_labels = dict(STAGES_ORDER)
    for stage_id, label in CARD_STAGES_ORDER:
        assert label == project_labels[stage_id]
