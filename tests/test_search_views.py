import json
from unittest.mock import patch

import pytest
from django.contrib.auth import get_user_model
from django.test import Client

from candidates.models import (
    Candidate,
    Career,
    Category,
    DiscrepancyReport,
    ExtractionLog,
    Resume,
    SearchSession,
    SearchTurn,
    ValidationDiagnosis,
)

User = get_user_model()


@pytest.fixture
def user(db):
    return User.objects.create_user(username="tester", password="test1234")


@pytest.fixture
def auth_client(user):
    client = Client()
    client.login(username="tester", password="test1234")
    return client


@pytest.fixture
def category(db):
    return Category.objects.create(name="Accounting", name_ko="회계")


@pytest.fixture
def candidate(db, category):
    c = Candidate.objects.create(
        name="강솔찬",
        current_company="현대엠시트",
        total_experience_years=12,
        primary_category=category,
    )
    c.categories.add(category)
    return c


@pytest.mark.django_db
def test_candidate_list_page(auth_client, candidate):
    resp = auth_client.get("/candidates/")
    assert resp.status_code == 200
    assert "강솔찬" in resp.content.decode()


@pytest.mark.django_db
def test_candidate_list_filter_category(auth_client, candidate, category):
    resp = auth_client.get(f"/candidates/?category={category.name}")
    assert resp.status_code == 200
    assert "강솔찬" in resp.content.decode()


@pytest.mark.django_db
def test_candidate_list_filter_category_htmx_renders_active_tab(
    auth_client, candidate, category
):
    resp = auth_client.get(
        f"/candidates/?category={category.name}",
        HTTP_HX_REQUEST="true",
        HTTP_HX_TARGET="main-content",
    )
    body = resp.content.decode()

    assert resp.status_code == 200
    assert 'hx-get="/candidates/?category=Accounting"' in body
    assert "bg-primary text-white" in body


@pytest.mark.django_db
def test_candidate_detail_page(auth_client, candidate):
    resp = auth_client.get(f"/candidates/{candidate.pk}/")
    assert resp.status_code == 200
    assert "강솔찬" in resp.content.decode()


@pytest.mark.django_db
def test_candidate_detail_uses_current_resume_diagnosis(auth_client, category):
    candidate = Candidate.objects.create(
        name="진단기준",
        birth_year=1990,
        primary_category=category,
    )
    old_resume = Resume.objects.create(
        candidate=candidate,
        file_name="old.pdf",
        drive_file_id="old_resume",
        drive_folder="Accounting",
        is_primary=True,
        version=1,
        processing_status=Resume.ProcessingStatus.PARSED,
    )
    current_resume = Resume.objects.create(
        candidate=candidate,
        file_name="current.pdf",
        drive_file_id="current_resume",
        drive_folder="Accounting",
        is_primary=False,
        version=2,
        processing_status=Resume.ProcessingStatus.PARSED,
    )
    candidate.current_resume = current_resume
    candidate.save(update_fields=["current_resume", "updated_at"])
    ValidationDiagnosis.objects.create(
        candidate=candidate,
        resume=current_resume,
        attempt_number=1,
        verdict="fail",
        overall_score=0.5,
        issues=[{"type": "hallucinated", "field": "birth_year"}],
        field_scores={},
        retry_action="human_review",
    )
    ValidationDiagnosis.objects.create(
        candidate=candidate,
        resume=old_resume,
        attempt_number=1,
        verdict="pass",
        overall_score=1.0,
        issues=[],
        field_scores={},
        retry_action="none",
    )

    resp = auth_client.get(f"/candidates/{candidate.pk}/")
    body = resp.content.decode()

    assert resp.status_code == 200
    assert "AI 생성" in body


@pytest.mark.django_db
def test_candidate_detail_page_shows_discrepancy_details(auth_client, candidate):
    DiscrepancyReport.objects.create(
        candidate=candidate,
        report_type=DiscrepancyReport.ReportType.SELF_CONSISTENCY,
        integrity_score=0.82,
        summary="주의 1건. 학력 시작 시점 확인 필요",
        alerts=[
            {
                "type": "AGE_MISMATCH",
                "severity": "YELLOW",
                "field": "educations",
                "layer": "self_consistency",
                "detail": "동지고등학교 시작 시점 추정 나이 14세로 비정상적으로 이릅니다.",
            }
        ],
    )

    resp = auth_client.get(f"/candidates/{candidate.pk}/")
    body = resp.content.decode()

    assert resp.status_code == 200
    assert "검토 사항" in body
    assert "주의 1건" in body
    assert "동지고등학교 시작 시점 추정 나이 14세로 비정상적으로 이릅니다." in body


