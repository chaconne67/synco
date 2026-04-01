# Voice UI/UX 점검 보고서 R3

> **점검일:** 2026-03-31
> **점검 방식:** 제로베이스 코드 리뷰 (기존 R1/R2 보고서 미참조)
> **대상 파일:**
> - `candidates/static/candidates/chatbot.js`
> - `candidates/templates/candidates/partials/chatbot_modal.html`
> - `candidates/templates/candidates/search.html`
> - `candidates/templates/candidates/partials/chat_messages.html`
> - `candidates/templates/candidates/partials/search_status_bar.html`

---

## 1. 플로팅 버튼 — 음성 검색 인지성

### 1.1 아이콘 선택 — PASS
- `search.html:105-108` — 마이크 SVG 아이콘 사용. 음성 입력 기능임을 즉시 인지 가능.
- `aria-label="음성 검색"` 적용되어 있음.

### 1.2 첫 방문 온보딩 툴팁 — PASS (경미한 개선 여지)
- `search.html:93-98` — "음성으로 검색해보세요" 툴팁이 FAB 위에 표시됨.
- `chatbot.js:607-625` — `localStorage`로 1회만 표시, 6초 후 자동 소멸, 첫 클릭 시 즉시 소멸.
- `animate-bounce`로 시선 유도.

**지적 사항:**
| # | 파일:라인 | 문제 | 심각도 | 수정 방향 |
|---|-----------|------|--------|-----------|
| 1.2a | `search.html:95` | 툴팁 `animate-bounce`에 `animation-iteration-count:3`이 설정되어 있지만, `input.css:16-22`의 `prefers-reduced-motion` 미디어쿼리가 전역적으로 `animation-duration: 0.01ms`를 적용하므로 reduced-motion 사용자에게는 사실상 보이지 않을 수 있음. 대체 표현(예: 정적 화살표 + 밑줄)이 없음 | LOW | reduced-motion 시 정적 스타일 폴백 추가 |
| 1.2b | `search.html:100` | FAB 버튼 크기 `w-14 h-14` (56px)로 44px 최소 터치 타겟 충족. 데스크톱은 `lg:w-[60px] lg:h-[60px]`. | — | PASS |

### 1.3 FAB 위치 — PASS
- `search.html:91` — `fixed bottom-6 right-4 lg:right-6 z-40`. 모바일/데스크톱 모두 접근 용이한 위치.

---

## 2. 모달 내부 — 음성 입력이 주 입력임을 시각적으로 전달하는가

### 2.1 레이아웃 계층 — PASS
- `chatbot_modal.html:57-88` — 음성 입력 영역(`voice-input-area`)이 기본 표시, 텍스트 입력 영역(`text-input-area`)은 `hidden`.
- 마이크 버튼이 중앙 배치(`flex flex-col items-center`), 크기 `w-14 h-14` (56px)로 시각적 주인공.
- "키보드로 입력" 링크가 하단에 작은 텍스트(`text-xs text-gray-400`)로 보조 역할 명시.

### 2.2 텍스트 ↔ 음성 전환 — PASS
- `chatbot_modal.html:93` — 텍스트 입력 모드에서 마이크 아이콘 버튼으로 음성 복귀 가능.
- `chatbot.js:46-61` — `showTextInput()` / `hideTextInput()` 토글 구현.

### 2.3 초기 인사 메시지 — PASS
- `chatbot_modal.html:35` — "안녕하세요! 마이크를 눌러 음성으로 검색하세요."
- 예시 칩 3개 제공 (`보험 영업 경력 10년`, `삼성전자 출신 HR`, `강남 30대 여성`).
- 칩 클릭 시 `searchWithChip()` 호출로 즉시 검색 실행.

