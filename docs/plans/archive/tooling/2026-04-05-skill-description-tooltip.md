# Skill Description Tooltip Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 기술 스택 칩에 약어/비자명 스킬의 설명을 tooltip으로 표시하여 채용 담당자가 스킬의 의미를 즉시 파악할 수 있게 한다.

**Architecture:** skills JSONField의 포맷을 `["string"]` → `[{"name", "description"}]`로 변경. 추출 프롬프트에서 AI가 이력서 맥락을 보고 설명을 생성. 기존 데이터(`["string"]`)는 하위 호환으로 유지.

**Tech Stack:** Django JSONField, Gemini API (기존 추출 파이프라인), Tailwind CSS tooltip

---

### File Map

| File | Action | Responsibility |
|------|--------|---------------|
| `data_extraction/services/extraction/prompts.py` | Modify | skills 스키마 변경 + description 생성 지시 |
| `data_extraction/services/save.py` | Modify | 새 포맷 저장 + 하위 호환 |
| `candidates/services/search.py` | Modify | 새 포맷 검색 호환 |
| `candidates/templates/candidates/partials/candidate_detail_content.html` | Modify | tooltip UI |
| `candidates/templatetags/candidate_extras.py` | Modify | skill 포맷 필터 추가 |
| `tests/test_de_save.py` | Modify | 새 포맷 저장 테스트 |
| `tests/test_search_views.py` | Modify | 검색 호환 테스트 |

---

### Task 1: 추출 프롬프트 스키마 변경

**Files:**
- Modify: `data_extraction/services/extraction/prompts.py:180` (STEP1_SCHEMA)
- Modify: `data_extraction/services/extraction/prompts.py:544` (EXTRACTION_JSON_SCHEMA)
- Modify: `data_extraction/services/extraction/prompts.py:61-67` (skills 구분 규칙)

- [ ] **Step 1: STEP1_SCHEMA의 skills 스키마 변경**

```python
# Before (line 180):
"skills": ["string (기술·도구·시스템·방법론 등 고유명사 키워드, 영문 공식명 우선)"],

# After:
"skills": [{"name": "string (영문 공식명 우선)", "description": "string | null (약어·비자명 스킬이면 한국어 간단 설명, 자명하면 null)"}],
```

- [ ] **Step 2: EXTRACTION_JSON_SCHEMA의 skills 스키마 변경**

```python
# Before (line 544):
"skills": ["string (기술·도구·시스템·방법론 등 고유명사 키워드, 영문 공식명 우선)"],

# After:
"skills": [{"name": "string (영문 공식명 우선)", "description": "string | null (약어·비자명 스킬이면 한국어 간단 설명, 자명하면 null)"}],
```

- [ ] **Step 3: skills 구분 규칙에 description 생성 원칙 추가**

`skills vs core_competencies 구분` 섹션(Step 1 프롬프트 기준 61행 부근, EXTRACTION 프롬프트 기준 444행 부근) 바로 뒤에 추가:

```
### skills description 생성 원칙

description의 목적: 채용 담당자가 스킬 칩을 보고 의미를 즉시 파악하게 하는 것입니다.
담당자는 모든 업계의 약어를 알지 못합니다.

원칙: 스킬 이름만으로 비전문가가 의미를 알 수 있으면 description은 null.
약어이거나 도메인 지식 없이는 의미가 불분명하면 한국어로 짧은 설명을 넣으세요.
이력서의 맥락(직군, 업무 내용)을 참고하여 같은 약어라도 정확한 의미를 판단하세요.

예) {"name": "SCM", "description": "공급망 관리(Supply Chain Management)"} — 약어, 설명 필요
예) {"name": "Python", "description": null} — 자명, 설명 불필요
예) {"name": "MBO", "description": "목표 관리 제도(Management By Objectives)"} — 약어, 맥락상 경영 분야
예) {"name": "ISO 9001", "description": "품질경영시스템 국제표준"} — 약어는 아니지만 비전문가에겐 불명확
```

Golden Rules 적용:
- Rule 1 (하드코딩 금지): "약어이면 description 필수" 같은 이분법 대신 "비전문가가 알 수 있는가"라는 판단 원칙 제공
- Rule 2 (충분한 맥락): description의 용도(채용 담당자 이해)와 WHY 명시
- Rule 3 (최적화 사례): O/X 경계 사례 4개로 판단 기준 구체화

