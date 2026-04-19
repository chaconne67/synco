# Clients 메뉴 UI 리디자인 — 핸드오프

**상태:** 구현 완료(커밋 b0902c2..e42e141). 운영 마이그레이션 미적용, 브라우저 수동 QA 대기.

## 복귀 절차

1. `git log --oneline 9e17ba7..HEAD` — 이번 스프린트 커밋 전수(Task 1–20).
2. 운영 미적용 마이그레이션 확인:
   ```
   ssh chaconne@49.247.46.171 \
     "docker exec \$(docker ps -qf name=synco_web) python manage.py showmigrations clients | grep '\[ \]'"
   ```
   0003/0004/0005 세 건 미적용 예상.
3. `uv run python manage.py runserver 0.0.0.0:8000` — 로컬 브라우저로 QA 체크리스트 실행.
4. QA 통과 시 사용자 승인 후 `./deploy.sh`.

## TODO (사용자 액션)

- [ ] 로컬 수동 QA (아래 체크리스트).
- [ ] QA 통과 후 운영 배포 승인 (`./deploy.sh` 실행 지시).
- [ ] 배포 후 `/clients/` 접속해 카테고리 카운트·카드 그리드 정상인지 확인.

## QA 체크리스트

**리스트 `/clients/`:**
- [ ] 헤더 카운트, 11개 카테고리 칩, 3-up 그리드, 카드 hover lift
- [ ] 칩 0건일 때 disabled, 활성 칩 `is-active`
- [ ] Filters 드롭다운: 규모/지역/거래건수/성사이력 조합
- [ ] Infinite scroll: 9건 이후 자동 로드
- [ ] 카드 상단 영역 클릭 → website 새 창(없으면 비활성), 하단 클릭 → 상세

**상세 `/clients/<pk>/`:**
- [ ] 프로필 카드(로고/웹사이트/설명/4-up 통계)
- [ ] 좌측: 담당자 카드, 계약 이력
- [ ] 우측: 프로젝트 세그먼티드 컨트롤(진행중/완료/전체) HTMX 전환
- [ ] 메모 섹션(있을 때만)
- [ ] 케밥 메뉴 → 수정/삭제

**폼 `/clients/new/` · `/clients/<pk>/edit/`:**
- [ ] 기본 정보 섹션(이름/업종/규모/지역/웹사이트/설명)
- [ ] 로고 업로드: 미리보기, 확장자(jpg/png/svg/webp)·2MB 검증
- [ ] 수정 폼: 기존 로고 썸네일 + 삭제 체크박스
- [ ] 담당자 JSON: 추가/삭제 왕복
- [ ] 메모 섹션

**삭제 가드:**
- [ ] 프로젝트(open/closed 무관) 있을 때 차단 배너
- [ ] 없을 때 삭제 성공 → 리스트 리다이렉트

## 제약 (Why)

- **카드 `📧` `⭐` 아이콘은 장식.** 이메일/즐겨찾기는 후속 phase — MVP 범위 외.
- **프로젝트 리스트 최근 20건 제한.** "전체 보기" 미구현 — 현재 수요 없음, 추가 시 별도 페이지.
- **로고는 원본 저장만.** 썸네일/webp 변환 없음 — Pillow만 의존성으로 추가, imagekit·thumbnail 도입 회피.
- **데이터 마이그레이션 KEYWORD_MAP 은 제한적.** 매칭 실패 텍스트 모두 "기타" — 배포 후 운영자가 shell 로 재분류 필요할 수 있음.
- **`Project.client` on_delete=CASCADE 유지.** 삭제 가드로 실질 차단. DB 레벨 PROTECT 승격은 후속 과제.

## 후속 과제

- `Project.client` → `on_delete=PROTECT` 승격(가드 중복이지만 DB 방어)
- 로고 썸네일 자동 생성
- `manage.py reclassify_industries` 커맨드 — 키워드 재분류