**지적 사항:**
| # | 파일:라인 | 문제 | 심각도 | 수정 방향 |
|---|-----------|------|--------|-----------|
| 2.3a | `chatbot_modal.html:38-49` | 예시 칩 버튼의 터치 타겟이 `px-3 py-1` + `text-[13px]`으로, 높이가 약 28px 수준. WCAG 2.2 권고 최소 터치 타겟 44x44px에 미달 | MEDIUM | `py-2` 이상으로 높이 확보하거나 `min-h-[44px]` 적용 |
| 2.3b | `chat_messages.html:6-16` | 히스토리 로드 시에도 동일한 칩이 표시되는데, 이 칩들에도 동일한 터치 타겟 이슈 존재 | MEDIUM | 위와 동일 |

---

## 3. 녹음 중 시각적 피드백

### 3.1 마이크 버튼 상태 변화 — PASS
- `chatbot.js:436-472` — `setMicState()` 함수가 3가지 상태(idle/recording/processing) 명확히 구분:
  - **idle:** `bg-primary` + 마이크 아이콘 + "마이크를 눌러 말씀하세요"
  - **recording:** `bg-red-500` + `scale-110` + 정지(■) 아이콘 + "듣고 있습니다..."
  - **processing:** `bg-gray-400` + 스피너 + "음성 인식 중..."

### 3.2 실시간 오디오 레벨 — PASS
- `chatbot.js:191-245` — `AudioContext` + `AnalyserNode`로 실시간 주파수 데이터 분석.
- 볼륨 정규화(0~1) 후 펄스 링 `scale`과 `opacity`를 동적 조절.
- `requestAnimationFrame` 루프로 부드러운 업데이트.

### 3.3 펄스 링 애니메이션 — PASS
- `chatbot_modal.html:61-62` — 2중 펄스 링(`mic-pulse-ring`, `mic-pulse-ring-2`).
- 녹음 시작 시 `hidden` 해제, JS에서 오디오 레벨에 따라 동적 크기 조절.

### 3.4 녹음 타이머 — PASS
- `chatbot.js:111-143` — `startRecordingTimer()` / `stopRecordingTimer()`.
- MM:SS 형식, 1초 간격 업데이트.
- 잔여 10초 이하 시 `animate-pulse` 추가로 긴급감 표현.
- 60초 자동 중지(`MAX_RECORDING_SECONDS`).

### 3.5 reduced-motion 대응 — PASS
- `chatbot.js:22` — `prefers-reduced-motion` 감지.
- `chatbot.js:213-221` — reduced-motion 시 펄스 링 대신 수평 레벨 바(`mic-level-bar`) 표시.
- `input.css:16-22` — 전역 애니메이션 최소화.

**지적 사항:**
| # | 파일:라인 | 문제 | 심각도 | 수정 방향 |
|---|-----------|------|--------|-----------|
| 3.5a | `chatbot.js:22` | `prefersReducedMotion`이 페이지 로드 시 한 번만 평가됨. 사용자가 OS 설정을 변경해도 반영되지 않음 | LOW | `matchMedia.addEventListener('change', ...)` 리스너 등록 |

---

## 4. 텍스트 입력과 음성 입력의 관계

### 4.1 주/보조 관계 명확성 — PASS
- 음성이 기본(voice-input-area 표시), 텍스트는 토글 후 접근(text-input-area hidden).
- "키보드로 입력" 라벨이 명시적.

### 4.2 텍스트 입력 UX — PASS
- `chatbot_modal.html:99-104` — Enter 키로 전송, 전용 전송 버튼 존재.
- placeholder "텍스트로 입력하세요..." 명확.

**지적 사항:**
| # | 파일:라인 | 문제 | 심각도 | 수정 방향 |
|---|-----------|------|--------|-----------|
| 4.2a | `chatbot_modal.html:104` | `onkeydown="if(event.key==='Enter')sendMessage()"` — IME 입력 중(한국어 조합 중) Enter가 `isComposing` 상태일 때도 전송됨. 한국어 입력 시 의도치 않은 전송 발생 가능 | **HIGH** | `event.isComposing` 체크 추가: `if(event.key==='Enter' && !event.isComposing) sendMessage()` |
| 4.2b | `chatbot_modal.html:106` | 전송 버튼 크기 `w-10 h-10` (40px)으로 44px 최소 터치 타겟에 2px 부족 | LOW | `w-11 h-11` 또는 `min-w-[44px] min-h-[44px]` |

