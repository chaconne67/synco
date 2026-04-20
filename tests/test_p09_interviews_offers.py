"""P09: Interview & Offer tests.

Tests for Interview/Offer CRUD, state transitions, project status
auto-transition, organization isolation, delete protection, and HTMX behavior.
"""

import pytest
from django.test import Client as TestClient
from django.urls import reverse
from django.utils import timezone

from accounts.models import User
from candidates.models import Candidate
from clients.models import Client
from projects.models import (
    Contact,
    Interview,
    Offer,
    Project,
    ProjectStatus,
    Submission)
from projects.services.lifecycle import (
    InvalidTransition,
    accept_offer,
    apply_interview_result,
    is_submission_offer_eligible,
    maybe_advance_to_closed_success,
    maybe_advance_to_interviewing,
    maybe_advance_to_negotiating,
    reject_offer)


# --- Fixtures ---




@pytest.fixture
def user_with_org(db):
    user = User.objects.create_user(username="p09_tester", password="test1234")
    return user


@pytest.fixture
def user_with_org2(db):
    user = User.objects.create_user(username="p09_tester2", password="test1234")
    return user


@pytest.fixture
def auth_client(user_with_org):
    c = TestClient()
    c.login(username="p09_tester", password="test1234")
    return c


@pytest.fixture
def auth_client2(user_with_org2):
    c = TestClient()
    c.login(username="p09_tester2", password="test1234")
    return c


@pytest.fixture
def client_obj(org):
    return Client.objects.create(name="Acme Corp", industry="IT")


@pytest.fixture
def client_obj2(org2):
    return Client.objects.create(
        name="Other Corp", industry="Finance"
    )


@pytest.fixture
def project(client_obj, user_with_org):
    p = Project.objects.create(
        client=client_obj
        title="Interview Test Project",
        created_by=user_with_org,
        status=ProjectStatus.RECOMMENDING)
    p.assigned_consultants.add(user_with_org)
    return p


@pytest.fixture
def project_other_org(client_obj2, user_with_org2):
    return Project.objects.create(
        client=client_obj2
        title="Other Org Project",
        created_by=user_with_org2)


@pytest.fixture
def candidate(org):
    return Candidate.objects.create(name="홍길동")


@pytest.fixture
def candidate2(org):
    return Candidate.objects.create(name="김영희")


@pytest.fixture
def interested_contact(project, candidate, user_with_org):
    return Contact.objects.create(
        project=project,
        candidate=candidate,
        consultant=user_with_org,
        channel=Contact.Channel.PHONE,
        contacted_at=timezone.now(),
        result=Contact.Result.INTERESTED)


@pytest.fixture
def interested_contact2(project, candidate2, user_with_org):
    return Contact.objects.create(
        project=project,
        candidate=candidate2,
        consultant=user_with_org,
        channel=Contact.Channel.EMAIL,
        contacted_at=timezone.now(),
        result=Contact.Result.INTERESTED)


@pytest.fixture
def passed_submission(project, candidate, user_with_org, interested_contact):
    """통과 상태의 Submission."""
    return Submission.objects.create(
        project=project,
        candidate=candidate,
        consultant=user_with_org,
        status=Submission.Status.PASSED,
        submitted_at=timezone.now())


@pytest.fixture
def passed_submission2(project, candidate2, user_with_org, interested_contact2):
    """두 번째 통과 Submission."""
    return Submission.objects.create(
        project=project,
        candidate=candidate2,
        consultant=user_with_org,
        status=Submission.Status.PASSED,
        submitted_at=timezone.now())


@pytest.fixture
def drafting_submission(project, candidate, user_with_org, interested_contact):
    """작성중 상태의 Submission."""
    return Submission.objects.create(
        project=project,
        candidate=candidate,
        consultant=user_with_org,
        status=Submission.Status.DRAFTING)


