# Phase 6 — 레거시 제거 + 린트 + E2E 확인

**전제**: Phase 5 완료. 핵심 로직 테스트 통과.
**목표**: Phase 1~5에서 임시로 남겨둔 모든 레거시 참조를 완전히 제거. 린트 통과. 개발 서버에서 `/browse` 스킬로 E2E 확인.
**예상 시간**: 0.5일
**리스크**: 낮음

---

## 1. 목표 상태

- `rg -n '\b(Contact|Offer)\b' projects/ tests/ conftest.py --glob '!**/migrations/**' --glob '!docs/**'` 결과 0건
- `rg -n 'ProjectStatus\.(NEW|SEARCHING|RECOMMENDING|INTERVIEWING|NEGOTIATING|ON_HOLD|PENDING_APPROVAL|CLOSED_SUCCESS|CLOSED_FAIL|CLOSED_CANCEL)' projects/ tests/` 결과 0건
- `rg -n 'new|searching|recommending|interviewing|negotiating|closed_success|closed_fail|closed_cancel|on_hold|pending_approval' projects/ tests/ --glob '*.py' --glob '*.html' --glob '!**/migrations/**'` 결과 0건 (false positive 제외)
- **`ProjectStatus.OPEN`/`ProjectStatus.CLOSED` 참조는 유지** (활성 2-state enum)
- `uv run ruff check .` 통과 (에러 0, 경고 0)
- `uv run ruff format .` 적용됨
- `uv run pytest -v` 전체 통과
- `uv run python manage.py check --deploy` 통과
- `uv run python manage.py makemigrations --check --dry-run` 통과
- `/browse` 스킬로 주요 플로우 E2E 확인 완료 (스크린샷 포함)
- 브랜치 `feat/project-application-redesign`이 머지 후보 상태

## 2. 사전 조건

- Phase 5 커밋 완료
- 모든 테스트 통과

## 3. 영향 범위

### 3.1 정리 대상 파일

**레포 전체 스캔** (docs/, migrations/, .venv/ 제외):

- `projects/views.py` 잔여 import 및 레거시 뷰 함수
- `projects/services/*.py` 잔여 import 및 레거시 서비스 로직
- `projects/templates/projects/partials/` 잔여 미사용 템플릿
- `projects/static/js/kanban.js` (드래그 앤 드롭)
- `projects/admin.py` 잔여 등록
- `projects/forms.py` 잔여 폼
- **`projects/management/commands/*.py`** 레거시 모델 참조
- **`projects/telegram/`** 레거시 워크플로우 참조
- **`projects/services/voice/`** 레거시 워크플로우 참조
- **`tests/*.py` 및 `conftest.py`** 레거시 모델/enum 참조
- **`projects/urls.py`** 레거시 라우트 및 역참조

### 3.2 최종 검증 파일
- `pyproject.toml`, `uv.lock` (의존성 변화 없음 예상)
- `CLAUDE.md` (필요 시 문서 업데이트)

## 4. 태스크 분할

### T6.1 — 레포 전체 레거시 grep 스캔

**스캔 범위**: 레포 전체 (docs/, migrations/, .venv/ 제외)

**작업**:
```bash
# Contact/Offer 모델 전체 참조 (word boundary, 멀티라인 import 포함)
rg -n '\b(Contact|Offer)\b' projects/ tests/ conftest.py \
  --glob '!**/migrations/**' --glob '!docs/**'

# ProjectStatus — 제거된 10-state 멤버만 (OPEN/CLOSED는 유지)
rg -n 'ProjectStatus\.(NEW|SEARCHING|RECOMMENDING|INTERVIEWING|NEGOTIATING|ON_HOLD|PENDING_APPROVAL|CLOSED_SUCCESS|CLOSED_FAIL|CLOSED_CANCEL)' \
  projects/ tests/

# 기존 10-state 문자열 (전체 제거 대상)
rg -n 'new|searching|recommending|interviewing|negotiating|closed_success|closed_fail|closed_cancel|on_hold|pending_approval' \
  projects/ tests/ --glob '*.py' --glob '*.html' --glob '!**/migrations/**'

# services/lifecycle 잔여 import
rg -n 'services\.lifecycle|from \.lifecycle import' projects/ tests/

# 기존 status_update 참조
rg -n 'status_update' projects/ tests/

# 비-projects 앱에서 projects.models 레거시 import
rg -n 'from projects\.models import.*(Contact|Offer|Submission)' . \
  --glob '!docs/**' --glob '!**/migrations/**'
```