---

## 5. 음성 → 결과 표시 흐름의 연속성

### 5.1 녹음 완료 → 서버 전송 → 결과 표시 — PASS
- `chatbot.js:268-330` — `handleRecordingComplete()`:
  1. `setMicState("processing")` — 즉시 시각적 전환
  2. "음성 인식 중..." 상태 텍스트 표시
  3. 서버 응답 → 인식 텍스트를 사용자 메시지로 표시 (`isVoice` 마이크 이모지 포함)
  4. `doSearch()` 호출 → "생각 중..." 인디케이터 표시
  5. 결과 수신 → AI 응답 표시 + 상태바 업데이트 + 후보자 리스트 새로고침

### 5.2 상태바 → 모달 재진입 — PASS
- `chatbot.js:519-527` — 검색 후 상태바에 "🔍 '쿼리' — N명 찾음" 표시.
- `search_status_bar.html:2` — 상태바 클릭 시 `toggleChatbot()` 호출로 대화 재진입.

### 5.3 세션 유지 — PASS
- `chatbot.js:7` — URL 파라미터 또는 `sessionStorage`에서 세션 복원.
- `chatbot.js:370` — 검색 후 `history.replaceState`로 URL에 session_id 반영.
- `chatbot.js:493-511` — `loadChatHistory()`로 모달 재오픈 시 이전 대화 복원.

**지적 사항:**
| # | 파일:라인 | 문제 | 심각도 | 수정 방향 |
|---|-----------|------|--------|-----------|
| 5.3a | `chatbot.js:513-517` | `refreshCandidateList()`가 `htmx.ajax`를 사용하는데, `htmx`가 로드되지 않았거나 지연 로드인 경우 에러 발생 가능. 방어 코드 없음 | LOW | `if (typeof htmx !== 'undefined')` 가드 추가 |

---

## 6. 에러 상태별 구체적 안내

### 6.1 마이크 권한 에러 — PASS
- `chatbot.js:170-180` — 에러 타입별 분기:
  - `NotAllowedError` → `showMicPermissionError()` (상세 안내)
  - `NotFoundError` → "마이크가 연결되어 있지 않습니다"
  - `NotReadableError` → "마이크가 다른 앱에서 사용 중입니다"
  - 기타 → "마이크를 사용할 수 없습니다. 텍스트로 입력해주세요"

### 6.2 마이크 권한 거부 상세 안내 — PASS
- `chatbot.js:479-491` — `showMicPermissionError()`:
  - 빨간 배경(`bg-red-50`)으로 시각적 구분
  - "브라우저 주소창 왼쪽 🔒 아이콘 → 마이크 → 허용으로 변경해주세요" 구체적 안내
  - "텍스트로 검색" 링크 제공 (폴백 경로)

### 6.3 음성 인식 결과 에러 — PASS
- `chatbot.js:308-311` — 빈 텍스트/무음 감지: "음성이 감지되지 않았습니다. 다시 말씀해주세요."
- `chatbot.js:321` — Rate limit: 서버 메시지 또는 "요청이 너무 많습니다. 잠시 후 다시 시도해주세요."
- `chatbot.js:323` — 인증 에러: "로그인이 필요합니다. 페이지를 새로고침해주세요."
- `chatbot.js:325` — 오프라인: "인터넷 연결을 확인해주세요."
- `chatbot.js:327` — 기타: "음성 인식에 실패했습니다. 텍스트로 입력해주세요."

