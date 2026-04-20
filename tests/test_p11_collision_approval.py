"""P11: Collision detection and approval workflow tests."""

import pytest
from django.test import Client as TestClient

from accounts.models import User
from clients.models import Client
from projects.models import Project, ProjectApproval
from projects.services.approval import (
    InvalidApprovalTransition,
    approve_project,
    cancel_approval,
    merge_project,
    reject_project,
    send_admin_message)
from projects.services.collision import compute_title_similarity, detect_collisions


# --- Fixtures ---



@pytest.fixture
def user_owner(db):
    user = User.objects.create_user(username="owner", password="test1234")
    return user


@pytest.fixture
def user_consultant(db):
    user = User.objects.create_user(username="consultant", password="test1234")
    return user


@pytest.fixture
def client_obj(org):
    return Client.objects.create(name="Acme Corp", industry="IT")


@pytest.fixture
def existing_project(org, client_obj, user_consultant):
    return Project.objects.create(
        client=client_obj
        title="품질기획팀장",
        status="searching",
        created_by=user_consultant)


@pytest.fixture
def auth_owner(user_owner):
    c = TestClient()
    c.login(username="owner", password="test1234")
    return c


@pytest.fixture
def auth_consultant(user_consultant):
    c = TestClient()
    c.login(username="consultant", password="test1234")
    return c


# --- Task 1: Model tests ---


class TestProjectApprovalModel:
    @pytest.mark.django_db
    def test_conflict_score_field_exists(
        self, client_obj, user_consultant, existing_project
    ):
        approval = ProjectApproval.objects.create(
            project=existing_project,
            requested_by=user_consultant,
            conflict_score=0.85,
            conflict_type="높은중복")
        approval.refresh_from_db()
        assert approval.conflict_score == 0.85
        assert approval.conflict_type == "높은중복"

    @pytest.mark.django_db
    def test_conflict_score_default(
        self, client_obj, user_consultant, existing_project
    ):
        approval = ProjectApproval.objects.create(
            project=existing_project,
            requested_by=user_consultant)
        approval.refresh_from_db()
        assert approval.conflict_score == 0.0
        assert approval.conflict_type == ""

    @pytest.mark.django_db
    def test_project_fk_set_null_on_delete(
        self, client_obj, user_consultant, existing_project
    ):
        """Verify that deleting the project sets FK to NULL instead of cascading."""
        approval = ProjectApproval.objects.create(
            project=existing_project,
            requested_by=user_consultant)
        existing_project.delete()
        approval.refresh_from_db()
        assert approval.project is None


# --- Task 2: Collision detection tests ---


class TestTitleSimilarity:
    def test_identical_titles(self):
        assert compute_title_similarity("품질기획팀장", "품질기획팀장") == 1.0

    def test_very_similar_titles(self):
        score = compute_title_similarity("품질기획팀장", "품질기획파트장")
        assert score >= 0.7  # high similarity

    def test_same_department_different_role(self):
        score = compute_title_similarity("경영기획팀장", "경영기획")
        assert score >= 0.5

    def test_completely_different(self):
        score = compute_title_similarity("품질기획팀장", "마케팅매니저")
        assert score < 0.5

    def test_empty_title(self):
        assert compute_title_similarity("", "품질기획팀장") == 0.0
        assert compute_title_similarity("품질기획팀장", "") == 0.0


class TestDetectCollisions:
    @pytest.mark.django_db
    def test_detects_similar_project(self, client_obj, existing_project):
        results = detect_collisions(client_obj.pk, "품질기획파트장", org)
        assert len(results) >= 1
        assert results[0]["project"].pk == existing_project.pk
        assert results[0]["score"] >= 0.7
        assert results[0]["conflict_type"] == "높은중복"

    @pytest.mark.django_db
    def test_no_collision_different_client(self, client_obj, existing_project):
        other_client = Client.objects.create(
            name="Other Corp", industry="Finance"
        )
        results = detect_collisions(other_client.pk, "품질기획팀장", org)
        assert len(results) == 0

    @pytest.mark.django_db
    def test_excludes_closed_projects(self, client_obj, user_consultant):
        Project.objects.create(
            client=client_obj
            title="품질기획팀장",
            status="closed_success",
            created_by=user_consultant)
        results = detect_collisions(client_obj.pk, "품질기획팀장", org)
        assert len(results) == 0

    @pytest.mark.django_db
    def test_medium_conflict_type(self, client_obj, existing_project):
        results = detect_collisions(client_obj.pk, "마케팅매니저", org)
        # Same client but low similarity -> medium or no result
        for r in results:
            if r["score"] < 0.7:
                assert r["conflict_type"] == "참고정보"

    @pytest.mark.django_db
    def test_max_five_results(self, client_obj, user_consultant):
        for i in range(8):
            Project.objects.create(
                client=client_obj
                title=f"품질기획팀장{i}",
                status="searching",
                created_by=user_consultant)
        results = detect_collisions(client_obj.pk, "품질기획팀장", org)
        assert len(results) <= 5


