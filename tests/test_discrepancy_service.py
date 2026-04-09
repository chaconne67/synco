import pytest
from django.core.management import call_command
from django.utils import timezone

from candidates.models import Candidate, Career, DiscrepancyReport, Education
from candidates.services.discrepancy import scan_candidate_discrepancies


@pytest.mark.django_db
def test_scan_candidate_discrepancies_creates_overlap_and_future_alerts(monkeypatch):
    monkeypatch.setattr(
        timezone, "localdate", lambda: timezone.datetime(2026, 4, 3).date()
    )
    candidate = Candidate.objects.create(name="김후보", total_experience_years=4)
    Career.objects.create(
        candidate=candidate,
        company="첫회사",
        start_date="2023-01",
        end_date="2024-12",
    )
    Career.objects.create(
        candidate=candidate,
        company="둘째회사",
        start_date="2024-06",
        end_date="2029-04",
    )

    report = scan_candidate_discrepancies(candidate)

    assert report.report_type == DiscrepancyReport.ReportType.SELF_CONSISTENCY
    assert report.total_alert_count == 2
    assert report.yellow_alert_count == 2
    assert any(alert["type"] == "OVERLAP" for alert in report.alerts)
    assert any(alert["type"] == "FUTURE_DATE" for alert in report.alerts)
    assert not any(alert["type"] == "EXPERIENCE_MISMATCH" for alert in report.alerts)


@pytest.mark.django_db
def test_scan_candidate_discrepancies_ignores_one_month_overlap(monkeypatch):
    monkeypatch.setattr(
        timezone, "localdate", lambda: timezone.datetime(2026, 4, 3).date()
    )
    candidate = Candidate.objects.create(name="한달중복", total_experience_years=4)
    Career.objects.create(
        candidate=candidate,
        company="첫회사",
        start_date="2023-01",
        end_date="2024-06",
    )
    Career.objects.create(
        candidate=candidate,
        company="둘째회사",
        start_date="2024-06",
        end_date="2025-12",
    )

    report = scan_candidate_discrepancies(candidate)

    assert not any(alert["type"] == "OVERLAP" for alert in report.alerts)


@pytest.mark.django_db
def test_scan_candidate_discrepancies_ignores_same_company_overlap(monkeypatch):
    monkeypatch.setattr(
        timezone, "localdate", lambda: timezone.datetime(2026, 4, 3).date()
    )
    candidate = Candidate.objects.create(name="부서이동", total_experience_years=10)
    Career.objects.create(
        candidate=candidate,
        company="KGI Securities",
        position="Head of Business Promotion Department",
        department="Business Promotion Department",
        start_date="2000-08",
        end_date="2005-03",
    )
    Career.objects.create(
        candidate=candidate,
        company="KGI Securities",
        position="Head of Management Supporting Office",
        department="Management Supporting Office",
        start_date="2002-04",
        end_date="2008-03",
    )

    report = scan_candidate_discrepancies(candidate)

    assert not any(alert["type"] == "OVERLAP" for alert in report.alerts)


@pytest.mark.django_db
def test_scan_candidate_discrepancies_marks_same_role_same_company_overlap_as_reference(
    monkeypatch,
):
    monkeypatch.setattr(
        timezone, "localdate", lambda: timezone.datetime(2026, 4, 3).date()
    )
    candidate = Candidate.objects.create(name="중복기재", total_experience_years=10)
    Career.objects.create(
        candidate=candidate,
        company="KGI Securities",
        position="Assistant Manager",
        department="Research Department",
        start_date="1994-09",
        end_date="1996-12",
    )
    Career.objects.create(
        candidate=candidate,
        company="KGI Securities",
        position="Assistant Manager",
        department="Research Department",
        start_date="1995-01",
        end_date="1997-01",
    )

    report = scan_candidate_discrepancies(candidate)

    overlap = next(alert for alert in report.alerts if alert["type"] == "OVERLAP")
    assert overlap["severity"] == "BLUE"
    assert (
        overlap["evidence"]["examples"][0]["reason"] == "same_company_same_role_overlap"
    )