### 6.4 검색 에러 — PASS
- `chatbot.js:372-384` — `doSearch()` catch 블록에서 동일한 분류 적용 (rate limit, auth, offline, 기타).

### 6.5 파일 크기 초과 — PASS
- `chatbot.js:273-276` — 10MB 초과 시 프론트엔드 차단 + 안내 메시지.

**지적 사항:**
| # | 파일:라인 | 문제 | 심각도 | 수정 방향 |
|---|-----------|------|--------|-----------|
| 6.5a | `chatbot.js:275` | blob 크기 초과 시 `appendAIMessage()`를 사용하지만, 이 메시지가 대화 히스토리에 남게 됨. 세션 로드 시 서버에서 반환되지 않으므로 불일치. 다만 기능적 문제는 아님 | LOW | `showToast()` 사용이 더 적절할 수 있음 |

---

## 7. 모바일 UX

### 7.1 바텀시트 레이아웃 — PASS
- `chatbot_modal.html:8-11` — 모바일: `bottom-0 left-0 right-0 h-[85vh] rounded-t-2xl` (바텀시트). 데스크톱: `lg:bottom-6 lg:right-6 lg:w-[380px] lg:h-[520px] lg:rounded-2xl` (플로팅 카드).

### 7.2 드래그 투 클로즈 — PASS
- `chatbot_modal.html:27-29` — 모바일 전용 드래그 핸들 (`lg:hidden`), 시각적 그랩 바 (`w-10 h-1 bg-gray-300 rounded-full`).
- `chatbot.js:559-604` — 터치 이벤트로 드래그 처리, 100px 임계값 초과 시 닫힘, `translateY` 애니메이션.

### 7.3 safe-area 대응 — PASS
- `chatbot_modal.html:56` — 입력바에 `safe-area-pb` 클래스 적용.
- `static/css/input.css:25-27` — `padding-bottom: env(safe-area-inset-bottom)` 정의.
- `base.html:6` — `viewport-fit=cover` 적용.

### 7.4 키보드 팝업 대응 — 점검 필요

**지적 사항:**
| # | 파일:라인 | 문제 | 심각도 | 수정 방향 |
|---|-----------|------|--------|-----------|
| 7.4a | `chatbot_modal.html:8` | 모바일에서 `h-[85vh]` 고정 높이 사용. 모바일 키보드가 올라오면 `vh` 단위는 키보드를 포함하지 않으므로, 입력 필드가 키보드에 가려질 수 있음 | **HIGH** | `h-[85dvh]` (dynamic viewport height) 사용 또는 `visualViewport` API로 높이 동적 조절. iOS Safari에서 특히 문제됨 |
| 7.4b | `chatbot_modal.html:8` | 모달이 `fixed` 포지셔닝인데, iOS Safari에서 `position: fixed` + 소프트 키보드 조합 시 스크롤/위치 버그가 빈번함 | MEDIUM | `visualViewport.resize` 이벤트 리스닝으로 모달 높이 보정, 또는 키보드 표시 시 `position: absolute`로 전환 |

### 7.5 터치 타겟 — 부분 PASS
- 닫기 버튼: `min-w-[44px] min-h-[44px]` — PASS (`chatbot_modal.html:19`).
- 마이크 버튼: `w-14 h-14` (56px) — PASS.
- FAB 버튼: `w-14 h-14` (56px) — PASS.
- 예시 칩: ~28px 높이 — FAIL (2.3a 참조).
- 전송 버튼: `w-10 h-10` (40px) — FAIL (4.2b 참조).

---

## 8. 첫 사용자 온보딩

### 8.1 FAB 툴팁 — PASS
- 첫 방문 시 "음성으로 검색해보세요" 바운스 툴팁 (1.2 참조).
- `localStorage`로 1회 표시 제어.

### 8.2 모달 내 가이드 — PASS
- 인사 메시지 + 예시 문구 + 클릭 가능 칩으로 첫 사용자 진입 장벽 낮춤.