# --- Task 3: Approval service tests ---


class TestApprovalService:
    @pytest.fixture
    def pending_project(self, client_obj, user_consultant):
        return Project.objects.create(
            client=client_obj
            title="품질기획파트장",
            status="pending_approval",
            created_by=user_consultant)

    @pytest.fixture
    def approval(self, pending_project, user_consultant, existing_project):
        return ProjectApproval.objects.create(
            project=pending_project,
            requested_by=user_consultant,
            conflict_project=existing_project,
            conflict_score=0.85,
            conflict_type="높은중복")

    @pytest.mark.django_db
    def test_approve_project(self, approval, user_owner, pending_project):
        approve_project(approval, user_owner)
        approval.refresh_from_db()
        pending_project.refresh_from_db()
        assert approval.status == "승인"
        assert pending_project.status == "new"
        assert approval.decided_by == user_owner
        assert approval.decided_at is not None

    @pytest.mark.django_db
    def test_reject_project(self, approval, user_owner, pending_project):
        reject_project(approval, user_owner, response_text="중복 프로젝트입니다.")
        approval.refresh_from_db()
        assert approval.status == "반려"
        assert approval.admin_response == "중복 프로젝트입니다."
        # Project should be deleted, FK set to NULL
        assert not Project.objects.filter(pk=pending_project.pk).exists()
        assert approval.project is None

    @pytest.mark.django_db
    def test_merge_project(
        self,
        approval,
        user_owner,
        pending_project,
        existing_project,
        user_consultant):
        merge_project(approval, user_owner, merge_target=existing_project)
        approval.refresh_from_db()
        assert approval.status == "합류"
        # Requester should be added to target project
        assert existing_project.assigned_consultants.filter(
            pk=user_consultant.pk
        ).exists()
        # Pending project should be deleted
        assert not Project.objects.filter(pk=pending_project.pk).exists()
        assert approval.project is None

    @pytest.mark.django_db
    def test_merge_defaults_to_conflict_project(
        self, approval, user_owner, pending_project, existing_project, user_consultant
    ):
        merge_project(approval, user_owner)  # No merge_target
        existing_project.refresh_from_db()
        assert existing_project.assigned_consultants.filter(
            pk=user_consultant.pk
        ).exists()

    @pytest.mark.django_db
    def test_send_admin_message(self, approval, user_owner):
        send_admin_message(approval, user_owner, "추가 정보를 제공해주세요.")
        approval.refresh_from_db()
        assert approval.admin_response == "추가 정보를 제공해주세요."
        assert approval.status == "대기"  # Status unchanged

    @pytest.mark.django_db
    def test_cancel_approval(self, approval, pending_project):
        cancel_approval(approval)
        assert not ProjectApproval.objects.filter(pk=approval.pk).exists()
        assert not Project.objects.filter(pk=pending_project.pk).exists()

    @pytest.mark.django_db
    def test_double_approve_raises(self, approval, user_owner):
        approve_project(approval, user_owner)
        with pytest.raises(InvalidApprovalTransition):
            approve_project(approval, user_owner)

    @pytest.mark.django_db
    def test_reject_after_approve_raises(self, approval, user_owner):
        approve_project(approval, user_owner)
        with pytest.raises(InvalidApprovalTransition):
            reject_project(approval, user_owner)


# --- Task 4: Form tests ---

from projects.forms import ApprovalDecisionForm, ProjectForm


class TestProjectFormNoStatus:
    @pytest.mark.django_db
    def test_status_not_in_form_fields(self):
        form = ProjectForm()
        assert "status" not in form.fields


