from projects.models import STAGES_ORDER


def test_stages_order_renamed_labels():
    """3단계 네이밍 변경 — 이력서 관련 3개만 바뀐다."""
    labels = dict(STAGES_ORDER)
    assert labels["resume"] == "이력서 준비"
    assert labels["prep_submission"] == "이력서 작성(제출용)"
    assert labels["client_submit"] == "이력서 제출"


def test_unchanged_labels():
    """나머지 5개 단계 라벨은 유지."""
    labels = dict(STAGES_ORDER)
    assert labels["sourcing"] == "서칭"
    assert labels["contact"] == "접촉"
    assert labels["pre_meeting"] == "사전 미팅"
    assert labels["interview"] == "면접"
    assert labels["hired"] == "입사"
