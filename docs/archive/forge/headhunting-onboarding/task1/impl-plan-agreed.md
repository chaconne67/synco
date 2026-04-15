# Task 1: InviteCode 모델 + Membership.status 추가

**Source:** `docs/forge/headhunting-onboarding/phase1/impl-plan-agreed.md` Task 1 섹션 (line 41-300)

**Files:**
- Modify: `accounts/models.py`
- Modify: `accounts/admin.py`
- Test: `tests/accounts/test_invite_code.py`

**구현 커밋:** `ffaba5a` — feat(accounts): add InviteCode model and Membership.status field

**검증 대상:**
1. InviteCode 모델이 정상 동작하는지 (생성, is_valid, use)
2. Membership.status 필드가 active/pending/rejected 상태를 지원하는지
3. InviteCode admin 등록이 되어 있는지
4. migration이 정상 적용되었는지
5. 테스트가 모두 통과하는지

<!-- forge:task1:구현담금질:complete:2026-04-12T02:00:00+09:00 -->