class TestApprovalDecisionForm:
    def test_valid_approve(self):
        form = ApprovalDecisionForm(data={"decision": "승인"})
        assert form.is_valid()

    def test_valid_reject_with_response(self):
        form = ApprovalDecisionForm(
            data={"decision": "반려", "response_text": "중복입니다."}
        )
        assert form.is_valid()

    def test_valid_message(self):
        form = ApprovalDecisionForm(
            data={"decision": "메시지", "response_text": "추가 정보 필요"}
        )
        assert form.is_valid()

    def test_invalid_decision(self):
        form = ApprovalDecisionForm(data={"decision": "invalid"})
        assert not form.is_valid()


# --- Task 5: View tests - collision check + project_create ---


class TestCollisionCheckView:
    @pytest.mark.django_db
    def test_collision_detected(self, auth_consultant, client_obj, existing_project):
        resp = auth_consultant.post(
            "/projects/new/check-collision/",
            {"client_id": str(client_obj.pk), "title": "품질기획파트장"},
            HTTP_HX_REQUEST="true")
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "유사 프로젝트" in content or "충돌" in content

    @pytest.mark.django_db
    def test_no_collision(self, auth_consultant, client_obj):
        resp = auth_consultant.post(
            "/projects/new/check-collision/",
            {"client_id": str(client_obj.pk), "title": "완전다른포지션"},
            HTTP_HX_REQUEST="true")
        assert resp.status_code == 200


class TestProjectCreateWithCollision:
    @pytest.mark.django_db
    def test_create_without_collision_normal(self, auth_consultant, client_obj):
        """No collision -> status=new, direct redirect."""
        resp = auth_consultant.post(
            "/projects/new/",
            {
                "client": str(client_obj.pk),
                "title": "완전새로운포지션",
                "jd_source": "",
            })
        assert resp.status_code == 302
        project = Project.objects.get(title="완전새로운포지션")
        assert project.status == "new"
        assert not ProjectApproval.objects.filter(project=project).exists()

    @pytest.mark.django_db
    def test_create_with_high_collision(
        self, auth_consultant, client_obj, existing_project, user_consultant
    ):
        """High collision -> pending_approval + ProjectApproval created."""
        resp = auth_consultant.post(
            "/projects/new/",
            {
                "client": str(client_obj.pk),
                "title": "품질기획파트장",
                "jd_source": "",
            })
        assert resp.status_code == 302  # PRG redirect
        project = Project.objects.get(title="품질기획파트장")
        assert project.status == "pending_approval"
        approval = ProjectApproval.objects.get(project=project)
        assert approval.conflict_project == existing_project
        assert approval.conflict_score >= 0.7
        assert approval.requested_by == user_consultant

    @pytest.mark.django_db
    def test_create_with_medium_collision_not_blocked(
        self, auth_consultant, client_obj, existing_project
    ):
        """Medium collision (< 0.7) should NOT block creation."""
        resp = auth_consultant.post(
            "/projects/new/",
            {
                "client": str(client_obj.pk),
                "title": "마케팅매니저",  # Low similarity with "품질기획팀장"
                "jd_source": "",
            })
        assert resp.status_code == 302
        project = Project.objects.get(title="마케팅매니저")
        assert project.status == "new"  # Not blocked
        assert not ProjectApproval.objects.filter(project=project).exists()


# --- Task 6: Approval queue, decide, cancel, guards ---


