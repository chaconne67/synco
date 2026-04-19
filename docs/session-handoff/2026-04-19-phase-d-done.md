# Phase D — 후보자 UI 리디자인 완료 핸드오프

**상태:** Phase D 완료. 코드 main에 반영됨 (origin 푸시 전). 브라우저 수동 QA만 남음.

## 빠른 복귀 절차

1. `git log --oneline ba3b5f7..HEAD` — Phase D 커밋 20여 개
2. 플랜: `docs/superpowers/plans/2026-04-19-candidate-ui-redesign.md`
3. 스펙: `docs/superpowers/specs/2026-04-19-candidate-ui-redesign-design.md`
4. 필요 시 커밋 메시지로 의도 복원

## 변경된 URL (수동 QA 대상)

- `/candidates/` — 헤더·카테고리 칩·카드 v2·하단 고정 검색바
- `/candidates/new/` — 신규 등록 폼 (중복 경고·이력서 업로드)
- `/candidates/<pk>/` — 프로필 헤더·좌측 5섹션·우측 사이드바·4-dot 언어 바

## 수동 회귀 체크리스트

- [ ] 리스트: 헤더·칩·카드·검색바 idle
- [ ] 카드 → 상세 → "Back to Talent Pool" 시 **검색바 재노출** (47a5fb0에서 수정)
- [ ] 검색바: 텍스트 전송·마이크 녹음·STT 자동 전송
- [ ] 카테고리 칩 필터링
- [ ] `/candidates/new/`: 필수 검증·중복 경고·이력서 업로드
- [ ] 상세: Summary·Work·Personal·Matched·Comments·Core Expertise·Education·Certifications·Languages·Activity Snapshot·(있다면) Awards/Patents
- [ ] 프로젝트 컨텍스트 `?project=<uuid>`로 진입 시 "프로젝트에 추가" 버튼

## 알려진 제약 (백로그 — why 보존)

1. **Drive 업로드는 readonly scope 폴백** — `candidates/services/candidate_create.py`의 `_upload_to_drive`가 실패 시 `manual-<uuid>` placeholder를 `drive_file_id`로 저장, Resume는 PENDING으로 생성. 실제 Drive 반영은 scope 확장 이후.
2. **`Category.candidate_count` 백필 필요** — post_save/m2m 시그널로 유지되지만 기존 카테고리는 후보자 변경 전까지 stale. 첫 배포 시 one-off 관리 명령으로 재계산 필요.
3. **Activity Snapshot의 Profile views / Last contacted는 placeholder "준비중"** — 실데이터 소스 미정. 백로그.
4. **`post_delete` 카테고리 카운트 재계산이 O(N 카테고리)** — 현재 20개 수준이라 무해, 카테고리 수 증가 시 `pre_delete`로 스코프 좁히기.

## 선택적 후속 작업 (우선순위 낮음)

- `search_chat` / `voice_transcribe` 뷰 docstring의 "chatbot" 잔재 단어 정리
- `uploaded_file.name` sanitization (`os.path.basename`) — defensive hygiene

## 배포

`./deploy.sh`는 사용자 명시 지시 시에만. 현 시점 자발 배포 금지.