@pytest.mark.django_db
def test_scan_candidate_discrepancies_downgrades_short_cross_company_overlap(
    monkeypatch,
):
    monkeypatch.setattr(
        timezone, "localdate", lambda: timezone.datetime(2026, 4, 3).date()
    )
    candidate = Candidate.objects.create(name="짧은이직중복", total_experience_years=10)
    Career.objects.create(
        candidate=candidate,
        company="첫회사",
        start_date="2023-01",
        end_date="2024-12",
    )
    Career.objects.create(
        candidate=candidate,
        company="둘째회사",
        start_date="2024-10",
        end_date="2025-12",
    )

    report = scan_candidate_discrepancies(candidate)

    overlap = next(alert for alert in report.alerts if alert["type"] == "OVERLAP")
    assert overlap["severity"] == "BLUE"
    assert (
        overlap["evidence"]["examples"][0]["reason"]
        == "short_cross_company_transition_overlap"
    )


@pytest.mark.django_db
def test_scan_candidate_discrepancies_detects_education_issues():
    candidate = Candidate.objects.create(name="이학력", birth_year=1995)
    Education.objects.create(
        candidate=candidate,
        institution="조기대학",
        degree="학사",
        start_year=2008,
        end_year=2012,
    )
    Education.objects.create(
        candidate=candidate,
        institution="대학원",
        degree="석사",
        end_year=2020,
    )

    report = scan_candidate_discrepancies(candidate)

    assert any(alert["type"] == "AGE_MISMATCH" for alert in report.alerts)
    assert not any(alert["type"] == "INCOMPLETE_DATES" for alert in report.alerts)


@pytest.mark.django_db
def test_scan_candidate_discrepancies_allows_high_school_starting_at_age_fifteen():
    candidate = Candidate.objects.create(name="정상고교", birth_year=1990)
    Education.objects.create(
        candidate=candidate,
        institution="동지고등학교",
        degree="고등학교",
        start_year=2005,
        end_year=2008,
    )

    report = scan_candidate_discrepancies(candidate)

    assert not any(alert["type"] == "AGE_MISMATCH" for alert in report.alerts)


@pytest.mark.django_db
def test_scan_candidate_discrepancies_marks_early_undergraduate_entry_as_reference():
    candidate = Candidate.objects.create(name="조기대입", birth_year=1990)
    Education.objects.create(
        candidate=candidate,
        institution="한양대학교",
        degree="학사",
        start_year=2006,
        end_year=2010,
    )

    report = scan_candidate_discrepancies(candidate)

    age_alert = next(
        alert for alert in report.alerts if alert["type"] == "AGE_MISMATCH"
    )
    assert age_alert["severity"] == "BLUE"
    assert "대학교 입학 시점" in age_alert["detail"]


@pytest.mark.django_db
def test_scan_candidate_discrepancies_keeps_strong_education_age_mismatch_as_warning():
    candidate = Candidate.objects.create(name="비정상대입", birth_year=1995)
    Education.objects.create(
        candidate=candidate,
        institution="조기대학",
        degree="학사",
        start_year=2008,
        end_year=2012,
    )

    report = scan_candidate_discrepancies(candidate)

    age_alert = next(
        alert for alert in report.alerts if alert["type"] == "AGE_MISMATCH"
    )
    assert age_alert["severity"] == "YELLOW"