- [ ] **Step 4: 테스트 실행**

Run: `uv run pytest tests/test_de_extraction.py -v`
Expected: 전체 PASS

- [ ] **Step 5: Commit**

```bash
git add data_extraction/services/extraction/prompts.py
git commit -m "feat(prompts): add skill description field to extraction schema"
```

---

### Task 2: 저장 로직 하위 호환

**Files:**
- Modify: `data_extraction/services/save.py:500,601`
- Test: `tests/test_de_save.py`

- [ ] **Step 1: 스킬 포맷 정규화 헬퍼 작성 (test first)**

`tests/test_de_save.py`에 추가:

```python
class TestNormalizeSkills:
    def test_new_format_passthrough(self):
        """New dict format passes through unchanged."""
        skills = [{"name": "SCM", "description": "공급망 관리"}]
        result = _normalize_skills_for_save(skills)
        assert result == [{"name": "SCM", "description": "공급망 관리"}]

    def test_legacy_string_format(self):
        """Legacy string format converted to dict with null description."""
        skills = ["Python", "SAP"]
        result = _normalize_skills_for_save(skills)
        assert result == [
            {"name": "Python", "description": None},
            {"name": "SAP", "description": None},
        ]

    def test_mixed_format(self):
        """Mixed formats handled gracefully."""
        skills = ["Python", {"name": "SCM", "description": "공급망 관리"}]
        result = _normalize_skills_for_save(skills)
        assert result == [
            {"name": "Python", "description": None},
            {"name": "SCM", "description": "공급망 관리"},
        ]

    def test_empty_list(self):
        skills = []
        result = _normalize_skills_for_save(skills)
        assert result == []
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/test_de_save.py::TestNormalizeSkills -v`
Expected: FAIL (함수 미존재)

- [ ] **Step 3: `_normalize_skills_for_save()` 구현**

`data_extraction/services/save.py`에 추가:

```python
def _normalize_skills_for_save(skills: list) -> list[dict]:
    """Normalize skills to [{"name": str, "description": str | None}] format.

    Handles both legacy ["string"] and new [{"name", "description"}] formats.
    """
    result = []
    for item in skills:
        if isinstance(item, str):
            result.append({"name": item, "description": None})
        elif isinstance(item, dict) and "name" in item:
            result.append({
                "name": item["name"],
                "description": item.get("description"),
            })
    return result
```

- [ ] **Step 4: 저장 로직에 정규화 적용**

`save.py`의 두 곳에서 skills 저장 시 정규화 호출:

```python
# Line ~500 (update path):
candidate.skills = _normalize_skills_for_save(extracted.get("skills", []))

# Line ~601 (create path):
skills=_normalize_skills_for_save(extracted.get("skills", [])),
```

- [ ] **Step 5: 테스트 실행 — 통과 확인**

Run: `uv run pytest tests/test_de_save.py -v`
Expected: 전체 PASS

- [ ] **Step 6: Commit**

```bash
git add data_extraction/services/save.py tests/test_de_save.py
git commit -m "feat(save): normalize skills to {name, description} format with backward compat"
```

---

### Task 3: 검색 로직 호환

**Files:**
- Modify: `candidates/services/search.py:370,387`
- Test: `tests/test_search_views.py`

- [ ] **Step 1: 테스트 작성 — 새 포맷 검색**

`tests/test_search_views.py`에 추가:

```python
class TestSkillSearchNewFormat:
    @pytest.fixture
    def candidate_with_new_skills(self, db, user):
        from candidates.models import Candidate
        c = Candidate.objects.create(
            name="신포맷",
            skills=[
                {"name": "SCM", "description": "공급망 관리"},
                {"name": "Python", "description": None},
            ],
        )
        c.categories.add(user.categories.first())
        return c

    def test_skill_keyword_search(self, client, candidate_with_new_skills, user):
        """skill_keywords filter should match name field in new format."""
        # The exact test depends on how search is called -
        # use the search service directly
        from candidates.services.search import apply_filters
        result = apply_filters({"skill_keywords": ["SCM"]}, user)
        assert candidate_with_new_skills in result

    def test_general_keyword_search(self, client, candidate_with_new_skills, user):
        """General keyword icontains should match name in new format."""
        from candidates.services.search import apply_filters
        result = apply_filters({"keyword": "SCM"}, user)
        assert candidate_with_new_skills in result
```

