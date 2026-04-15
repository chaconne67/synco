# Task 2: 데코레이터 + context processor + _get_org 통합

**Source:** `docs/forge/headhunting-onboarding/phase1/impl-plan-agreed.md` Task 2 섹션 (line 302-569)

**Files:**
- Create: `accounts/decorators.py`
- Create: `accounts/context_processors.py`
- Create: `accounts/helpers.py`
- Modify: `main/settings.py`
- Modify: `projects/views.py` — _get_org import 변경
- Modify: `clients/views.py` — _get_org import 변경
- Test: `tests/accounts/test_rbac.py`

**구현 커밋:** `67df8d2` — feat(accounts): add RBAC decorators, context processor, consolidate _get_org

**검증 대상:**
1. membership_required 데코레이터: active 통과, pending/rejected/없음 리다이렉트
2. role_required 데코레이터: 허용 역할 통과, 미허용 역할 403
3. context_processors.membership: 템플릿에 membership 주입
4. _get_org 헬퍼: active membership 기반 Organization 반환
5. projects/views.py, clients/views.py의 _get_org import 변경 정상 작동
6. 테스트가 모두 통과하는지

<!-- forge:task2:구현담금질:complete:2026-04-12T02:00:00+09:00 -->