@pytest.mark.django_db
def test_candidate_detail_page_shows_experience_review_section_without_report(
    auth_client, category
):
    candidate = Candidate.objects.create(
        name="김재환",
        current_company="Dow Corning Korea",
        total_experience_years=8,
        primary_category=category,
    )
    candidate.categories.add(category)
    Career.objects.create(
        candidate=candidate,
        company="Dow Corning Korea",
        start_date="2018-01",
        end_date="",
        is_current=True,
    )
    Career.objects.create(
        candidate=candidate,
        company="Incomplete Corp",
        start_date="2014-03",
        end_date="",
        is_current=False,
    )

    resp = auth_client.get(f"/candidates/{candidate.pk}/")
    body = resp.content.decode()

    assert resp.status_code == 200
    assert "검토 사항" in body
    assert "참고 1건" in body
    assert "날짜와 기간 정보가 모두 부족한 경력 1건은 총 경력 계산에서 제외했습니다." in body


@pytest.mark.django_db
def test_review_detail_uses_current_resume_raw_text(auth_client, category):
    candidate = Candidate.objects.create(
        name="리뷰기준",
        raw_text="",
        primary_category=category,
    )
    Resume.objects.create(
        candidate=candidate,
        file_name="old.pdf",
        drive_file_id="review_old",
        drive_folder="Accounting",
        is_primary=True,
        version=1,
        processing_status=Resume.ProcessingStatus.PARSED,
        raw_text="이전 원문",
    )
    current_resume = Resume.objects.create(
        candidate=candidate,
        file_name="current.pdf",
        drive_file_id="review_current",
        drive_folder="Accounting",
        is_primary=False,
        version=2,
        processing_status=Resume.ProcessingStatus.PARSED,
        raw_text="현재 원문",
    )
    candidate.current_resume = current_resume
    candidate.save(update_fields=["current_resume", "updated_at"])

    resp = auth_client.get(f"/candidates/review/{candidate.pk}/")
    body = resp.content.decode()

    assert resp.status_code == 200
    assert "현재 원문" in body
    assert "이전 원문" not in body


@pytest.mark.django_db
def test_review_confirm_logs_current_resume(auth_client, category):
    candidate = Candidate.objects.create(
        name="확인로그",
        primary_category=category,
        validation_status=Candidate.ValidationStatus.NEEDS_REVIEW,
    )
    current_resume = Resume.objects.create(
        candidate=candidate,
        file_name="current.pdf",
        drive_file_id="confirm_current",
        drive_folder="Accounting",
        is_primary=True,
        version=1,
        processing_status=Resume.ProcessingStatus.PARSED,
    )
    candidate.current_resume = current_resume
    candidate.save(update_fields=["current_resume", "updated_at"])

    resp = auth_client.post(f"/candidates/review/{candidate.pk}/confirm/")

    log = ExtractionLog.objects.order_by("-created_at").first()
    candidate.refresh_from_db()
    assert resp.status_code == 204
    assert candidate.validation_status == Candidate.ValidationStatus.CONFIRMED
    assert log.resume == current_resume


@pytest.mark.django_db
def test_review_reject_logs_current_resume(auth_client, category):
    candidate = Candidate.objects.create(
        name="반려로그",
        primary_category=category,
        validation_status=Candidate.ValidationStatus.NEEDS_REVIEW,
    )
    current_resume = Resume.objects.create(
        candidate=candidate,
        file_name="current.pdf",
        drive_file_id="reject_current",
        drive_folder="Accounting",
        is_primary=True,
        version=1,
        processing_status=Resume.ProcessingStatus.PARSED,
    )
    candidate.current_resume = current_resume
    candidate.save(update_fields=["current_resume", "updated_at"])

    resp = auth_client.post(
        f"/candidates/review/{candidate.pk}/reject/",
        {"reason": "정보 불충분"},
    )

    log = ExtractionLog.objects.order_by("-created_at").first()
    candidate.refresh_from_db()
    assert resp.status_code == 204
    assert candidate.validation_status == Candidate.ValidationStatus.FAILED
    assert log.resume == current_resume