### 8.3 재진입 경로 — PASS
- FAB 버튼 항상 표시.
- 상태바 클릭으로 이전 대화 재진입.
- URL session_id로 새로고침 후에도 세션 유지.

**지적 사항:**
| # | 파일:라인 | 문제 | 심각도 | 수정 방향 |
|---|-----------|------|--------|-----------|
| 8.3a | `chatbot.js:607-625` | 온보딩 툴팁이 모달 외부(FAB)에만 있음. 모달을 열었을 때 음성 버튼 자체에 대한 추가 가이드(예: 첫 사용 시 마이크 버튼 주변 하이라이트/리플)는 없음. 현재 인사 메시지로 충분할 수 있으나, 마이크 버튼과 텍스트 안내 사이의 시각적 연결이 약함 | LOW | 첫 사용 시 마이크 버튼에 pulse 효과 또는 화살표로 시선 유도 |

---

## 9. 접근성

### 9.1 ARIA 속성 — PASS
- `chatbot_modal.html:12-14` — `role="dialog"`, `aria-modal="true"`, `aria-label="AI 검색"`.
- `chatbot_modal.html:19` — 닫기 버튼 `aria-label="닫기"`.
- `chatbot_modal.html:66` — 마이크 버튼 `aria-label="음성 검색"`.
- `chatbot_modal.html:93` — 음성 전환 버튼 `aria-label="음성 입력으로 전환"`.
- `chatbot_modal.html:107` — 전송 버튼 `aria-label="전송"`.

### 9.2 키보드 네비게이션 — PASS
- `chatbot.js:550-557` — Escape 키로 모달 닫기.
- 모든 인터랙티브 요소가 네이티브 `<button>` 또는 `<input>`.

### 9.3 reduced-motion — PASS
- `input.css:16-22` — 전역 애니메이션 최소화.
- `chatbot.js:213-221` — 오디오 레벨 바 폴백.

### 9.4 포커스 관리 — 부분 PASS

**지적 사항:**
| # | 파일:라인 | 문제 | 심각도 | 수정 방향 |
|---|-----------|------|--------|-----------|
| 9.4a | `chatbot.js:24-44` | 모달 열 때 포커스를 모달 내부로 이동시키지 않음. 스크린리더 사용자가 모달이 열린 것을 인지하기 어려움 | **MEDIUM** | 모달 열 때 첫 포커스 가능한 요소(마이크 버튼)로 `focus()` 호출 |
| 9.4b | `chatbot.js:24-44` | 포커스 트랩(focus trap)이 없음. 모달 열린 상태에서 Tab 키로 모달 외부 요소에 포커스 가능 | **MEDIUM** | 포커스 트랩 구현 (첫/마지막 요소 순환) |
| 9.4c | `chatbot.js:30-34` | 모달 닫을 때 포커스를 FAB 버튼으로 복원하지 않음. 스크린리더 사용자의 포커스가 사라짐 | MEDIUM | 닫기 시 `document.getElementById('chatbot-toggle').querySelector('button').focus()` |

### 9.5 마이크 버튼 ARIA 상태 — 문제 있음

**지적 사항:**
| # | 파일:라인 | 문제 | 심각도 | 수정 방향 |
|---|-----------|------|--------|-----------|
| 9.5a | `chatbot.js:436-472` | `setMicState()`에서 버튼의 시각적 상태만 변경하고 `aria-label`이나 `aria-pressed`를 업데이트하지 않음. 스크린리더 사용자가 현재 상태(녹음 중/처리 중)를 알 수 없음 | **MEDIUM** | 상태별 `aria-label` 동적 변경: idle→"음성 검색", recording→"녹음 중지", processing→"음성 인식 중" |
| 9.5b | `chatbot.js:474-477` | `updateMicStatus()` 텍스트가 시각적으로만 업데이트됨. `aria-live` 영역이 아니므로 스크린리더에 알림되지 않음 | MEDIUM | `mic-status-text`에 `aria-live="polite"` 추가 |

