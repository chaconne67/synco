# impl-plan Rulings — t12

**Status:** COMPLETE
**Rounds:** 1
**Red-team:** Codex CLI, Gemini API

---

## Accepted Items

### R1-01: expires_at DateTimeField + DateInput type mismatch [MAJOR] — ACCEPTED
- Change `forms.DateTimeField` to `forms.DateField`
- Add `clean_expires_at()` that converts selected date to end-of-day aware datetime
- Gemini's CRITICAL claim (form always fails) disproven by execution test

### R1-02: expires_at missing future-date validation [MAJOR] — ACCEPTED
- Add past-date rejection in `clean_expires_at()`
- Combined with R1-01 fix

### R1-03: NotificationPreference hardcoded defaults [MAJOR] — PARTIAL ACCEPTED
- Remove fallback defaults from `to_preferences()` `.get()` calls
- Keep explicit field declarations (not dynamically generated)

### R1-04: InviteCodeCreateForm role choices hardcoded [MAJOR] — ACCEPTED
- Derive from `InviteCode.Role` excluding `OWNER`

### R1-05: Widget CSS inconsistent [MINOR] — ACCEPTED
- Define `INPUT_CSS` constant using project pattern (`focus:ring-primary`, `text-[15px]`)

## Rebutted Items

### R1-06: No test step in plan [MINOR] — REBUTTED
- Form-only task; testing deferred to view integration in t13/t15
- Consistent with prior task patterns (t03-t11)