@pytest.mark.django_db
def test_candidate_list_page_shows_discrepancy_badge(auth_client, candidate):
    DiscrepancyReport.objects.create(
        candidate=candidate,
        report_type=DiscrepancyReport.ReportType.SELF_CONSISTENCY,
        integrity_score=0.82,
        summary="주의 1건. 총 경력 차이 확인 필요",
        alerts=[
            {
                "type": "EXPERIENCE_MISMATCH",
                "severity": "YELLOW",
                "field": "total_experience_years",
                "layer": "self_consistency",
                "detail": "이력서 표기 12년과 경력 합산 10년 차이",
            }
        ],
    )

    resp = auth_client.get("/candidates/")
    body = resp.content.decode()

    assert resp.status_code == 200
    assert "주의 1건" in body
    assert "이력서 표기" in body
    assert "12년" in body
    assert "경력 합산" in body
    assert "10년" in body
    assert "차이" in body


@pytest.mark.django_db
def test_candidate_list_page_shows_experience_review_detail_without_report(
    auth_client, category
):
    candidate = Candidate.objects.create(
        name="김재환",
        current_company="Dow Corning Korea",
        total_experience_years=8,
        primary_category=category,
    )
    candidate.categories.add(category)
    Career.objects.create(
        candidate=candidate,
        company="Dow Corning Korea",
        start_date="2018-01",
        end_date="",
        is_current=True,
    )
    Career.objects.create(
        candidate=candidate,
        company="Incomplete Corp",
        start_date="2014-03",
        end_date="",
        is_current=False,
    )

    resp = auth_client.get("/candidates/")
    body = resp.content.decode()

    assert resp.status_code == 200
    assert "참고 1건" in body
    assert "불완전 경력 제외 1건" in body


@pytest.mark.django_db
def test_login_required(client):
    resp = client.get("/candidates/")
    assert resp.status_code == 302


@pytest.mark.django_db
def test_candidate_list_reapplies_structured_session_filters(auth_client, user, category):
    matching = Candidate.objects.create(
        name="강솔찬",
        current_company="현대엠시트",
        total_experience_years=12,
        primary_category=category,
    )
    matching.categories.add(category)

    other_category = Category.objects.create(name="HR", name_ko="인사")
    other = Candidate.objects.create(
        name="박민수",
        current_company="네이버",
        total_experience_years=6,
        primary_category=other_category,
    )
    other.categories.add(other_category)

    session = SearchSession.objects.create(
        user=user,
        current_filters={
            "category": "Accounting",
            "min_experience_years": 10,
        },
    )
    SearchTurn.objects.create(
        session=session,
        turn_number=1,
        user_text="회계 10년 이상",
        ai_response="회계 카테고리 10년 이상 후보자를 찾았습니다.",
        filters_applied=session.current_filters,
        result_count=1,
    )

    resp = auth_client.get(f"/candidates/?session_id={session.pk}")
    body = resp.content.decode()

    assert resp.status_code == 200
    assert "강솔찬" in body
    assert "박민수" not in body


@pytest.mark.django_db
@patch("candidates.views.parse_and_search")
def test_search_chat_saves_structured_filters(mock_parse, auth_client):
    mock_parse.return_value = {
        "candidates": [],
        "filters": {
            "category": "Accounting",
            "company_keywords": ["삼성"],
            "keyword": None,
        },
        "ai_message": "회계 카테고리에서 삼성 경력자를 찾았습니다.",
        "is_valid": True,
        "result_count": 3,
    }

    resp = auth_client.post(
        "/candidates/search/",
        data=json.dumps({"message": "회계 중 삼성 경력자"}),
        content_type="application/json",
    )

    assert resp.status_code == 200
    session = SearchSession.objects.get()
    assert session.current_filters["category"] == "Accounting"
    assert session.current_filters["company_keywords"] == ["삼성"]