class TestApprovalQueueView:
    @pytest.fixture
    def pending_project(self, client_obj, user_consultant):
        return Project.objects.create(
            client=client_obj
            title="품질기획파트장",
            status="pending_approval",
            created_by=user_consultant)

    @pytest.fixture
    def approval(self, pending_project, user_consultant, existing_project):
        return ProjectApproval.objects.create(
            project=pending_project,
            requested_by=user_consultant,
            conflict_project=existing_project,
            conflict_score=0.85,
            conflict_type="높은중복",
            message="인사팀으로부터 직접 의뢰")

    @pytest.mark.django_db
    def test_owner_can_access_queue(self, auth_owner, approval):
        resp = auth_owner.get("/projects/approvals/")
        assert resp.status_code == 200
        assert "품질기획파트장" in resp.content.decode()

    @pytest.mark.django_db
    def test_consultant_cannot_access_queue(self, auth_consultant, approval):
        resp = auth_consultant.get("/projects/approvals/")
        assert resp.status_code == 403

    @pytest.mark.django_db
    def test_approve_decision(self, auth_owner, approval, pending_project):
        resp = auth_owner.post(
            f"/projects/approvals/{approval.pk}/decide/",
            {"decision": "승인"})
        assert resp.status_code == 302
        pending_project.refresh_from_db()
        assert pending_project.status == "new"

    @pytest.mark.django_db
    def test_reject_decision(self, auth_owner, approval, pending_project):
        resp = auth_owner.post(
            f"/projects/approvals/{approval.pk}/decide/",
            {"decision": "반려", "response_text": "중복입니다."})
        assert resp.status_code == 302
        assert not Project.objects.filter(pk=pending_project.pk).exists()

    @pytest.mark.django_db
    def test_merge_decision(
        self,
        auth_owner,
        approval,
        pending_project,
        existing_project,
        user_consultant):
        resp = auth_owner.post(
            f"/projects/approvals/{approval.pk}/decide/",
            {"decision": "합류"})
        assert resp.status_code == 302
        assert existing_project.assigned_consultants.filter(
            pk=user_consultant.pk
        ).exists()
        assert not Project.objects.filter(pk=pending_project.pk).exists()

    @pytest.mark.django_db
    def test_message_decision(self, auth_owner, approval, pending_project):
        resp = auth_owner.post(
            f"/projects/approvals/{approval.pk}/decide/",
            {"decision": "메시지", "response_text": "추가 정보 필요합니다."})
        assert resp.status_code == 302
        approval.refresh_from_db()
        assert approval.status == "대기"  # Unchanged
        assert approval.admin_response == "추가 정보 필요합니다."

    @pytest.mark.django_db
    def test_merge_with_custom_target(
        self,
        auth_owner,
        approval,
        pending_project,
        client_obj,
        user_consultant):
        alt_project = Project.objects.create(
            client=client_obj
            title="대체합류대상",
            status="searching",
            created_by=user_consultant)
        resp = auth_owner.post(
            f"/projects/approvals/{approval.pk}/decide/",
            {"decision": "합류", "merge_target": str(alt_project.pk)})
        assert resp.status_code == 302
        assert alt_project.assigned_consultants.filter(pk=user_consultant.pk).exists()


class TestApprovalCancelView:
    @pytest.fixture
    def pending_project(self, client_obj, user_consultant):
        return Project.objects.create(
            client=client_obj
            title="품질기획파트장",
            status="pending_approval",
            created_by=user_consultant)

    @pytest.fixture
    def approval(self, pending_project, user_consultant):
        return ProjectApproval.objects.create(
            project=pending_project,
            requested_by=user_consultant)

    @pytest.mark.django_db
    def test_requester_can_cancel(self, auth_consultant, approval, pending_project):
        resp = auth_consultant.post(f"/projects/{pending_project.pk}/approval/cancel/")
        assert resp.status_code == 302
        assert not Project.objects.filter(pk=pending_project.pk).exists()
        assert not ProjectApproval.objects.filter(pk=approval.pk).exists()


class TestPendingApprovalGuards:
    @pytest.fixture
    def pending_project(self, client_obj, user_consultant):
        p = Project.objects.create(
            client=client_obj
            title="승인대기프로젝트",
            status="pending_approval",
            created_by=user_consultant)
        p.assigned_consultants.add(user_consultant)
        return p

    @pytest.mark.django_db
    def test_contact_create_blocked(self, auth_consultant, pending_project):
        resp = auth_consultant.get(f"/projects/{pending_project.pk}/contacts/new/")
        assert resp.status_code == 403

    @pytest.mark.django_db
    def test_submission_create_blocked(self, auth_consultant, pending_project):
        resp = auth_consultant.get(f"/projects/{pending_project.pk}/submissions/new/")
        assert resp.status_code == 403

    @pytest.mark.django_db
    def test_status_update_blocked(self, auth_consultant, pending_project):
        import json

        resp = auth_consultant.patch(
            f"/projects/{pending_project.pk}/status/",
            json.dumps({"status": "new"}),
            content_type="application/json")
        assert resp.status_code == 403

    @pytest.mark.django_db
    def test_project_update_blocked(self, auth_consultant, pending_project):
        resp = auth_consultant.post(
            f"/projects/{pending_project.pk}/edit/",
            {
                "client": str(pending_project.client_id),
                "title": "수정된 제목",
            })
        assert resp.status_code == 403

    @pytest.mark.django_db
    def test_project_delete_blocked(self, auth_consultant, pending_project):
        resp = auth_consultant.post(f"/projects/{pending_project.pk}/delete/")
        assert resp.status_code == 403
        assert Project.objects.filter(pk=pending_project.pk).exists()
