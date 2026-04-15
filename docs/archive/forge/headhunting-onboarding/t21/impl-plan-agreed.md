# t21: contact_update() "관심" 결과 시 추천 유도 배너

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** contact_update() 뷰에서 결과를 "관심"으로 **변경**할 때, 추천 서류 작성을 유도하는 배너를 표시한다. 이미 Submission이 있거나, 이미 "관심"이던 컨택을 재편집하는 경우에는 배너를 표시하지 않는다.

**Design spec:** `docs/forge/headhunting-onboarding/t21/design-spec.md`

**depends_on:** t19

---

## Tempering Decisions

| ID | 이슈 | 판정 | 변경 |
|----|-------|------|------|
| R1-01 | contactChanged 이벤트로 배너 즉시 덮어쓰기 | ACCEPT | 배너를 #contact-form-area에 단독 삽입 대신, 컨택 탭 전체를 리렌더링하여 배너 포함. HX-Retarget="#tab-content" |
| R1-02 | 상태 "변경" 검사 누락 | ACCEPT | old_result 보존 → 전이 조건(non-INTERESTED → INTERESTED)으로 변경 |
| R1-03 | CTA 클릭 시 tabChanged 미발행 | ACCEPT | CTA 버튼에 hx-on::after-request로 tabChanged 이벤트 발행 추가 |
| R1-04 | 테스트가 HTMX 헤더 미검증 | ACCEPT | HX-Retarget, HX-Reswap, HX-Trigger 헤더 검증 + 재편집 시 배너 미표시 테스트 추가 |
| R1-05 | 배너 CTA 후 잔류 | REBUT | #contact-form-area는 #tab-content 안에 위치. CTA가 #tab-content를 교체하므로 자동 제거 |

---

## File Map

| 파일 | 동작 | 역할 |
|------|------|------|
| `projects/views.py` | 수정 | `contact_update()` "관심" 전환 시 유도 배너 포함한 탭 리렌더링 |
| `projects/templates/projects/partials/contact_interest_banner.html` | 생성 | "관심" 결과 저장 후 추천 유도 배너 |
| `tests/test_p20_workflow_transition.py` | 추가 | 배너 표시/비표시/HTMX 헤더 테스트 |

---

- [ ] **Step 1: 실패 테스트 작성**

`tests/test_p20_workflow_transition.py`에 추가:

```python
class TestContactInterestBanner:
    """contact_update에서 결과를 '관심'으로 변경하면
    응답에 추천 유도 배너가 포함되어야 한다."""

    @pytest.mark.django_db
    def test_interest_result_shows_banner(
        self, auth_client, project, candidate, user_with_org
    ):
        """결과가 '관심'으로 변경되면 배너가 포함된다."""
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="응답",
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/edit/",
            {
                "candidate": str(candidate.pk),
                "channel": "전화",
                "contacted_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "result": "관심",
                "notes": "",
            },
        )
        assert resp.status_code == 200
        content = resp.content.decode()
        assert "추천 서류 작성하기" in content

    @pytest.mark.django_db
    def test_interest_result_has_htmx_headers(
        self, auth_client, project, candidate, user_with_org
    ):
        """'관심' 전환 시 HX-Retarget, HX-Reswap, HX-Trigger 헤더가 올바르다."""
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="응답",
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/edit/",
            {
                "candidate": str(candidate.pk),
                "channel": "전화",
                "contacted_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "result": "관심",
                "notes": "",
            },
        )
        assert resp.headers.get("HX-Retarget") == "#tab-content"
        assert resp.headers.get("HX-Reswap") == "innerHTML"
        assert "contactChanged" in resp.headers.get("HX-Trigger", "")

    @pytest.mark.django_db
    def test_non_interest_result_no_banner(
        self, auth_client, project, candidate, user_with_org
    ):
        """결과가 '관심'이 아니면 배너가 포함되지 않는다."""
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="응답",
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/edit/",
            {
                "candidate": str(candidate.pk),
                "channel": "전화",
                "contacted_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "result": "미응답",
                "notes": "",
            },
        )
        # 204 반환 (기존 동작) — 배너 없음
        assert resp.status_code == 204

    @pytest.mark.django_db
    def test_interest_but_already_submitted_no_banner(
        self, auth_client, project, candidate, user_with_org
    ):
        """이미 Submission이 있으면 배너를 표시하지 않는다."""
        Submission.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
        )
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="응답",
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/edit/",
            {
                "candidate": str(candidate.pk),
                "channel": "전화",
                "contacted_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "result": "관심",
                "notes": "",
            },
        )
        # 이미 제출 완료이므로 배너 없이 204 반환
        assert resp.status_code == 204

    @pytest.mark.django_db
    def test_already_interested_edit_no_banner(
        self, auth_client, project, candidate, user_with_org
    ):
        """이미 '관심'인 컨택의 메모만 수정하면 배너가 표시되지 않는다."""
        contact = Contact.objects.create(
            project=project,
            candidate=candidate,
            consultant=user_with_org,
            channel="전화",
            contacted_at=timezone.now(),
            result="관심",  # 이미 관심
        )
        resp = auth_client.post(
            f"/projects/{project.pk}/contacts/{contact.pk}/edit/",
            {
                "candidate": str(candidate.pk),
                "channel": "전화",
                "contacted_at": timezone.now().strftime("%Y-%m-%dT%H:%M"),
                "result": "관심",  # 변경 없음
                "notes": "메모 추가",
            },
        )
        # 관심→관심 (변경 없음)이므로 배너 없이 204 반환
        assert resp.status_code == 204
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/test_p20_workflow_transition.py::TestContactInterestBanner -v`
Expected: FAIL — 현재 `contact_update()`는 항상 204를 반환