@pytest.mark.django_db
def test_scan_discrepancies_command_creates_report(monkeypatch):
    monkeypatch.setattr(
        timezone, "localdate", lambda: timezone.datetime(2026, 4, 3).date()
    )
    candidate = Candidate.objects.create(name="커맨드대상", total_experience_years=1)
    Career.objects.create(
        candidate=candidate,
        company="오타회사",
        start_date="2026-05",
        end_date="2026-06",
    )

    call_command("scan_discrepancies", "--candidate-id", str(candidate.pk))

    report = candidate.discrepancy_reports.get()
    assert report.report_type == DiscrepancyReport.ReportType.SELF_CONSISTENCY
    assert any(alert["type"] == "FUTURE_DATE" for alert in report.alerts)


@pytest.mark.django_db
def test_scan_candidate_discrepancies_downgrades_small_future_date_to_reference(
    monkeypatch,
):
    monkeypatch.setattr(
        timezone, "localdate", lambda: timezone.datetime(2026, 4, 3).date()
    )
    candidate = Candidate.objects.create(name="작은미래")
    Career.objects.create(
        candidate=candidate,
        company="가까운미래회사",
        start_date="2024-01",
        end_date="2026-05",
    )

    report = scan_candidate_discrepancies(candidate)

    future_alert = next(
        alert for alert in report.alerts if alert["type"] == "FUTURE_DATE"
    )
    assert future_alert["severity"] == "BLUE"
    assert future_alert["evidence"]["applied_exception"] == "near_future_date"


@pytest.mark.django_db
def test_scan_candidate_discrepancies_applies_career_confidence_gate(monkeypatch):
    monkeypatch.setattr(
        timezone, "localdate", lambda: timezone.datetime(2026, 4, 3).date()
    )
    candidate = Candidate.objects.create(
        name="낮은신뢰도경력",
        field_confidences={"careers": 0.4},
    )
    Career.objects.create(
        candidate=candidate,
        company="첫회사",
        start_date="2023-01",
        end_date="2024-12",
    )
    Career.objects.create(
        candidate=candidate,
        company="둘째회사",
        start_date="2024-06",
        end_date="2026-12",
    )

    report = scan_candidate_discrepancies(candidate)

    overlap = next(alert for alert in report.alerts if alert["type"] == "OVERLAP")
    assert overlap["severity"] == "BLUE"
    assert overlap["confidence_gate"]["downgraded"] is True


@pytest.mark.django_db
def test_scan_candidate_discrepancies_applies_education_confidence_gate():
    candidate = Candidate.objects.create(
        name="낮은신뢰도학력",
        birth_year=1995,
        field_confidences={"educations": 0.4},
    )
    Education.objects.create(
        candidate=candidate,
        institution="조기대학",
        degree="학사",
        start_year=2008,
        end_year=2012,
    )

    report = scan_candidate_discrepancies(candidate)

    age_alert = next(
        alert for alert in report.alerts if alert["type"] == "AGE_MISMATCH"
    )
    assert age_alert["severity"] == "BLUE"
    assert age_alert["confidence_gate"]["downgraded"] is True


@pytest.mark.django_db
def test_scan_candidate_discrepancies_uses_resume_reference_date_for_experience_total(
    monkeypatch,
):
    monkeypatch.setattr(
        timezone, "localdate", lambda: timezone.datetime(2026, 4, 3).date()
    )
    candidate = Candidate.objects.create(
        name="기준일후보",
        total_experience_years=10,
        resume_reference_date="2021-12",
        resume_reference_date_source=Candidate.ResumeReferenceDateSource.FILE_MODIFIED_TIME,
    )
    Career.objects.create(
        candidate=candidate,
        company="첫회사",
        start_date="2012-01",
        end_date="2016-12",
    )
    Career.objects.create(
        candidate=candidate,
        company="현재회사",
        start_date="2017-01",
        end_date="",
        is_current=True,
    )

    report = scan_candidate_discrepancies(candidate)

    assert all(alert["type"] != "EXPERIENCE_MISMATCH" for alert in report.alerts)