- [ ] **Step 2: 테스트 실행 — 실패 확인**

Run: `uv run pytest tests/test_search_views.py::TestSkillSearchNewFormat -v`
Expected: FAIL (contains 쿼리가 새 포맷에서 동작하지 않을 수 있음)

- [ ] **Step 3: 검색 로직 수정**

`candidates/services/search.py`의 두 쿼리를 수정:

```python
# Line 370 - skill_keywords exact match:
# Before:
qs = qs.filter(skills__contains=[kw])
# After — match both legacy ["string"] and new [{"name": "string"}]:
qs = qs.filter(
    Q(skills__contains=[kw])           # legacy format
    | Q(skills__contains=[{"name": kw}])  # new format (partial dict match)
)

# Line 387 - general keyword search:
# skills__icontains already does text search on JSON, works for both formats
# because "SCM" appears as text in both '["SCM"]' and '[{"name": "SCM", ...}]'
# No change needed here.
```

Note: `skills__contains=[{"name": kw}]`가 PostgreSQL jsonb에서 동작하는지 확인 필요. Django의 `__contains`는 jsonb `@>` 연산자를 사용하며, 부분 dict 매칭을 지원함.

- [ ] **Step 4: 테스트 실행 — 통과 확인**

Run: `uv run pytest tests/test_search_views.py -v`
Expected: 전체 PASS

- [ ] **Step 5: Commit**

```bash
git add candidates/services/search.py tests/test_search_views.py
git commit -m "feat(search): support new skills format in keyword search"
```

---

### Task 4: 템플릿 tooltip UI

**Files:**
- Modify: `candidates/templates/candidates/partials/candidate_detail_content.html:383-391`
- Modify: `candidates/templatetags/candidate_extras.py`

- [ ] **Step 1: 템플릿 필터 작성**

`candidates/templatetags/candidate_extras.py`에 추가:

```python
@register.filter
def skill_name(skill):
    """Extract skill name from either string or dict format."""
    if isinstance(skill, dict):
        return skill.get("name", "")
    return str(skill)


@register.filter
def skill_description(skill):
    """Extract skill description from dict format. Returns empty string if none."""
    if isinstance(skill, dict):
        return skill.get("description") or ""
    return ""
```

- [ ] **Step 2: 템플릿 수정 — tooltip 칩**

`candidate_detail_content.html`의 skills 섹션을 교체:

```html
{% if candidate.skills %}
<div>
  <h3 class="text-[13px] font-medium text-gray-400 mb-2">기술 스택</h3>
  <div class="flex flex-wrap gap-1.5">
    {% for skill in candidate.skills %}
    {% with desc=skill|skill_description name=skill|skill_name %}
    {% if desc %}
    <span class="relative group cursor-help">
      <span class="text-[13px] font-medium text-primary bg-primary-light px-2.5 py-1 rounded-full
                   border border-transparent group-hover:border-primary/30 transition">{{ name }}</span>
      <span class="invisible group-hover:visible opacity-0 group-hover:opacity-100
                   absolute bottom-full left-1/2 -translate-x-1/2 mb-1.5
                   bg-gray-800 text-white text-[12px] rounded-lg px-2.5 py-1.5
                   whitespace-nowrap shadow-lg transition-all duration-150 z-10
                   pointer-events-none">{{ desc }}</span>
    </span>
    {% else %}
    <span class="text-[13px] font-medium text-primary bg-primary-light px-2.5 py-1 rounded-full">{{ name }}</span>
    {% endif %}
    {% endwith %}
    {% endfor %}
  </div>
</div>
{% endif %}
```

- [ ] **Step 3: 테스트 실행**

Run: `uv run pytest -v`
Expected: 전체 PASS

- [ ] **Step 4: Commit**

```bash
git add candidates/templatetags/candidate_extras.py candidates/templates/candidates/partials/candidate_detail_content.html
git commit -m "feat(ui): add tooltip for skill descriptions on hover"
```

---

### Task 5: 전체 통합 테스트

- [ ] **Step 1: 전체 테스트 실행**

Run: `uv run pytest -v`
Expected: 전체 PASS

- [ ] **Step 2: 린트 확인**

Run: `uv run ruff check . && uv run ruff format --check .`
Expected: 이슈 없음
