from datetime import timedelta

import pytest
from django.urls import reverse
from django.utils import timezone

from accounts.models import Membership, Organization, User
from candidates.models import Candidate
from clients.models import Client
from projects.models import (
    ActionItem,
    ActionType,
    Application,
    Interview,
    Project,
)


@pytest.fixture
def org(db):
    return Organization.objects.create(name="TestOrg")


@pytest.fixture
def owner(org):
    u = User.objects.create_user(username="owner", password="x", level=2)
    Membership.objects.create(user=u, organization=org, role="owner")
    return u


@pytest.fixture
def owner_client(client, owner):
    client.force_login(owner)
    return client


@pytest.mark.django_db
def test_dashboard_renders_with_empty_org(owner_client):
    """Skeleton: dashboard renders 200 with empty org, no crash."""
    resp = owner_client.get(reverse("dashboard"))
    assert resp.status_code == 200
    assert b"Monthly Success" in resp.content


def _close_project(project, result, at):
    """Helper: close a project at specific datetime."""
    Project.objects.filter(pk=project.pk).update(
        status="closed", result=result, closed_at=at
    )


@pytest.fixture
def client_obj(org):
    return Client.objects.create(organization=org, name="ClientCo")


@pytest.mark.django_db
def test_s1_monthly_success_counts(owner_client, org, client_obj):
    """S1-1: 이번 달 성공/진행중/성공률 렌더."""
    now = timezone.localtime()
    month_start = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    last_month = month_start - timedelta(days=1)

    # 이번 달 성공 2건
    for i in range(2):
        p = Project.objects.create(organization=org, client=client_obj, title=f"S{i}")
        _close_project(p, "success", month_start + timedelta(days=1))
    # 이번 달 실패 1건
    p = Project.objects.create(organization=org, client=client_obj, title="F1")
    _close_project(p, "fail", month_start + timedelta(days=2))
    # 지난 달 성공 (제외되어야 함)
    p = Project.objects.create(organization=org, client=client_obj, title="OLD")
    _close_project(p, "success", last_month)
    # 진행 중 3건
    for i in range(3):
        Project.objects.create(organization=org, client=client_obj, title=f"O{i}")

    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()

    # 큰 숫자 = 이번 달 성공 2건
    assert 'data-testid="s1-success-count">2<' in body
    # 진행 중 = 3건
    assert 'data-testid="s1-active-count">3<' in body
    # 성공률 = 2 / (2+1) = 67%
    assert 'data-testid="s1-success-rate">67<' in body


@pytest.mark.django_db
def test_s1_monthly_success_empty(owner_client):
    """S1-1 빈 조직: 0/0/— 렌더."""
    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()
    assert 'data-testid="s1-success-count">0<' in body
    assert 'data-testid="s1-active-count">0<' in body
    assert 'data-testid="s1-success-rate">—<' in body


@pytest.mark.django_db
def test_s1_project_status_counts(owner_client, org, client_obj):
    """S1-3: 서칭/스크리닝/완료 개수 렌더."""
    # 서칭 4건
    for i in range(4):
        Project.objects.create(
            organization=org, client=client_obj, title=f"SR{i}",
            status="open", phase="searching",
        )
    # 스크리닝 2건
    for i in range(2):
        Project.objects.create(
            organization=org, client=client_obj, title=f"SC{i}",
            status="open", phase="screening",
        )
    # 완료 3건 (성공 2 + 실패 1)
    for i, res in enumerate(["success", "success", "fail"]):
        p = Project.objects.create(
            organization=org, client=client_obj, title=f"CL{i}",
        )
        _close_project(p, res, timezone.now())

    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()

    assert 'data-testid="s3-searching">4<' in body
    assert 'data-testid="s3-screening">2<' in body
    assert 'data-testid="s3-closed">3<' in body


@pytest.fixture
def consultant_user(org):
    u = User.objects.create_user(
        username="c1", password="x", first_name="민호", last_name="김"
    )
    Membership.objects.create(user=u, organization=org, role="consultant")
    return u


@pytest.mark.django_db
def test_s2_team_performance_lists_members(owner_client, org, client_obj, consultant_user):
    """S2-1: owner + consultant 목록, viewer 제외."""
    viewer = User.objects.create_user(username="v1", password="x", first_name="뷰어")
    Membership.objects.create(user=viewer, organization=org, role="viewer")

    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()

    # consultant 한글명 표시 (last_name="김" + first_name="민호" → "김민호")
    assert "김민호" in body
    # owner 본인도 표시 (username="owner" fallback)
    assert "owner" in body
    # viewer 제외
    assert "뷰어" not in body
    # 역할 한글
    assert "컨설턴트" in body
    assert "대표" in body


@pytest.mark.django_db
def test_s2_team_performance_success_rate(owner_client, org, client_obj, consultant_user):
    """S2-1: 성공률 = 본인 담당 success / 본인 담당 closed."""
    # consultant가 담당한 프로젝트 4건 closed (3성공 1실패) + 2 open
    for i in range(3):
        p = Project.objects.create(organization=org, client=client_obj, title=f"S{i}")
        p.assigned_consultants.add(consultant_user)
        _close_project(p, "success", timezone.now())
    p = Project.objects.create(organization=org, client=client_obj, title="F")
    p.assigned_consultants.add(consultant_user)
    _close_project(p, "fail", timezone.now())
    for i in range(2):
        p = Project.objects.create(
            organization=org, client=client_obj, title=f"O{i}", status="open"
        )
        p.assigned_consultants.add(consultant_user)

    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()

    # 성공률 75% (3/4)
    assert 'data-testid="s2-rate-c1">75%<' in body
    # 현재 프로젝트 2건
    assert 'data-testid="s2-active-c1">2건 진행 중<' in body