**산출물**: 각 결과에 대해 "유지 / 삭제 / 수정" 결정 후 일괄 정리.

---

### T6.2 — views.py 최종 정리
**파일**: `projects/views.py`
**작업**:
- T6.1 결과에서 views.py 관련 참조 모두 제거
- 미사용 import 삭제 (`Contact`, `Offer`, `Submission.Status` 등)
- **`ProjectStatus` import는 유지** (활성 enum)
- 레거시 뷰 함수 제거 (offer CRUD, contact CRUD, 10-state 전환 등)
- `ruff check projects/views.py` 통과

---

### T6.3 — services 최종 정리
**파일들**: `projects/services/*.py`
**작업**:
- 각 파일에서 Contact/Offer grep 후 정리
- 특히:
  - `services/lifecycle.py` 완전 삭제 (Phase 2에서 결정)
  - `services/dashboard.py` 잔여 status 집계 제거 (**ProjectStatus.OPEN/CLOSED 참조는 유지**)
  - `services/collision.py` 잔여 참조 제거 (**ProjectStatus.CLOSED 참조는 유지**)
  - `services/auto_actions.py` 잔여 트리거 제거
  - `services/urgency.py` 레거시 주석 정리
- 필요 시 import 정리

---

### T6.4 — forms.py 최종 정리
**파일**: `projects/forms.py`
**작업**:
- `OfferForm` 완전 삭제 (Phase 3에서 시작했지만 잔여 확인)
- `ProjectStatusForm` 삭제 (10-state 전환 폼)
- `SubmissionStatusForm` 삭제
- 미사용 import 제거

---

### T6.5 — admin.py 최종 정리
**파일**: `projects/admin.py`
**작업**:
- Contact admin 등록 제거
- Offer admin 등록 제거
- ActionType admin 등록 확인 (Phase 1에서 추가됨)
- Application, ActionItem admin 등록 (개발 편의용) — 선택

---

### T6.6 — 템플릿 최종 정리

**선행 필수: 역참조 스캔**
```bash
# 삭제 후보 템플릿의 참조 확인
for tpl in tab_offers dash_pipeline view_board_card offer_form; do
  echo "=== $tpl ==="
  rg -n "$tpl" projects/ --glob '*.py' --glob '*.html'
done
```

**참조 카운트 0인 파일만 삭제. 참조가 있는 파일은 호출부를 먼저 수정.**

**파일들**: `projects/templates/projects/`
**작업**:
- 역참조 스캔 결과에 따라 삭제/수정 결정
- **`dash_full.html`은 삭제 금지** (dashboard.html:12 및 views.py:2105에서 활성 사용 중)
- 상위 템플릿에서 `{% include %}` 참조 제거 (삭제 대상 파일에 대해)
- `view_filters.html`에서 레거시 상태 옵션 제거 (`searching` 등)

**삭제 후보** (역참조 스캔으로 확인 후):
- `partials/tab_offers.html`
- `partials/dash_pipeline.html`
- `partials/view_board_card.html`
- `partials/offer_form.html`
- 기타 참조 0인 레거시 partial

---

### T6.7 — 정적 자산 정리
**파일**: `projects/static/js/kanban.js`
**작업**:
- 새 칸반은 드래그 앤 드롭 없음
- 파일 전체 제거 또는 새 용도로 재작성 (빈 파일만 유지도 OK)
- base 템플릿에서 `<script>` 참조 제거

---

### T6.8 — URL 정리 (확장)
**파일**: `projects/urls.py`
**작업**:
- 주석 처리된 구 라우트 제거
- **레거시 라우트 역참조 분석**:
  ```bash
  # 레거시 라우트명 역참조 스캔
  rg -n 'offer_create|offer_update|offer_delete|offer_accept|offer_reject|project_tab_offers|status_update|contact_' \
    projects/ tests/ --glob '*.py' --glob '*.html'
  
  # reverse() 호출에서 레거시 패턴
  rg -n "reverse\(.*offer|reverse\(.*contact|reverse\(.*status_update" \
    projects/ tests/ --glob '*.py'
  
  # {% url %} 태그에서 레거시 패턴
  rg -n "url '.*offer|url '.*contact|url '.*status_update" \
    projects/templates/ --glob '*.html'
  ```
