# Phase 6 — 레거시 제거 + 린트 + E2E 확인

**전제**: Phase 5 완료. 핵심 로직 테스트 통과.
**목표**: Phase 1~5에서 임시로 남겨둔 모든 레거시 참조를 완전히 제거. 린트 통과. 개발 서버에서 `/browse` 스킬로 E2E 확인.
**예상 시간**: 0.5일
**리스크**: 낮음

---

## 1. 목표 상태

- `grep -r "ProjectStatus\|class Contact\|class Offer" projects/` 결과 0건
- `uv run ruff check .` 통과 (에러 0, 경고 0)
- `uv run ruff format .` 적용됨
- `uv run pytest -v` 전체 통과
- `uv run python manage.py check --deploy` 통과
- `/browse` 스킬로 주요 플로우 E2E 확인 완료 (스크린샷 포함)
- 브랜치 `feat/project-application-redesign`이 머지 후보 상태

## 2. 사전 조건

- Phase 5 커밋 완료
- 모든 테스트 통과

## 3. 영향 범위

### 3.1 정리 대상 파일 (Phase 1~5에서 임시 주석·stub으로 남겨둔 것)
- `projects/views.py` 잔여 import
- `projects/services/` 잔여 import
- `projects/templates/projects/partials/` 잔여 미사용 템플릿
- `projects/static/js/kanban.js` (드래그 앤 드롭)
- `projects/admin.py` 잔여 등록
- `projects/forms.py` 잔여 폼

### 3.2 최종 검증 파일
- `pyproject.toml`, `uv.lock` (의존성 변화 없음 예상)
- `CLAUDE.md` (필요 시 문서 업데이트)

## 4. 태스크 분할

### T6.1 — 레거시 grep 스캔
**작업**:
```bash
# ProjectStatus enum 전체 참조
grep -rn "ProjectStatus" projects/ --include="*.py"

# Contact 모델 직접 참조
grep -rn "class Contact\b\|from.*import.*Contact\b\|models\.Contact\b" projects/

# Offer 모델 직접 참조
grep -rn "class Offer\b\|from.*import.*Offer\b\|models\.Offer\b" projects/

# 기존 10-state 문자열
grep -rn "closed_success\|closed_fail\|closed_cancel\|on_hold\|pending_approval\|recommending\|negotiating" projects/

# services/lifecycle 잔여 import
grep -rn "services\.lifecycle\|from .lifecycle import" projects/

# 기존 status_update 참조
grep -rn "status_update" projects/
```

**산출물**: 각 결과에 대해 "유지 / 삭제 / 수정" 결정 후 일괄 정리.

---

### T6.2 — views.py 최종 정리
**파일**: `projects/views.py`
**작업**:
- T6.1 결과에서 views.py 관련 참조 모두 제거
- 미사용 import 삭제 (`ProjectStatus`, `Contact`, `Offer`, `Submission.Status` 등)
- 함수 레벨에서 참조 없음 확인
- `ruff check projects/views.py` 통과

---

### T6.3 — services 최종 정리
**파일들**: `projects/services/*.py`
**작업**:
- 각 파일에서 ProjectStatus/Contact/Offer grep 후 정리
- 특히:
  - `services/lifecycle.py` 완전 삭제 (Phase 2에서 결정)
  - `services/dashboard.py` 잔여 status 집계 제거
  - `services/collision.py` 잔여 참조 제거
  - `services/auto_actions.py` 잔여 트리거 제거
- 필요 시 import 정리

---

### T6.4 — forms.py 최종 정리
**파일**: `projects/forms.py`
**작업**:
- `OfferForm` 완전 삭제 (Phase 3에서 시작했지만 잔여 확인)
- `ProjectStatusForm` 삭제
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
**파일들**: `projects/templates/projects/`
**작업**:
```bash
# 레거시 템플릿 파일 확인
ls projects/templates/projects/partials/ | grep -E "offer|status|dash_full|dash_pipeline|view_board_card"
```
- 발견된 파일 삭제
- 상위 템플릿에서 `{% include %}` 참조 제거

**파일 삭제 대상** (Phase 4에서 시작했지만 누락 방지):
- `partials/tab_offers.html`
- `partials/dash_full.html`
- `partials/dash_pipeline.html`
- `partials/view_board_card.html`
- 기타 status 관련 partial

---

### T6.7 — 정적 자산 정리
**파일**: `projects/static/js/kanban.js`
**작업**:
- 새 칸반은 드래그 앤 드롭 없음
- 파일 전체 제거 또는 새 용도로 재작성 (빈 파일만 유지도 OK)
- base 템플릿에서 `<script>` 참조 제거