---

## 요약 — 심각도별 분류

### HIGH (즉시 수정 권장)
| # | 요약 | 파일 |
|---|------|------|
| 4.2a | 한국어 IME 조합 중 Enter 전송 버그 | `chatbot_modal.html:104` |
| 7.4a | 모바일 키보드 팝업 시 `vh` 단위로 인한 입력 필드 가려짐 | `chatbot_modal.html:8` |

### MEDIUM (조기 수정 권장)
| # | 요약 | 파일 |
|---|------|------|
| 2.3a | 예시 칩 버튼 터치 타겟 44px 미달 (~28px) | `chatbot_modal.html:38-49` |
| 2.3b | 히스토리 로드 시 칩 터치 타겟 동일 이슈 | `chat_messages.html:6-16` |
| 7.4b | iOS Safari fixed 포지셔닝 + 키보드 버그 | `chatbot_modal.html:8` |
| 9.4a | 모달 열 때 포커스 미이동 | `chatbot.js:24-44` |
| 9.4b | 포커스 트랩 미구현 | `chatbot.js:24-44` |
| 9.4c | 모달 닫을 때 포커스 미복원 | `chatbot.js:30-34` |
| 9.5a | 마이크 버튼 ARIA 상태 미반영 | `chatbot.js:436-472` |
| 9.5b | 상태 텍스트 aria-live 미적용 | `chatbot.js:474-477` |

### LOW (개선 권장)
| # | 요약 | 파일 |
|---|------|------|
| 1.2a | reduced-motion 시 툴팁 정적 폴백 없음 | `search.html:95` |
| 3.5a | reduced-motion 설정 실시간 반영 안 됨 | `chatbot.js:22` |
| 4.2b | 전송 버튼 40px (44px 미달) | `chatbot_modal.html:106` |
| 5.3a | htmx 미로드 시 방어 코드 없음 | `chatbot.js:513-517` |
| 6.5a | blob 초과 메시지가 대화에 남음 | `chatbot.js:275` |
| 8.3a | 마이크 버튼 시각적 온보딩 부재 | `chatbot.js:607-625` |

### PASS 항목 (문제 없음)
- 플로팅 버튼 아이콘/위치/크기
- 음성=주/텍스트=보조 레이아웃
- 녹음 중 3단계 상태 표시 (idle/recording/processing)
- 실시간 오디오 레벨 시각화
- 녹음 타이머 + 자동 중지
- reduced-motion 오디오 레벨 바 폴백
- 에러 타입별 구체적 안내 (권한 거부 종류별, 무음, 네트워크, rate limit, 인증, 파일 크기)
- 바텀시트 드래그 투 클로즈
- safe-area 대응
- 세션 유지/복원
- 상태바 재진입 경로
- 대화 dialog ARIA 마크업
- Escape 키 닫기
- 전역 reduced-motion CSS

---

## 총평

보이스 퍼스트 검색 인터페이스로서 **핵심 기능과 시각적 피드백은 잘 구현**되어 있음. 음성 입력의 주/보조 위계, 녹음 중 다층 피드백(색상+크기+펄스+타이머+상태텍스트), 에러 분기 처리가 상세함.

**가장 시급한 수정 2건:**
1. **한국어 IME Enter 버그** (4.2a) — 한국어 사용자 전원에게 영향. 1줄 수정으로 해결 가능.
2. **모바일 키보드 `vh` 이슈** (7.4a) — 텍스트 입력 전환 시 입력란이 키보드에 가려져 사용 불가할 수 있음.

접근성 쪽은 포커스 관리(9.4a~c)와 ARIA 상태 반영(9.5a~b)이 주요 개선점. 시각적 사용자에게는 문제없으나, 스크린리더 사용자 경험에 공백이 있음.