- 레거시 라우트 삭제 시 연결된 뷰 함수/템플릿도 함께 제거
- 이름 충돌 확인 (`show_urls` 커맨드 사용)

---

### T6.9 — Management Commands 정리
**파일들**: `projects/management/commands/*.py`
**작업**:
- `check_due_actions.py`: Contact import 제거, Contact.objects 쿼리 제거/대체
- `send_reminders.py`: Contact/Interview/Submission import 제거, 레거시 워크플로우 제거/대체
- 각 커맨드가 정리 후에도 `--help` 실행 가능한지 smoke test
- Telegram handlers (`projects/telegram/`) 레거시 참조 정리
- Voice services (`projects/services/voice/`) 레거시 참조 정리

---

### T6.10 — `ruff check` / `ruff format`
**작업**:
```bash
uv run ruff check .
uv run ruff format .
```

**예상**: 
- `ruff check`가 에러 없이 통과
- `ruff format`이 변경 사항을 적용 (있다면)
- 수정된 파일이 있으면 커밋에 포함

---

### T6.10a — Migration drift 검증
**작업**:
```bash
# 미생성 migration 확인 (Phase 6이 모델을 실수로 변경했는지)
uv run python manage.py makemigrations --check --dry-run

# migration 상태 확인
uv run python manage.py showmigrations projects
```

**예상**: Phase 6은 코드 정리만이므로 새 migration이 생기면 안 된다. 생기면 원인 조사.

---

### T6.11 — 전체 테스트 재실행
**작업**:
```bash
uv run pytest -v
```

**예상**: Phase 5에서 만든 테스트 + 기존 유지 테스트 전부 통과.

---

### T6.12 — `manage.py check` 전체 + stale content type 점검
**작업**:
```bash
uv run python manage.py check
uv run python manage.py check --deploy

# stale content type 점검 (삭제된 Contact/Offer 모델의 잔여 메타데이터)
uv run python manage.py remove_stale_contenttypes --dry-run
```

**예상**: 에러 0, 경고 0 (또는 프로덕션 관련 무시 가능한 경고만). stale content type이 있으면 기록만 하고 별도 migration에서 처리.

---

### T6.13 — 개발 DB 클린 재생성 + 수동 seed
**작업**:
```bash
docker compose down -v
docker compose up -d
sleep 3
uv run python manage.py migrate
uv run python manage.py seed_action_types  # Phase 5에서 추가한 커맨드
# (선택) seed_from_excel --consultant=김현정 --limit=5
```

**검증**:
- ActionType 23개 존재
- Project, Application 0건 (또는 seed 데이터)

---

### T6.14 — `/browse` 스킬로 E2E 확인
**작업**:
1. 개발 서버 기동:
   ```bash
   uv run python manage.py runserver 0.0.0.0:8000
   ```
2. 브라우저 자동화로 확인:
   - `/dashboard/` 접근 → 빈 상태 표시 확인
   - `/projects/` 접근 → 3컬럼 칸반 (빈 상태)
   - 관리자 페이지 `/admin/projects/actiontype/` → 23개 ActionType 표시
   - 프로젝트 생성 플로우:
     - 새 Project 생성 → 상세 페이지 이동
     - 후보자 추가 모달 → DB 검색 탭 → 기존 Candidate 선택 → Application 생성
     - ActionItem 추가 → reach_out 타입 선택 → 생성
     - ActionItem 완료 → 후속 제안 모달 → 선택 → 새 액션 생성
     - 대시보드 재방문 → 새 ActionItem이 "오늘 할 일"에 표시
3. 각 단계별 스크린샷 저장
4. 이슈 발견 시 즉시 수정·재테스트

---

### T6.15 — 문서 최종 업데이트
**파일**: `docs/designs/20260414-project-application-redesign/README.md`
**작업**:
- 구현 완료 날짜 기록
- 실제 소요 시간 기록 (예상과 비교)
- 발견된 이슈 및 해결 기록
- Phase 6 완료 후 `plan-forge-batch` 결과 링크 (있다면)