@pytest.fixture
def interview(passed_submission):
    """1차 면접 (대기 상태)."""
    return Interview.objects.create(
        submission=passed_submission,
        round=1,
        scheduled_at=timezone.now(),
        type=Interview.Type.IN_PERSON)


@pytest.fixture
def passed_interview(passed_submission):
    """1차 면접 (합격 상태)."""
    return Interview.objects.create(
        submission=passed_submission,
        round=1,
        scheduled_at=timezone.now(),
        type=Interview.Type.IN_PERSON,
        result=Interview.Result.PASSED)


@pytest.fixture
def offer(passed_submission, passed_interview):
    """오퍼 (협상중 상태)."""
    return Offer.objects.create(
        submission=passed_submission)


# --- Login Required ---


class TestInterviewLoginRequired:
    """면접 관련 URL 미로그인 시 redirect 검증."""

    def test_tab_requires_login(self, project):
        c = TestClient()
        url = reverse("projects:project_tab_interviews", args=[project.pk])
        resp = c.get(url)
        assert resp.status_code == 302

    def test_create_requires_login(self, project):
        c = TestClient()
        url = reverse("projects:interview_create", args=[project.pk])
        resp = c.get(url)
        assert resp.status_code == 302

    def test_update_requires_login(self, project, interview):
        c = TestClient()
        url = reverse("projects:interview_update", args=[project.pk, interview.pk])
        resp = c.get(url)
        assert resp.status_code == 302

    def test_delete_requires_login(self, project, interview):
        c = TestClient()
        url = reverse("projects:interview_delete", args=[project.pk, interview.pk])
        resp = c.post(url)
        assert resp.status_code == 302

    def test_result_requires_login(self, project, interview):
        c = TestClient()
        url = reverse("projects:interview_result", args=[project.pk, interview.pk])
        resp = c.get(url)
        assert resp.status_code == 302


class TestOfferLoginRequired:
    """오퍼 관련 URL 미로그인 시 redirect 검증."""

    def test_tab_requires_login(self, project):
        c = TestClient()
        url = reverse("projects:project_tab_offers", args=[project.pk])
        resp = c.get(url)
        assert resp.status_code == 302

    def test_create_requires_login(self, project):
        c = TestClient()
        url = reverse("projects:offer_create", args=[project.pk])
        resp = c.get(url)
        assert resp.status_code == 302

    def test_update_requires_login(self, project, offer):
        c = TestClient()
        url = reverse("projects:offer_update", args=[project.pk, offer.pk])
        resp = c.get(url)
        assert resp.status_code == 302

    def test_delete_requires_login(self, project, offer):
        c = TestClient()
        url = reverse("projects:offer_delete", args=[project.pk, offer.pk])
        resp = c.post(url)
        assert resp.status_code == 302

    def test_accept_requires_login(self, project, offer):
        c = TestClient()
        url = reverse("projects:offer_accept", args=[project.pk, offer.pk])
        resp = c.post(url)
        assert resp.status_code == 302

    def test_reject_requires_login(self, project, offer):
        c = TestClient()
        url = reverse("projects:offer_reject", args=[project.pk, offer.pk])
        resp = c.post(url)
        assert resp.status_code == 302


# --- Organization Isolation ---