---

### T6.8 — URL 정리
**파일**: `projects/urls.py`
**작업**:
- 주석 처리된 구 라우트 제거
- 이름 충돌 확인 (`show_urls` 커맨드 사용)

---

### T6.9 — `ruff check` / `ruff format`
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

### T6.10 — 전체 테스트 재실행
**작업**:
```bash
uv run pytest -v
```

**예상**: Phase 5에서 만든 테스트 + 기존 유지 테스트 전부 통과.

---

### T6.11 — `manage.py check` 전체
**작업**:
```bash
uv run python manage.py check
uv run python manage.py check --deploy
```

**예상**: 에러 0, 경고 0 (또는 프로덕션 관련 무시 가능한 경고만).

---

### T6.12 — 개발 DB 클린 재생성 + 수동 seed
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

### T6.13 — `/browse` 스킬로 E2E 확인
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

### T6.14 — 문서 최종 업데이트
**파일**: `docs/designs/20260414-project-application-redesign/README.md`
**작업**:
- 구현 완료 날짜 기록
- 실제 소요 시간 기록 (예상과 비교)
- 발견된 이슈 및 해결 기록
- Phase 6 완료 후 `plan-forge-batch` 결과 링크 (있다면)

---

### T6.15 — 커밋 및 브랜치 준비
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

- Remove all ProjectStatus/Contact/Offer references
- Clean up views.py, services/, forms.py, admin.py
- Delete legacy templates (tab_offers, dash_full, dash_pipeline,
  view_board_card, kanban.js)
- ruff check/format clean
- pytest full suite passing
- E2E verified via /browse tool

Closes: Project/Application redesign
Refs: docs/designs/20260414-project-application-redesign/FINAL-SPEC.md
```

**브랜치 상태**: `feat/project-application-redesign`이 머지 준비 완료.

---

## 5. 검증 체크리스트

- [ ] `grep -rn "ProjectStatus" projects/` 결과 0건
- [ ] `grep -rn "class Contact\b" projects/` 결과 0건
- [ ] `grep -rn "class Offer\b" projects/` 결과 0건
- [ ] `grep -rn "services\.lifecycle" projects/` 결과 0건
- [ ] `ruff check .` 에러 0, 경고 0
- [ ] `ruff format .` 적용됨
- [ ] `pytest -v` 전체 통과
- [ ] `manage.py check` 통과
- [ ] `manage.py check --deploy` 통과
- [ ] 개발 서버 정상 기동
- [ ] `/dashboard/`, `/projects/`, `/admin/projects/actiontype/` 브라우저 접근 가능
- [ ] 프로젝트 생성 → 후보자 추가 → ActionItem 완료 E2E 플로우 성공
- [ ] 스크린샷 수집 완료

## 6. 리스크와 대응

| 리스크 | 대응 |
|---|---|
| ruff check에서 새 lint 규칙 경고 | `ruff format` 먼저 실행, 남은 경고는 개별 판단 |
| 기존 테스트에서 삭제된 모델 참조 | Phase 5에서 정리됐어야 하지만 누락 시 즉시 제거 |
| `/browse` 스킬 실행 실패 | 수동 브라우저 확인으로 대체, 스크린샷만 확보 |
| 배포 환경 체크(`--deploy`) 경고 | DEBUG/SECRET_KEY/ALLOWED_HOSTS 관련은 개발 환경 무시 가능 |
| 생각 못 한 잔여 참조 (e.g., README, docs/) | docs/는 FINAL-SPEC과 plans/만 최종 참조, 나머지 히스토리는 그대로 두되 README에 명시 |

## 7. 커밋 포인트

위 T6.15 커밋. 총 6개 커밋(Phase 1~6 각각 1개)이 `feat/project-application-redesign` 브랜치에 남음.

## 8. 머지 조건

- 모든 Phase 1~6 커밋이 순서대로 쌓임
- 최종 pytest + ruff + check 통과
- E2E 스크린샷 확보
- 사장님 검토 완료 후 `main` 브랜치로 머지
- **운영 배포는 RBAC 작업(`feat/rbac-onboarding`)과 분리**, 두 큰 변화를 동시에 배포하지 않음

---

**이전 Phase**: [phase-5-tests.md](phase-5-tests.md)
**구현 완료**: 이 문서까지 완료 시 재설계 전체 구현 완료.