- [ ] **Step 3: contact_interest_banner.html 생성**

```html
<!-- projects/templates/projects/partials/contact_interest_banner.html -->
<div id="interest-banner"
     class="bg-green-50 border border-green-200 rounded-lg p-4 mb-4">
  <div class="flex items-start gap-3">
    <svg class="w-5 h-5 text-green-500 mt-0.5 shrink-0" fill="none" stroke="currentColor" viewBox="0 0 24 24">
      <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M5 13l4 4L19 7"/>
    </svg>
    <div>
      <p class="text-[14px] font-medium text-green-800">
        {{ candidate_name }}님 컨택 결과가 "관심"으로 저장되었습니다.
      </p>
      <button hx-get="{% url 'projects:submission_create' project.pk %}?candidate={{ candidate_id }}"
              hx-target="#tab-content"
              hx-trigger="click"
              hx-on::after-request="document.body.dispatchEvent(new CustomEvent('tabChanged', {detail: {activeTab: 'submissions'}}))"
              class="mt-2 inline-flex items-center text-[14px] font-medium text-green-700 hover:text-green-900 transition">
        추천 서류 작성하기
        <svg class="w-4 h-4 ml-1" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path stroke-linecap="round" stroke-linejoin="round" stroke-width="2" d="M9 5l7 7-7 7"/>
        </svg>
      </button>
    </div>
  </div>
</div>
```

- [ ] **Step 4: contact_update() 뷰 수정**

`projects/views.py`의 `contact_update()`. 현재 성공 분기:

```python
        if form.is_valid():
            form.save()
            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "contactChanged"},
            )
```

변경:
```python
        if form.is_valid():
            old_result = contact.result  # 저장 전 결과 보존
            contact = form.save()

            # "관심"으로 전환되었고 아직 Submission이 없으면 유도 배너 포함 탭 리렌더링
            if (
                old_result != Contact.Result.INTERESTED
                and contact.result == Contact.Result.INTERESTED
                and not project.submissions.filter(
                    candidate=contact.candidate
                ).exists()
            ):
                # 컨택 탭 컨텍스트 구성 (project_tab_contacts 뷰와 동일)
                from projects.services.contact import release_expired_reservations
                release_expired_reservations()

                completed_contacts = (
                    project.contacts.exclude(result=Contact.Result.RESERVED)
                    .select_related("candidate", "consultant")
                    .order_by("-contacted_at")
                )
                reserved_contacts = (
                    project.contacts.filter(
                        result=Contact.Result.RESERVED,
                        locked_until__gt=timezone.now(),
                    )
                    .select_related("candidate", "consultant")
                    .order_by("-created_at")
                )
                submitted_candidate_ids = set(
                    project.submissions.values_list("candidate_id", flat=True)
                )

                response = render(
                    request,
                    "projects/partials/tab_contacts.html",
                    {
                        "project": project,
                        "completed_contacts": completed_contacts,
                        "reserved_contacts": reserved_contacts,
                        "can_release": request.user in project.assigned_consultants.all(),
                        "submitted_candidate_ids": submitted_candidate_ids,
                        "interest_banner": {
                            "candidate_name": contact.candidate.name,
                            "candidate_id": contact.candidate.pk,
                        },
                    },
                )
                response["HX-Retarget"] = "#tab-content"
                response["HX-Reswap"] = "innerHTML"
                response["HX-Trigger"] = "contactChanged"
                return response

            return HttpResponse(
                status=204,
                headers={"HX-Trigger": "contactChanged"},
            )
```

- [ ] **Step 5: tab_contacts.html에 배너 include 추가**

`projects/templates/projects/partials/tab_contacts.html`의 `<!-- 폼 삽입 영역 -->` 직후 (line 14 부근):

```html
  <!-- 폼 삽입 영역 -->
  <div id="contact-form-area">
    {% if interest_banner %}
      {% include "projects/partials/contact_interest_banner.html" with candidate_name=interest_banner.candidate_name candidate_id=interest_banner.candidate_id %}
    {% endif %}
  </div>
```

기존 `<div id="contact-form-area"></div>`를 위 코드로 교체.

- [ ] **Step 6: 테스트 실행 — 통과 확인**

Run: `uv run pytest tests/test_p20_workflow_transition.py::TestContactInterestBanner -v`
Expected: All 5 tests PASS

- [ ] **Step 7: 전체 테스트 실행**

Run: `uv run pytest -v`
Expected: 기존 테스트 포함 전부 PASS

- [ ] **Step 8: 커밋**

```bash
git add projects/views.py projects/templates/projects/partials/contact_interest_banner.html projects/templates/projects/partials/tab_contacts.html tests/test_p20_workflow_transition.py
git commit -m "feat(projects): show submission prompt banner when contact result changes to INTERESTED"
```

<!-- forge:t21:impl-plan:complete:2026-04-13T00:25:00+09:00 -->