class TestInterviewOrgIsolation:
    """타 조직 프로젝트의 Interview 접근 시 404."""

    def test_tab_other_org_404(self, auth_client, project_other_org):
        url = reverse("projects:project_tab_interviews", args=[project_other_org.pk])
        resp = auth_client.get(url)
        assert resp.status_code == 404

    def test_create_other_org_404(self, auth_client, project_other_org):
        url = reverse("projects:interview_create", args=[project_other_org.pk])
        resp = auth_client.get(url)
        assert resp.status_code == 404

    def test_update_other_org_404(self, auth_client, project_interview):
        url = reverse(
            "projects:interview_update",
            args=[project_other_org.pk, interview.pk])
        resp = auth_client.get(url)
        assert resp.status_code == 404

    def test_delete_other_org_404(self, auth_client, project_interview):
        url = reverse(
            "projects:interview_delete",
            args=[project_other_org.pk, interview.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 404

    def test_result_other_org_404(self, auth_client, project_interview):
        url = reverse(
            "projects:interview_result",
            args=[project_other_org.pk, interview.pk])
        resp = auth_client.get(url)
        assert resp.status_code == 404


class TestOfferOrgIsolation:
    """타 조직 프로젝트의 Offer 접근 시 404."""

    def test_tab_other_org_404(self, auth_client, project_other_org):
        url = reverse("projects:project_tab_offers", args=[project_other_org.pk])
        resp = auth_client.get(url)
        assert resp.status_code == 404

    def test_create_other_org_404(self, auth_client, project_other_org):
        url = reverse("projects:offer_create", args=[project_other_org.pk])
        resp = auth_client.get(url)
        assert resp.status_code == 404

    def test_update_other_org_404(self, auth_client, project_offer):
        url = reverse(
            "projects:offer_update",
            args=[project_other_org.pk, offer.pk])
        resp = auth_client.get(url)
        assert resp.status_code == 404

    def test_delete_other_org_404(self, auth_client, project_offer):
        url = reverse(
            "projects:offer_delete",
            args=[project_other_org.pk, offer.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 404

    def test_accept_other_org_404(self, auth_client, project_offer):
        url = reverse(
            "projects:offer_accept",
            args=[project_other_org.pk, offer.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 404

    def test_reject_other_org_404(self, auth_client, project_offer):
        url = reverse(
            "projects:offer_reject",
            args=[project_other_org.pk, offer.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 404


# --- Interview CRUD ---


class TestInterviewCRUD:
    def test_create_interview(self, auth_client, project, passed_submission):
        """통과 Submission에 면접 등록."""
        url = reverse("projects:interview_create", args=[project.pk])
        scheduled = timezone.now().strftime("%Y-%m-%dT%H:%M")
        resp = auth_client.post(
            url,
            {
                "submission": str(passed_submission.pk),
                "round": 1,
                "scheduled_at": scheduled,
                "type": Interview.Type.IN_PERSON,
                "location": "서울 강남구 테헤란로",
                "notes": "1차 면접",
            })
        assert resp.status_code == 204
        assert Interview.objects.filter(submission=passed_submission, round=1).exists()

    def test_create_with_submission_prefill(
        self, auth_client, project, passed_submission
    ):
        """?submission= query param으로 submission 프리필 + round 자동 계산."""
        url = reverse("projects:interview_create", args=[project.pk])
        resp = auth_client.get(url + f"?submission={passed_submission.pk}")
        assert resp.status_code == 200
        content = resp.content.decode()
        # round 초기값 1이 있어야 함
        assert 'value="1"' in content

    def test_round_auto_increment(
        self, auth_client, project, passed_submission, interview
    ):
        """이전 차수 + 1 자동 제안."""
        url = reverse("projects:interview_create", args=[project.pk])
        resp = auth_client.get(url + f"?submission={passed_submission.pk}")
        content = resp.content.decode()
        # round=1 이미 있으므로 2가 제안되어야 함
        assert 'value="2"' in content

    def test_create_only_passed_submission(
        self, auth_client, project, drafting_submission
    ):
        """통과 상태 Submission만 선택 가능 (작성중은 불가)."""
        url = reverse("projects:interview_create", args=[project.pk])
        resp = auth_client.get(url)
        content = resp.content.decode()
        assert str(drafting_submission.candidate.name) not in content

    def test_create_duplicate_round_blocked(
        self, auth_client, project, passed_submission, interview
    ):
        """같은 submission+round 중복 등록 차단."""
        url = reverse("projects:interview_create", args=[project.pk])
        scheduled = timezone.now().strftime("%Y-%m-%dT%H:%M")
        resp = auth_client.post(
            url,
            {
                "submission": str(passed_submission.pk),
                "round": 1,  # 이미 존재
                "scheduled_at": scheduled,
                "type": Interview.Type.VIDEO,
            })
        # 200 = form re-render with error
        assert resp.status_code == 200
        assert Interview.objects.filter(submission=passed_submission).count() == 1

    def test_update_interview(self, auth_client, project, interview):
        """면접 수정."""
        url = reverse("projects:interview_update", args=[project.pk, interview.pk])
        scheduled = timezone.now().strftime("%Y-%m-%dT%H:%M")
        resp = auth_client.post(
            url,
            {
                "submission": str(interview.submission.pk),
                "round": 1,
                "scheduled_at": scheduled,
                "type": Interview.Type.VIDEO,
                "location": "Zoom",
                "notes": "화상으로 변경",
            })
        assert resp.status_code == 204
        interview.refresh_from_db()
        assert interview.type == Interview.Type.VIDEO
        assert interview.location == "Zoom"

    def test_delete_interview(self, auth_client, project, interview):
        """면접 삭제."""
        url = reverse("projects:interview_delete", args=[project.pk, interview.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 204
        assert not Interview.objects.filter(pk=interview.pk).exists()

    def test_delete_blocked_with_offer(
        self, auth_client, project, passed_interview, offer
    ):
        """오퍼 존재 시 면접 삭제 차단."""
        url = reverse(
            "projects:interview_delete",
            args=[project.pk, passed_interview.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 400
        assert Interview.objects.filter(pk=passed_interview.pk).exists()

    def test_tab_shows_interviews(self, auth_client, project, interview):
        """면접 탭에 면접 목록 표시."""
        url = reverse("projects:project_tab_interviews", args=[project.pk])
        resp = auth_client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert interview.submission.candidate.name in content


# --- Interview Result ---


class TestInterviewResult:
    def test_result_pending_to_passed(self, auth_client, project, interview):
        """대기 → 합격."""
        url = reverse("projects:interview_result", args=[project.pk, interview.pk])
        resp = auth_client.post(
            url,
            {
                "result": Interview.Result.PASSED,
                "feedback": "우수",
            })
        assert resp.status_code == 204
        interview.refresh_from_db()
        assert interview.result == Interview.Result.PASSED
        assert interview.feedback == "우수"

    def test_result_pending_to_failed(self, auth_client, project, interview):
        """대기 → 탈락."""
        url = reverse("projects:interview_result", args=[project.pk, interview.pk])
        resp = auth_client.post(
            url,
            {
                "result": Interview.Result.FAILED,
                "feedback": "경험 부족",
            })
        assert resp.status_code == 204
        interview.refresh_from_db()
        assert interview.result == Interview.Result.FAILED

    def test_result_pending_to_on_hold(self, auth_client, project, interview):
        """대기 → 보류."""
        url = reverse("projects:interview_result", args=[project.pk, interview.pk])
        resp = auth_client.post(
            url,
            {
                "result": Interview.Result.ON_HOLD,
            })
        assert resp.status_code == 204
        interview.refresh_from_db()
        assert interview.result == Interview.Result.ON_HOLD

    def test_result_already_passed_fails(self, auth_client, project, passed_interview):
        """합격 상태에서 재변경 불가."""
        url = reverse(
            "projects:interview_result",
            args=[project.pk, passed_interview.pk])
        resp = auth_client.post(
            url,
            {
                "result": Interview.Result.FAILED,
            })
        assert resp.status_code == 400
        passed_interview.refresh_from_db()
        assert passed_interview.result == Interview.Result.PASSED

    def test_result_already_failed_fails(self, auth_client, project, passed_submission):
        """탈락 상태에서 재변경 불가."""
        failed = Interview.objects.create(
            submission=passed_submission,
            round=1,
            scheduled_at=timezone.now(),
            type=Interview.Type.PHONE,
            result=Interview.Result.FAILED)
        url = reverse("projects:interview_result", args=[project.pk, failed.pk])
        resp = auth_client.post(
            url,
            {
                "result": Interview.Result.PASSED,
            })
        assert resp.status_code == 400


# --- Interview Result Service ---


class TestInterviewResultService:
    def test_apply_result_from_pending(self, passed_submission):
        interview = Interview.objects.create(
            submission=passed_submission,
            round=1,
            scheduled_at=timezone.now(),
            type=Interview.Type.IN_PERSON)
        result = apply_interview_result(interview, Interview.Result.PASSED, "좋음")
        assert result.result == Interview.Result.PASSED
        assert result.feedback == "좋음"

    def test_apply_result_from_passed_raises(self, passed_submission):
        interview = Interview.objects.create(
            submission=passed_submission,
            round=1,
            scheduled_at=timezone.now(),
            type=Interview.Type.IN_PERSON,
            result=Interview.Result.PASSED)
        with pytest.raises(InvalidTransition):
            apply_interview_result(interview, Interview.Result.FAILED, "")

    def test_apply_result_from_failed_raises(self, passed_submission):
        interview = Interview.objects.create(
            submission=passed_submission,
            round=1,
            scheduled_at=timezone.now(),
            type=Interview.Type.IN_PERSON,
            result=Interview.Result.FAILED)
        with pytest.raises(InvalidTransition):
            apply_interview_result(interview, Interview.Result.PASSED, "")


# --- Offer CRUD ---


class TestOfferCRUD:
    def test_create_offer(
        self, auth_client, project, passed_submission, passed_interview
    ):
        """최신 면접 합격 Submission에 오퍼 등록."""
        url = reverse("projects:offer_create", args=[project.pk])
        resp = auth_client.post(
            url,
            {
                "submission": str(passed_submission.pk),
                "salary": "8000만원",
                "position_title": "시니어 개발자",
                "start_date": "2026-05-01",
                "notes": "연봉 협의 가능",
            })
        assert resp.status_code == 204
        assert Offer.objects.filter(submission=passed_submission).exists()

    def test_create_only_latest_interview_passed(
        self, auth_client, project, passed_submission
    ):
        """최신(max round) 면접 합격인 Submission만 선택 가능."""
        # 1차 합격
        Interview.objects.create(
            submission=passed_submission,
            round=1,
            scheduled_at=timezone.now(),
            type=Interview.Type.IN_PERSON,
            result=Interview.Result.PASSED)
        # 2차 탈락 (최신)
        Interview.objects.create(
            submission=passed_submission,
            round=2,
            scheduled_at=timezone.now(),
            type=Interview.Type.VIDEO,
            result=Interview.Result.FAILED)
        url = reverse("projects:offer_create", args=[project.pk])
        resp = auth_client.get(url)
        content = resp.content.decode()
        # 드롭다운에 해당 후보자가 없어야 함
        assert passed_submission.candidate.name not in content

    def test_create_duplicate_offer_blocked(
        self, auth_client, project, passed_submission, offer
    ):
        """이미 Offer 있는 Submission은 드롭다운에 미표시."""
        url = reverse("projects:offer_create", args=[project.pk])
        resp = auth_client.get(url)
        content = resp.content.decode()
        assert str(passed_submission.pk) not in content

    def test_update_offer(self, auth_client, project, offer):
        """오퍼 수정."""
        url = reverse("projects:offer_update", args=[project.pk, offer.pk])
        resp = auth_client.post(
            url,
            {
                "submission": str(offer.submission.pk),
                "salary": "9000만원",
                "position_title": "리드 개발자",
                "start_date": "2026-06-01",
                "notes": "상향 조정",
            })
        assert resp.status_code == 204
        offer.refresh_from_db()
        assert offer.salary == "9000만원"

    def test_delete_offer_negotiating(self, auth_client, project, offer):
        """협상중 오퍼 삭제 가능."""
        url = reverse("projects:offer_delete", args=[project.pk, offer.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 204
        assert not Offer.objects.filter(pk=offer.pk).exists()

    def test_delete_offer_accepted_blocked(self, auth_client, project, offer):
        """수락된 오퍼 삭제 차단."""
        offer.status = Offer.Status.ACCEPTED
        offer.save()
        url = reverse("projects:offer_delete", args=[project.pk, offer.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 400
        assert Offer.objects.filter(pk=offer.pk).exists()

    def test_delete_offer_rejected_blocked(self, auth_client, project, offer):
        """거절된 오퍼 삭제 차단."""
        offer.status = Offer.Status.REJECTED
        offer.save()
        url = reverse("projects:offer_delete", args=[project.pk, offer.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 400

    def test_tab_shows_offers(self, auth_client, project, offer):
        """오퍼 탭에 오퍼 목록 표시."""
        url = reverse("projects:project_tab_offers", args=[project.pk])
        resp = auth_client.get(url)
        assert resp.status_code == 200
        content = resp.content.decode()
        assert offer.submission.candidate.name in content


# --- Offer Accept/Reject ---


class TestOfferAcceptReject:
    def test_accept_negotiating(self, auth_client, project, offer):
        """협상중 → 수락 + decided_at 기록."""
        url = reverse("projects:offer_accept", args=[project.pk, offer.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 204
        offer.refresh_from_db()
        assert offer.status == Offer.Status.ACCEPTED
        assert offer.decided_at is not None

    def test_reject_negotiating(self, auth_client, project, offer):
        """협상중 → 거절 + decided_at 기록."""
        url = reverse("projects:offer_reject", args=[project.pk, offer.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 204
        offer.refresh_from_db()
        assert offer.status == Offer.Status.REJECTED
        assert offer.decided_at is not None

    def test_accept_already_accepted_fails(self, auth_client, project, offer):
        """이미 수락된 오퍼 재수락 불가."""
        offer.status = Offer.Status.ACCEPTED
        offer.save()
        url = reverse("projects:offer_accept", args=[project.pk, offer.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 400

    def test_reject_already_rejected_fails(self, auth_client, project, offer):
        """이미 거절된 오퍼 재거절 불가."""
        offer.status = Offer.Status.REJECTED
        offer.save()
        url = reverse("projects:offer_reject", args=[project.pk, offer.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 400

    def test_accept_already_rejected_fails(self, auth_client, project, offer):
        """이미 거절된 오퍼 수락 불가."""
        offer.status = Offer.Status.REJECTED
        offer.save()
        url = reverse("projects:offer_accept", args=[project.pk, offer.pk])
        resp = auth_client.post(url)
        assert resp.status_code == 400


# --- Offer Status Service ---


class TestOfferStatusService:
    def test_accept_offer(self, passed_submission, passed_interview):
        offer = Offer.objects.create(submission=passed_submission)
        result = accept_offer(offer)
        assert result.status == Offer.Status.ACCEPTED
        assert result.decided_at is not None

    def test_reject_offer(self, passed_submission, passed_interview):
        offer = Offer.objects.create(submission=passed_submission)
        result = reject_offer(offer)
        assert result.status == Offer.Status.REJECTED

    def test_accept_already_accepted_raises(self, passed_submission, passed_interview):
        offer = Offer.objects.create(
            submission=passed_submission, status=Offer.Status.ACCEPTED
        )
        with pytest.raises(InvalidTransition):
            accept_offer(offer)

    def test_reject_already_rejected_raises(self, passed_submission, passed_interview):
        offer = Offer.objects.create(
            submission=passed_submission, status=Offer.Status.REJECTED
        )
        with pytest.raises(InvalidTransition):
            reject_offer(offer)


# --- Project Status Auto-transition ---


class TestProjectStatusAutoTransition:
    def test_first_interview_to_interviewing(self, project):
        """RECOMMENDING → INTERVIEWING."""
        assert project.status == ProjectStatus.RECOMMENDING
        changed = maybe_advance_to_interviewing(project)
        assert changed
        project.refresh_from_db()
        assert project.status == ProjectStatus.INTERVIEWING

    def test_first_interview_from_new_to_interviewing(self, project):
        """NEW → INTERVIEWING."""
        project.status = ProjectStatus.NEW
        project.save()
        changed = maybe_advance_to_interviewing(project)
        assert changed
        project.refresh_from_db()
        assert project.status == ProjectStatus.INTERVIEWING

    def test_already_interviewing_no_change(self, project):
        """이미 INTERVIEWING이면 변경 없음."""
        project.status = ProjectStatus.INTERVIEWING
        project.save()
        changed = maybe_advance_to_interviewing(project)
        assert not changed

    def test_first_offer_to_negotiating(self, project):
        """INTERVIEWING → NEGOTIATING."""
        project.status = ProjectStatus.INTERVIEWING
        project.save()
        changed = maybe_advance_to_negotiating(project)
        assert changed
        project.refresh_from_db()
        assert project.status == ProjectStatus.NEGOTIATING

    def test_already_negotiating_no_change(self, project):
        """이미 NEGOTIATING이면 변경 없음."""
        project.status = ProjectStatus.NEGOTIATING
        project.save()
        changed = maybe_advance_to_negotiating(project)
        assert not changed

    def test_offer_accepted_to_closed_success(self, project):
        """NEGOTIATING → CLOSED_SUCCESS."""
        project.status = ProjectStatus.NEGOTIATING
        project.save()
        changed = maybe_advance_to_closed_success(project)
        assert changed
        project.refresh_from_db()
        assert project.status == ProjectStatus.CLOSED_SUCCESS

    def test_no_reverse_transition(self, project):
        """INTERVIEWING → RECOMMENDING 역전환 방지 (recommending 전환 함수 없지만 논리 검증)."""
        project.status = ProjectStatus.INTERVIEWING
        project.save()
        # advance_to_interviewing은 이미 INTERVIEWING이면 False
        changed = maybe_advance_to_interviewing(project)
        assert not changed
        project.refresh_from_db()
        assert project.status == ProjectStatus.INTERVIEWING

    def test_closed_success_no_further_advance(self, project):
        """CLOSED_SUCCESS 이후 자동 전환 없음."""
        project.status = ProjectStatus.CLOSED_SUCCESS
        project.save()
        assert not maybe_advance_to_interviewing(project)
        assert not maybe_advance_to_negotiating(project)
        assert not maybe_advance_to_closed_success(project)


# --- Offer Eligibility ---


class TestOfferEligibility:
    def test_eligible_with_passed_interview(self, passed_submission):
        """최신 인터뷰 합격 → eligible."""
        Interview.objects.create(
            submission=passed_submission,
            round=1,
            scheduled_at=timezone.now(),
            type=Interview.Type.IN_PERSON,
            result=Interview.Result.PASSED)
        assert is_submission_offer_eligible(passed_submission) is True

    def test_not_eligible_with_failed_interview(self, passed_submission):
        """최신 인터뷰 탈락 → not eligible."""
        Interview.objects.create(
            submission=passed_submission,
            round=1,
            scheduled_at=timezone.now(),
            type=Interview.Type.IN_PERSON,
            result=Interview.Result.FAILED)
        assert is_submission_offer_eligible(passed_submission) is False

    def test_not_eligible_without_interview(self, passed_submission):
        """인터뷰 없음 → not eligible."""
        assert is_submission_offer_eligible(passed_submission) is False

    def test_not_eligible_1st_pass_2nd_fail(self, passed_submission):
        """1차 합격 + 2차 탈락 → not eligible."""
        Interview.objects.create(
            submission=passed_submission,
            round=1,
            scheduled_at=timezone.now(),
            type=Interview.Type.IN_PERSON,
            result=Interview.Result.PASSED)
        Interview.objects.create(
            submission=passed_submission,
            round=2,
            scheduled_at=timezone.now(),
            type=Interview.Type.VIDEO,
            result=Interview.Result.FAILED)
        assert is_submission_offer_eligible(passed_submission) is False


# --- HTMX Behavior ---


class TestHTMXBehavior:
    def test_interview_create_returns_204_with_trigger(
        self, auth_client, project, passed_submission
    ):
        """면접 생성 성공 시 204 + HX-Trigger: interviewChanged."""
        url = reverse("projects:interview_create", args=[project.pk])
        scheduled = timezone.now().strftime("%Y-%m-%dT%H:%M")
        resp = auth_client.post(
            url,
            {
                "submission": str(passed_submission.pk),
                "round": 1,
                "scheduled_at": scheduled,
                "type": Interview.Type.IN_PERSON,
            })
        assert resp.status_code == 204
        assert resp.headers.get("HX-Trigger") == "interviewChanged"

    def test_offer_create_returns_204_with_trigger(
        self, auth_client, project, passed_submission, passed_interview
    ):
        """오퍼 생성 성공 시 204 + HX-Trigger: offerChanged."""
        url = reverse("projects:offer_create", args=[project.pk])
        resp = auth_client.post(
            url,
            {
                "submission": str(passed_submission.pk),
                "salary": "7000만원",
                "position_title": "매니저",
            })
        assert resp.status_code == 204
        assert resp.headers.get("HX-Trigger") == "offerChanged"

    def test_interview_tab_has_auto_refresh_trigger(self, auth_client, project):
        """면접 탭에 interviewChanged 자동 새로고침 트리거 존재."""
        url = reverse("projects:project_tab_interviews", args=[project.pk])
        resp = auth_client.get(url)
        content = resp.content.decode()
        assert "interviewChanged" in content

    def test_offer_tab_has_auto_refresh_trigger(self, auth_client, project):
        """오퍼 탭에 offerChanged 자동 새로고침 트리거 존재."""
        url = reverse("projects:project_tab_offers", args=[project.pk])
        resp = auth_client.get(url)
        content = resp.content.decode()
        assert "offerChanged" in content


# --- P07 Integration ---


class TestP07Integration:
    def test_passed_submission_shows_interview_link(
        self, auth_client, project, passed_submission
    ):
        """통과 건에 '면접 등록' 링크 표시."""
        url = reverse("projects:project_tab_submissions", args=[project.pk])
        resp = auth_client.get(url)
        content = resp.content.decode()
        assert "면접 등록" in content
        # disabled placeholder가 아닌 실제 링크인지 확인
        assert "준비중" not in content


# --- Model Fields ---


class TestModelFields:
    def test_interview_new_fields_default(self, passed_submission):
        """Interview 새 필드 기본값."""
        interview = Interview.objects.create(
            submission=passed_submission,
            round=1,
            scheduled_at=timezone.now(),
            type=Interview.Type.IN_PERSON)
        assert interview.location == ""
        assert interview.notes == ""

    def test_offer_new_fields_default(self, passed_submission, passed_interview):
        """Offer 새 필드 기본값."""
        offer = Offer.objects.create(submission=passed_submission)
        assert offer.notes == ""
        assert offer.decided_at is None

    def test_interview_unique_constraint(self, passed_submission):
        """같은 submission+round 중복 차단."""
        Interview.objects.create(
            submission=passed_submission,
            round=1,
            scheduled_at=timezone.now(),
            type=Interview.Type.IN_PERSON)
        from django.db import IntegrityError

        with pytest.raises(IntegrityError):
            Interview.objects.create(
                submission=passed_submission,
                round=1,
                scheduled_at=timezone.now(),
                type=Interview.Type.VIDEO)