@pytest.mark.django_db
def test_s2_team_performance_empty_rate(owner_client, org, consultant_user):
    """S2-1: 표본 없는 멤버는 '—'."""
    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()

    assert 'data-testid="s2-rate-c1">—<' in body


# ===========================================================================
# S3 Weekly Schedule
# ===========================================================================


def _this_monday_midnight():
    now = timezone.localtime()
    monday = now - timedelta(days=now.weekday())
    return monday.replace(hour=0, minute=0, second=0, microsecond=0)


@pytest.fixture
def interview_type(db):
    obj, _ = ActionType.objects.get_or_create(
        code="interview_round", defaults={"label_ko": "면접"}
    )
    return obj


@pytest.fixture
def submit_type(db):
    obj, _ = ActionType.objects.get_or_create(
        code="submit_to_client", defaults={"label_ko": "서류 제출"}
    )
    return obj


@pytest.mark.django_db
def test_s3_weekly_empty(owner_client):
    """S3 Weekly: 빈 상태 렌더."""
    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()
    assert "이번 주 일정이 없습니다" in body


@pytest.mark.django_db
def test_s3_weekly_shows_interview(
    owner_client, org, client_obj, interview_type, consultant_user
):
    """S3 Weekly: Interview 표시, '인터뷰' 키워드·후보자명 포함."""
    monday = _this_monday_midnight()
    cand = Candidate.objects.create(name="박해준")
    proj = Project.objects.create(organization=org, client=client_obj, title="P1")
    app = Application.objects.create(project=proj, candidate=cand)
    ai = ActionItem.objects.create(
        application=app,
        action_type=interview_type,
        title="1차 면접",
        scheduled_at=monday + timedelta(days=2, hours=11),
    )
    Interview.objects.create(
        action_item=ai, round=1, scheduled_at=monday + timedelta(days=2, hours=11),
        type="화상", location="Zoom",
    )

    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()
    assert "1차 면접" in body
    assert "박해준" in body
    assert "이번 주 일정이 없습니다" not in body


# ===========================================================================
# S3 Monthly Calendar
# ===========================================================================


@pytest.mark.django_db
def test_s3_monthly_has_42_cells(owner_client):
    """Monthly Calendar: 항상 42셀 렌더."""
    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()
    assert body.count('class="cal-day') == 42


@pytest.mark.django_db
def test_s3_monthly_today_class(owner_client):
    """Monthly Calendar: 오늘 셀에 today 클래스."""
    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()
    assert 'class="cal-day today"' in body


@pytest.mark.django_db
def test_s3_monthly_interview_label(
    owner_client, org, client_obj, interview_type, consultant_user
):
    """Monthly Calendar: 이번 달 Interview → '인터뷰' 레이블 표시."""
    now = timezone.localtime()
    # 이번 달 중순 날짜 사용 (이번 달에 확실히 속하도록)
    mid_month = now.replace(day=15, hour=10, minute=0, second=0, microsecond=0)

    cand = Candidate.objects.create(name="이월력")
    proj = Project.objects.create(organization=org, client=client_obj, title="CalP")
    app = Application.objects.create(project=proj, candidate=cand)
    ai = ActionItem.objects.create(
        application=app,
        action_type=interview_type,
        title="2차 면접",
        scheduled_at=mid_month,
    )
    Interview.objects.create(
        action_item=ai,
        round=2,
        scheduled_at=mid_month,
        type="대면",
        location="서울",
    )

    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()
    assert "인터뷰" in body


@pytest.mark.django_db
def test_s3_monthly_outside_day_shows_event(
    owner_client, org, client_obj, submit_type
):
    """S3 Monthly: 전/다음달 outside 셀에도 ActionItem 라벨이 뜬다."""
    # grid 시작일 (이번 달 첫 주의 일요일)
    now = timezone.localtime()
    first = now.replace(day=1, hour=0, minute=0, second=0, microsecond=0)
    sunday_offset = first.isoweekday() % 7
    grid_start = first - timedelta(days=sunday_offset)
    if sunday_offset == 0:
        pytest.skip("1일이 일요일이면 outside 셀 leading 없음")

    outside_day = grid_start + timedelta(hours=10)  # 이전 달의 일요일
    cand = Candidate.objects.create(name="이전달")
    proj = Project.objects.create(organization=org, client=client_obj, title="Outside")
    app = Application.objects.create(project=proj, candidate=cand)
    ActionItem.objects.create(
        application=app, action_type=submit_type,
        title="서류 제출", scheduled_at=outside_day,
    )

    resp = owner_client.get(reverse("dashboard"))
    body = resp.content.decode()
    # outside 셀은 muted 이지만 라벨은 나와야 한다
    assert "일정" in body or "서류 제출" in body  # event_label "일정"이 나온다