@pytest.mark.django_db
def test_scan_candidate_discrepancies_ignores_small_experience_gap(monkeypatch):
    monkeypatch.setattr(
        timezone, "localdate", lambda: timezone.datetime(2026, 4, 3).date()
    )
    candidate = Candidate.objects.create(name="작은차이", total_experience_years=10)
    Career.objects.create(
        candidate=candidate,
        company="현재회사",
        start_date="2016-08",
        end_date="",
        is_current=True,
    )

    report = scan_candidate_discrepancies(candidate)

    assert not any(alert["type"] == "EXPERIENCE_MISMATCH" for alert in report.alerts)


@pytest.mark.django_db
def test_scan_candidate_discrepancies_downgrades_experience_mismatch_when_latest_career_missing_end_date(
    monkeypatch,
):
    monkeypatch.setattr(
        timezone, "localdate", lambda: timezone.datetime(2026, 4, 3).date()
    )
    candidate = Candidate.objects.create(name="종료일누락", total_experience_years=22)
    Career.objects.create(
        candidate=candidate,
        company="오래된회사",
        start_date="1995-07",
        end_date="1996-07",
    )
    Career.objects.create(
        candidate=candidate,
        company="중간회사",
        start_date="2000-08",
        end_date="2001-08",
    )
    Career.objects.create(
        candidate=candidate,
        company="최근회사",
        start_date="2005-07",
        end_date="",
        is_current=False,
    )

    report = scan_candidate_discrepancies(candidate)

    mismatch = next(
        alert for alert in report.alerts if alert["type"] == "EXPERIENCE_MISMATCH"
    )
    assert mismatch["severity"] == "YELLOW"
    assert mismatch["evidence"]["applied_exception"] == "latest_career_missing_end_date"
    assert mismatch["evidence"]["exception_context"]["company"] == "최근회사"
    assert "종료일이 비어 있어" in mismatch["detail"]


@pytest.mark.django_db
def test_scan_candidate_discrepancies_uses_warning_for_boundary_experience_gap(
    monkeypatch,
):
    monkeypatch.setattr(
        timezone, "localdate", lambda: timezone.datetime(2026, 4, 3).date()
    )
    candidate = Candidate.objects.create(name="경계차이", total_experience_years=9)
    Career.objects.create(
        candidate=candidate,
        company="첫회사",
        start_date="2020-01",
        end_date="2021-12",
    )
    Career.objects.create(
        candidate=candidate,
        company="둘째회사",
        start_date="2022-01",
        end_date="2023-12",
    )
    Career.objects.create(
        candidate=candidate,
        company="현재회사",
        start_date="2024-01",
        end_date="",
        is_current=True,
    )

    report = scan_candidate_discrepancies(candidate)

    mismatch = next(
        alert for alert in report.alerts if alert["type"] == "EXPERIENCE_MISMATCH"
    )
    assert mismatch["severity"] == "YELLOW"


@pytest.mark.django_db
def test_scan_candidate_discrepancies_downgrades_experience_mismatch_when_ignored_careers_exist(
    monkeypatch,
):
    monkeypatch.setattr(
        timezone, "localdate", lambda: timezone.datetime(2026, 4, 3).date()
    )
    candidate = Candidate.objects.create(name="누락경력반영", total_experience_years=12)
    Career.objects.create(
        candidate=candidate,
        company="첫회사",
        start_date="2018-01",
        end_date="2020-12",
    )
    Career.objects.create(
        candidate=candidate,
        company="둘째회사",
        start_date="2021-01",
        end_date="2022-12",
    )
    Career.objects.create(
        candidate=candidate,
        company="누락회사",
        start_date="미정",
        end_date="2024-06",
    )

    report = scan_candidate_discrepancies(candidate)

    mismatch = next(
        alert for alert in report.alerts if alert["type"] == "EXPERIENCE_MISMATCH"
    )
    assert mismatch["severity"] == "YELLOW"
    assert (
        mismatch["evidence"]["applied_exception"]
        == "ignored_career_in_total_experience"
    )
    assert "계산에서 제외" in mismatch["detail"]
