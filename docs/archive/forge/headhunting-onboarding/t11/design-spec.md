# t11: NotificationPreference 모델 추가

> **Phase:** 2단계 — 통합 설정 + 조직 관리
> **선행 조건:** 1단계 (RBAC + 온보딩) 구현 완료 (t01-t10)

---

## 배경

1단계에서 역할 체계(owner/consultant/viewer)와 초대코드 기반 온보딩이 도입되었다.
통합 설정 페이지의 "알림 설정" 탭을 위해, 사용자별 알림 수신 여부를 저장하는 모델이 필요하다.

현재 알림 설정은 "준비 중" 상태로만 표시되며, 데이터 모델이 없다. 이 태스크에서 모델과 마이그레이션을 먼저 준비한다.

---

## 요구사항

### NotificationPreference 모델

`accounts.models.NotificationPreference` — User와 OneToOne 관계.

| 필드 | 타입 | 설명 |
|------|------|------|
| user | OneToOneField(User) | 사용자 참조 |
| preferences | JSONField | 알림 유형별 채널 on/off |

`preferences` 기본값 구조:

```json
{
  "contact_result": {"web": true, "telegram": true},
  "recommendation_feedback": {"web": true, "telegram": true},
  "project_approval": {"web": true, "telegram": true},
  "newsfeed_update": {"web": true, "telegram": false}
}
```

### 알림 유형 매핑

| 알림 유형 | 키 | 웹 기본 | 텔레그램 기본 |
|----------|-----|---------|-------------|
| 새 컨택 결과 | contact_result | O | O |
| 추천 피드백 | recommendation_feedback | O | O |
| 프로젝트 승인 요청 | project_approval | O | O |
| 뉴스피드 업데이트 | newsfeed_update | O | X |

> **Note:** 알림 발송 로직 자체는 이 단계에서 구현하지 않는다. 모델만 준비한다.

---

## 제약

- `BaseModel`을 상속하여 `created_at`, `updated_at` 필드를 자동으로 포함한다.
- Admin 등록 필수.
- 마이그레이션 생성 및 적용까지 포함.