---

### T6.16 — 커밋 및 브랜치 준비
**작업**:
```bash
git status
git diff --stat
git add .
git commit -m "..."
```

**최종 커밋 메시지**:
```
chore(projects): remove legacy references and finalize redesign

- Remove all Contact/Offer model references (code only, tables retained)
- Clean up views.py, services/, forms.py, admin.py, management commands
- Delete legacy templates (tab_offers, dash_pipeline, view_board_card)
- Clean up legacy URL routes and reverse references
- Remove retired 10-state ProjectStatus members (keep OPEN/CLOSED)
- ruff check/format clean
- pytest full suite passing
- E2E verified via /browse tool

Closes: Project/Application redesign
Refs: docs/designs/20260414-project-application-redesign/FINAL-SPEC.md
```

**브랜치 상태**: `feat/project-application-redesign`이 머지 준비 완료.

---

## 5. 검증 체크리스트

- [ ] `rg -n '\b(Contact|Offer)\b' projects/ tests/ conftest.py --glob '!**/migrations/**'` 결과 0건
- [ ] `rg -n 'ProjectStatus\.(NEW|SEARCHING|...)' projects/ tests/` 결과 0건
- [ ] 레거시 10-state 문자열 스캔 결과 0건
- [ ] `rg -n 'services\.lifecycle' projects/ tests/` 결과 0건
- [ ] `ruff check .` 에러 0, 경고 0
- [ ] `ruff format .` 적용됨
- [ ] `makemigrations --check --dry-run` 통과 (drift 없음)
- [ ] `pytest -v` 전체 통과
- [ ] `manage.py check` 통과
- [ ] `manage.py check --deploy` 통과
- [ ] `remove_stale_contenttypes --dry-run` 결과 확인
- [ ] Management commands smoke test (--help 실행)
- [ ] 개발 서버 정상 기동
- [ ] `/dashboard/`, `/projects/`, `/admin/projects/actiontype/` 브라우저 접근 가능
- [ ] 프로젝트 생성 → 후보자 추가 → ActionItem 완료 E2E 플로우 성공
- [ ] 스크린샷 수집 완료

## 6. 리스크와 대응

| 리스크 | 대응 |
|---|---|
| ruff check에서 새 lint 규칙 경고 | `ruff format` 먼저 실행, 남은 경고는 개별 판단 |
| 기존 테스트에서 삭제된 모델 참조 | 레포 전체 grep으로 사전 감지 후 제거 |
| `/browse` 스킬 실행 실패 | 수동 브라우저 확인으로 대체, 스크린샷만 확보 |
| 배포 환경 체크(`--deploy`) 경고 | DEBUG/SECRET_KEY/ALLOWED_HOSTS 관련은 개발 환경 무시 가능 |
| 템플릿 삭제 후 TemplateDoesNotExist | 역참조 스캔 필수 선행. 참조 0건 확인 후만 삭제 |
| Management command 런타임 실패 | 각 커맨드 --help smoke test로 import 검증 |
| Migration drift (실수로 모델 변경) | `makemigrations --check --dry-run` 게이트로 차단 |
| Stale content types (삭제된 모델 잔여) | `remove_stale_contenttypes --dry-run`으로 확인, 별도 migration에서 처리 |

## 7. 커밋 포인트

위 T6.16 커밋. 총 6개 커밋(Phase 1~6 각각 1개)이 `feat/project-application-redesign` 브랜치에 남음.

## 8. 머지 조건

- 모든 Phase 1~6 커밋이 순서대로 쌓임
- 최종 pytest + ruff + check 통과
- E2E 스크린샷 확보
- 사장님 검토 완료 후 `main` 브랜치로 머지
- **운영 배포는 RBAC 작업(`feat/rbac-onboarding`)과 분리**, 두 큰 변화를 동시에 배포하지 않음

---

**이전 Phase**: [phase-5-tests.md](phase-5-tests.md)
**구현 완료**: 이 문서까지 완료 시 재설계 전체 구현 완료.

<!-- forge:phase-6-cleanup:impl-plan:complete:2026-04-14T13:30:00Z -->
