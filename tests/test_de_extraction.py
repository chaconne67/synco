"""Tests for data_extraction.services.extraction.* modules.

Combined from:
- tests/test_integrity_pipeline.py
- tests/test_integrity_step1.py
- tests/test_integrity_step2.py
- tests/test_integrity_step3.py
- tests/test_integrity_cross_version.py
- tests/test_integrity_validators.py
"""

import pytest
from unittest.mock import patch

from data_extraction.services.extraction.prompts import (
    EXTRACTION_SYSTEM_PROMPT,
    STEP1_SYSTEM_PROMPT,
    CAREER_SYSTEM_PROMPT,
    EDUCATION_SYSTEM_PROMPT,
    build_extraction_prompt,
    build_step1_prompt,
)
from data_extraction.services.extraction.integrity import (
    extract_raw_data,
    normalize_career_group,
    normalize_education_group,
    normalize_skills,
    check_period_overlaps,
    check_career_education_overlap,
    compare_versions,
    run_integrity_pipeline,
    _normalize_company,
)
from data_extraction.services.extraction.validators import (
    validate_step1,
    validate_step1_5,
    validate_step2,
)


# ===========================================================================
# Prompts tests
# ===========================================================================


class TestExtractionPrompt:
    def test_build_extraction_prompt_contains_text(self):
        result = build_extraction_prompt("이력서 내용입니다")
        assert "이력서 내용입니다" in result

    def test_build_extraction_prompt_contains_schema(self):
        result = build_extraction_prompt("테스트")
        assert "field_confidences" in result

    def test_build_extraction_prompt_with_reference_date(self):
        result = build_extraction_prompt("테스트", file_reference_date="2024-01-15")
        assert "2024-01-15" in result
        assert "파일 메타데이터" in result

    def test_build_extraction_prompt_without_reference_date(self):
        result = build_extraction_prompt("테스트")
        assert "파일 메타데이터" not in result

    def test_extraction_system_prompt_content(self):
        assert "한국어 이력서 파싱 전문가" in EXTRACTION_SYSTEM_PROMPT
        assert "JSON만 출력" in EXTRACTION_SYSTEM_PROMPT


class TestStep1Prompt:
    def test_system_prompt_has_key_principles(self):
        assert "정규화 시스템" in STEP1_SYSTEM_PROMPT
        assert "source_section" in STEP1_SYSTEM_PROMPT
        assert "duration_text" in STEP1_SYSTEM_PROMPT
        assert "누락" in STEP1_SYSTEM_PROMPT

    def test_build_prompt_includes_text(self):
        prompt = build_step1_prompt("이력서 텍스트 내용")
        assert "이력서 텍스트 내용" in prompt

    def test_build_prompt_includes_schema(self):
        prompt = build_step1_prompt("테스트")
        assert "source_section" in prompt
        assert "duration_text" in prompt

    def test_build_prompt_includes_feedback_when_provided(self):
        prompt = build_step1_prompt("이력서 텍스트", feedback="경력 섹션 누락")
        assert "이전 추출에 대한 피드백" in prompt
        assert "경력 섹션 누락" in prompt

    def test_build_prompt_no_feedback_section_when_none(self):
        prompt = build_step1_prompt("이력서 텍스트")
        assert "이전 추출에 대한 피드백" not in prompt


class TestStep2Prompts:
    def test_career_prompt_has_key_principles(self):
        assert "부산물" in CAREER_SYSTEM_PROMPT
        assert "거짓 경보" in CAREER_SYSTEM_PROMPT
        assert "채용 담당자" in CAREER_SYSTEM_PROMPT

    def test_education_prompt_has_key_principles(self):
        assert "솔직하게" in EDUCATION_SYSTEM_PROMPT
        assert "편입" in EDUCATION_SYSTEM_PROMPT


# ===========================================================================
# Step 1 extraction tests
# ===========================================================================


class TestStep1Extract:
    @patch("data_extraction.services.extraction.integrity._call_llm")
    def test_returns_raw_data_on_success(self, mock_call):
        mock_call.return_value = {
            "name": "테스트",
            "careers": [{"company": "A사", "source_section": "경력란"}],
            "educations": [],
        }
        result = extract_raw_data("이력서 텍스트")
        assert result["name"] == "테스트"
        assert len(result["careers"]) == 1

    @patch("data_extraction.services.extraction.integrity._call_llm")
    def test_returns_none_on_failure(self, mock_call):
        mock_call.return_value = None
        result = extract_raw_data("이력서 텍스트")
        assert result is None

    @patch("data_extraction.services.extraction.integrity._call_llm")
    def test_retries_with_feedback(self, mock_call):
        mock_call.side_effect = [
            {
                "name": "테스트",
                "careers": [{"company": "A사", "source_section": "경력란"}],
                "educations": [],
            },
        ]
        extract_raw_data(
            "이력서 텍스트",
            feedback="일문 섹션이 누락되었습니다.",
        )
        call_args = mock_call.call_args
        assert "일문 섹션" in call_args[0][1]


# ===========================================================================
# Step 2 normalization tests
# ===========================================================================


class TestNormalizeCareerGroup:
    @patch("data_extraction.services.extraction.integrity._call_llm")
    def test_multiple_careers_returned(self, mock_call):
        mock_call.return_value = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2022-01",
                    "end_date": None,
                    "is_current": True,
                    "order": 0,
                },
                {
                    "company": "B사",
                    "start_date": "2020-01",
                    "end_date": "2021-12",
                    "is_current": False,
                    "order": 1,
                },
            ],
            "flags": [],
        }
        entries = [
            {
                "company": "A사",
                "start_date": "2022.01",
                "end_date": "현재",
                "source_section": "경력란",
            },
            {
                "company": "B사",
                "start_date": "2020.01",
                "end_date": "2021.12",
                "source_section": "경력란",
            },
        ]
        result = normalize_career_group(entries, "전체 경력")
        assert len(result["careers"]) == 2
        assert result["flags"] == []

    @patch("data_extraction.services.extraction.integrity._call_llm")
    def test_date_conflict_detected(self, mock_call):
        mock_call.return_value = {
            "careers": [
                {
                    "company": "카모스테크",
                    "start_date": "1999-02",
                    "end_date": "2003-07",
                    "is_current": False,
                    "order": 0,
                },
            ],
            "flags": [
                {
                    "type": "DATE_CONFLICT",
                    "severity": "RED",
                    "field": "careers.start_date",
                    "detail": "시작일 7년 차이",
                    "chosen": "1999-02",
                    "alternative": "1992-02",
                    "reasoning": "다수의 섹션이 1999년, 1개 섹션만 1992년",
                }
            ],
        }
        entries = [
            {"company": "카모스테크", "start_date": "1999.2", "source_section": "국문"},
            {
                "company": "カモステック",
                "start_date": "1992.2",
                "source_section": "일문",
            },
        ]
        result = normalize_career_group(entries, "전체 경력")
        assert len(result["flags"]) == 1
        assert result["flags"][0]["type"] == "DATE_CONFLICT"

    @patch("data_extraction.services.extraction.integrity._call_llm")
    def test_single_career_fallback(self, mock_call):
        mock_call.return_value = {
            "career": {
                "company": "A사",
                "start_date": "2020-01",
                "end_date": "2022-06",
                "is_current": False,
            },
            "flags": [],
        }
        entries = [
            {"company": "A사", "start_date": "2020.01", "source_section": "경력란"}
        ]
        result = normalize_career_group(entries, "전체 경력")
        assert "careers" in result
        assert len(result["careers"]) == 1

    @patch("data_extraction.services.extraction.integrity._call_llm")
    def test_gemini_failure_returns_none(self, mock_call):
        mock_call.return_value = None
        result = normalize_career_group([], "전체 경력")
        assert result is None


class TestNormalizeEducationGroup:
    @patch("data_extraction.services.extraction.integrity._call_llm")
    def test_short_degree_detected(self, mock_call):
        mock_call.return_value = {
            "educations": [
                {
                    "institution": "X대",
                    "degree": "학사",
                    "start_year": 2020,
                    "end_year": 2022,
                }
            ],
            "flags": [
                {
                    "type": "SHORT_DEGREE",
                    "severity": "YELLOW",
                    "field": "educations",
                    "detail": "4년제 2년 재학",
                    "chosen": None,
                    "alternative": None,
                    "reasoning": "편입 가능성 확인 필요",
                }
            ],
        }
        entries = [
            {
                "institution": "X대",
                "degree": "학사",
                "start_year": 2020,
                "end_year": 2022,
                "source_section": "학력란",
            }
        ]
        result = normalize_education_group(entries)
        assert len(result["flags"]) == 1
        assert result["flags"][0]["type"] == "SHORT_DEGREE"

    @patch("data_extraction.services.extraction.integrity._call_llm")
    def test_dropout_no_flag(self, mock_call):
        mock_call.return_value = {
            "educations": [
                {
                    "institution": "Y대",
                    "degree": "중퇴",
                    "start_year": 2018,
                    "end_year": 2020,
                    "is_abroad": False,
                }
            ],
            "flags": [],
        }
        entries = [
            {
                "institution": "Y대",
                "degree": "중퇴",
                "start_year": 2018,
                "end_year": 2020,
                "source_section": "학력란",
            }
        ]
        result = normalize_education_group(entries)
        assert result["flags"] == []

    def test_empty_entries_returns_empty(self):
        result = normalize_education_group([])
        assert result == {"educations": [], "flags": []}

    @patch("data_extraction.services.extraction.integrity._call_llm")
    def test_gemini_failure_returns_none(self, mock_call):
        mock_call.return_value = None
        entries = [{"institution": "Z대", "degree": "학사", "source_section": "학력란"}]
        result = normalize_education_group(entries)
        assert result is None


class TestNormalizeSkills:
    def test_passthrough(self):
        raw = {
            "certifications": [{"name": "정보처리기사", "date": "2020-05"}],
            "language_skills": [{"language": "영어", "level": "상"}],
        }
        result = normalize_skills(raw)
        assert result["certifications"] == raw["certifications"]
        assert result["language_skills"] == raw["language_skills"]

    def test_empty_data(self):
        result = normalize_skills({})
        assert result["certifications"] == []
        assert result["language_skills"] == []


class TestCarryForwardEducationStatus:
    """학력 status는 위조 단서이므로 Step 2가 떨어뜨려도 Step 1 raw에서 복원되어야 한다."""

    def test_status_carried_forward_when_step2_drops_it(self):
        from data_extraction.services.extraction.integrity import (
            _carry_forward_education_fields,
        )

        normalized = [
            {"institution": "서울대", "degree": "학사", "end_year": 2014, "status": ""}
        ]
        raw = [
            {
                "institution": "서울대",
                "degree": "학사",
                "end_year": 2014,
                "status": "중퇴",
                "gpa": "3.8/4.5",
            }
        ]
        _carry_forward_education_fields(normalized, raw)
        assert normalized[0]["status"] == "중퇴"
        assert normalized[0]["gpa"] == "3.8/4.5"

    def test_status_not_overwritten_when_step2_provides_it(self):
        from data_extraction.services.extraction.integrity import (
            _carry_forward_education_fields,
        )

        normalized = [
            {
                "institution": "서울대",
                "end_year": 2014,
                "status": "졸업",
            }
        ]
        raw = [
            {
                "institution": "서울대",
                "end_year": 2014,
                "status": "수료",
            }
        ]
        _carry_forward_education_fields(normalized, raw)
        # Step 2 명시값이 우선 — Step 2가 의도적으로 normalize한 결과를 신뢰
        assert normalized[0]["status"] == "졸업"


# ===========================================================================
# Step 3a: Period overlap tests
# ===========================================================================


class TestPeriodOverlaps:
    def test_no_overlap_sequential(self):
        careers = [
            {
                "company": "A사",
                "start_date": "2020-01",
                "end_date": "2022-06",
                "is_current": False,
            },
            {
                "company": "B사",
                "start_date": "2022-07",
                "end_date": "2024-01",
                "is_current": False,
            },
        ]
        assert check_period_overlaps(careers) == []

    def test_short_overlap_normal(self):
        careers = [
            {
                "company": "A사",
                "start_date": "2020-01",
                "end_date": "2022-06",
                "is_current": False,
            },
            {
                "company": "B사",
                "start_date": "2022-05",
                "end_date": "2024-01",
                "is_current": False,
            },
        ]
        assert check_period_overlaps(careers) == []

    def test_long_overlap_flagged(self):
        careers = [
            {
                "company": "A사",
                "start_date": "2020-01",
                "end_date": "2022-06",
                "is_current": False,
            },
            {
                "company": "B사",
                "start_date": "2021-01",
                "end_date": "2024-01",
                "is_current": False,
            },
        ]
        result = check_period_overlaps(careers)
        assert len(result) == 1
        assert result[0]["type"] == "PERIOD_OVERLAP"
        assert "17개월" in result[0]["detail"]

    def test_current_career_uses_today(self):
        careers = [
            {
                "company": "A사",
                "start_date": "2020-01",
                "end_date": None,
                "is_current": True,
            },
            {
                "company": "B사",
                "start_date": "2023-01",
                "end_date": "2024-01",
                "is_current": False,
            },
        ]
        result = check_period_overlaps(careers)
        assert len(result) >= 1

    def test_affiliated_group_excluded(self):
        careers = [
            {
                "company": "삼성카드",
                "start_date": "2002-08",
                "end_date": "2006-05",
                "is_current": False,
            },
            {
                "company": "삼성그룹 T/F",
                "start_date": "2004-03",
                "end_date": "2005-03",
                "is_current": False,
            },
        ]
        affiliated = [
            {
                "canonical_name": "삼성",
                "entry_indices": [0, 1],
                "relationship": "affiliated_group",
            }
        ]
        assert check_period_overlaps(careers, affiliated_groups=affiliated) == []

    def test_repeated_overlaps_red(self):
        careers = [
            {
                "company": "A사",
                "start_date": "1994-02",
                "end_date": "1995-11",
                "is_current": False,
            },
            {
                "company": "B사",
                "start_date": "1995-01",
                "end_date": "1997-10",
                "is_current": False,
            },
            {
                "company": "C사",
                "start_date": "1996-10",
                "end_date": "2000-03",
                "is_current": False,
            },
        ]
        result = check_period_overlaps(careers)
        assert any(f["severity"] == "RED" for f in result)

    def test_no_end_date_not_current_skipped(self):
        careers = [
            {
                "company": "A사",
                "start_date": "2020-01",
                "end_date": None,
                "is_current": False,
            },
            {
                "company": "B사",
                "start_date": "2020-06",
                "end_date": "2022-01",
                "is_current": False,
            },
        ]
        assert check_period_overlaps(careers) == []


class TestCareerEducationOverlap:
    def test_no_overlap(self):
        careers = [
            {
                "company": "A사",
                "start_date": "2020-01",
                "end_date": "2024-01",
                "is_current": False,
            }
        ]
        educations = [{"institution": "서울대", "start_year": 2014, "end_year": 2018}]
        assert check_career_education_overlap(careers, educations) == []

    def test_long_overlap_flagged(self):
        careers = [
            {
                "company": "A사",
                "start_date": "2016-01",
                "end_date": "2020-01",
                "is_current": False,
            }
        ]
        educations = [{"institution": "서울대", "start_year": 2014, "end_year": 2018}]
        result = check_career_education_overlap(careers, educations)
        assert len(result) == 1
        assert result[0]["type"] == "CAREER_EDUCATION_OVERLAP"

    def test_short_overlap_normal(self):
        careers = [
            {
                "company": "A사",
                "start_date": "2017-09",
                "end_date": "2020-01",
                "is_current": False,
            }
        ]
        educations = [{"institution": "서울대", "start_year": 2014, "end_year": 2018}]
        assert check_career_education_overlap(careers, educations) == []


# ===========================================================================
# Step 3b: Cross-version comparison tests
# ===========================================================================


class TestNormalizeCompany:
    def test_strip_korean_suffixes(self):
        assert _normalize_company("주식회사 삼성전자") == "삼성전자"
        assert _normalize_company("삼성전자 주식회사") == "삼성전자"
        assert _normalize_company("㈜삼성전자") == "삼성전자"
        assert _normalize_company("(주)삼성전자") == "삼성전자"

    def test_strip_english_suffixes(self):
        assert _normalize_company("Samsung Co., Ltd.") == "samsung"
        assert _normalize_company("Google Inc.") == "google"
        assert _normalize_company("Apple Corp.") == "apple"

    def test_case_insensitive(self):
        assert _normalize_company("Samsung Electronics") == _normalize_company(
            "samsung electronics"
        )

    def test_whitespace_normalization(self):
        assert _normalize_company("  삼성  전자  ") == "삼성 전자"

    def test_korean_suffix_variants_match(self):
        assert _normalize_company("㈜현대자동차") == _normalize_company(
            "(주)현대자동차"
        )


class TestCrossVersionNoChanges:
    def test_identical_data_no_flags(self):
        data = {
            "careers": [
                {
                    "company": "삼성전자",
                    "start_date": "2020-01",
                    "end_date": "2023-06",
                    "position": "과장",
                },
            ],
            "educations": [
                {
                    "institution": "서울대학교",
                    "degree": "경영학 학사",
                    "start_year": 2014,
                    "end_year": 2018,
                },
            ],
        }
        assert compare_versions(data, data) == []

    def test_empty_data_no_flags(self):
        data = {"careers": [], "educations": []}
        assert compare_versions(data, data) == []


class TestCareerDeleted:
    def test_short_career_deleted_yellow(self):
        previous = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2022-01",
                    "end_date": "2023-06",
                    "position": None,
                },
                {
                    "company": "B사",
                    "start_date": "2020-01",
                    "end_date": "2021-06",
                    "position": None,
                },
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2022-01",
                    "end_date": "2023-06",
                    "position": None,
                },
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 1
        assert flags[0]["type"] == "CAREER_DELETED"
        assert flags[0]["severity"] == "YELLOW"
        assert "B사" in flags[0]["detail"]

    def test_long_career_deleted_red(self):
        previous = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2022-01",
                    "end_date": "2023-06",
                    "position": None,
                },
                {
                    "company": "B사",
                    "start_date": "2018-01",
                    "end_date": "2021-06",
                    "position": None,
                },
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2022-01",
                    "end_date": "2023-06",
                    "position": None,
                },
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 1
        assert flags[0]["type"] == "CAREER_DELETED"
        assert flags[0]["severity"] == "RED"

    def test_deleted_career_fuzzy_match(self):
        previous = {
            "careers": [
                {
                    "company": "㈜삼성전자",
                    "start_date": "2020-01",
                    "end_date": "2023-06",
                    "position": None,
                },
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {
                    "company": "(주)삼성전자",
                    "start_date": "2020-01",
                    "end_date": "2023-06",
                    "position": None,
                },
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 0

    def test_korean_to_english_company_match_via_company_en(self):
        """이전이 한국어, 현재가 영문 + company_en에 한국어가 있으면 같은 회사로."""
        previous = {
            "careers": [
                {
                    "company": "한국법령정보원",
                    "start_date": "2020-03",
                    "end_date": "2021-12",
                },
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {
                    "company": "Korea Law Information Service",
                    "company_en": "Korea Law Information Service",
                    "start_date": "2020-03",
                    "end_date": "2021-12",
                },
            ],
            "educations": [],
        }
        # 한국어 표기와 영문 표기가 회사 키 교집합 0이지만 시작일 매칭으로 같은 회사로 인식
        flags = compare_versions(current, previous)
        assert len(flags) == 0

    def test_company_en_overlap_matches_across_versions(self):
        """양 버전 모두 company_en을 가지고 있고 영문이 같으면 같은 회사로."""
        previous = {
            "careers": [
                {
                    "company": "삼성전자",
                    "company_en": "Samsung Electronics",
                    "start_date": "2018-03",
                    "end_date": "2021-06",
                },
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {
                    "company": "Samsung Electronics",
                    "company_en": None,
                    "start_date": "2018-03",
                    "end_date": "2021-06",
                },
            ],
            "educations": [],
        }
        # 이전의 company_en과 현재의 company가 둘 다 'samsungelectronics' normalize → 매칭
        flags = compare_versions(current, previous)
        assert len(flags) == 0


class TestCareerPeriodChanged:
    def test_minor_date_change_no_flag(self):
        previous = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020-01",
                    "end_date": "2023-06",
                    "position": None,
                },
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020-03",
                    "end_date": "2023-06",
                    "position": None,
                },
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 0

    def test_significant_start_change_yellow(self):
        previous = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020-01",
                    "end_date": "2023-06",
                    "position": None,
                },
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2019-06",
                    "end_date": "2023-06",
                    "position": None,
                },
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 1
        assert flags[0]["type"] == "CAREER_PERIOD_CHANGED"
        assert flags[0]["severity"] == "YELLOW"
        assert "시작일" in flags[0]["detail"]

    def test_significant_end_change_yellow(self):
        previous = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020-01",
                    "end_date": "2023-01",
                    "position": None,
                },
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020-01",
                    "end_date": "2023-12",
                    "position": None,
                },
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 1
        assert flags[0]["type"] == "CAREER_PERIOD_CHANGED"
        assert flags[0]["severity"] == "YELLOW"

    def test_multiple_careers_changed_red(self):
        previous = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020-01",
                    "end_date": "2022-06",
                    "position": None,
                },
                {
                    "company": "B사",
                    "start_date": "2018-01",
                    "end_date": "2019-12",
                    "position": None,
                },
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2019-01",
                    "end_date": "2023-06",
                    "position": None,
                },
                {
                    "company": "B사",
                    "start_date": "2017-01",
                    "end_date": "2020-06",
                    "position": None,
                },
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        period_flags = [f for f in flags if f["type"] == "CAREER_PERIOD_CHANGED"]
        assert len(period_flags) == 2
        assert all(f["severity"] == "RED" for f in period_flags)

    def test_period_changed_with_suffix_variation(self):
        previous = {
            "careers": [
                {
                    "company": "주식회사 카카오",
                    "start_date": "2020-01",
                    "end_date": "2022-06",
                    "position": None,
                },
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {
                    "company": "카카오",
                    "start_date": "2019-01",
                    "end_date": "2022-06",
                    "position": None,
                },
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 1
        assert flags[0]["type"] == "CAREER_PERIOD_CHANGED"


class TestCareerAddedRetroactively:
    def test_new_past_career_yellow(self):
        previous = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020-01",
                    "end_date": "2023-06",
                    "position": None,
                },
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020-01",
                    "end_date": "2023-06",
                    "position": None,
                },
                {
                    "company": "Z사",
                    "start_date": "2017-01",
                    "end_date": "2019-06",
                    "position": None,
                },
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 1
        assert flags[0]["type"] == "CAREER_ADDED_RETROACTIVELY"
        assert flags[0]["severity"] == "YELLOW"
        assert "Z사" in flags[0]["detail"]

    def test_new_recent_career_no_flag(self):
        previous = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020-01",
                    "end_date": "2023-06",
                    "position": None,
                },
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020-01",
                    "end_date": "2023-06",
                    "position": None,
                },
                {
                    "company": "B사",
                    "start_date": "2023-07",
                    "end_date": "2024-06",
                    "position": None,
                },
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 0

    def test_new_career_no_end_date_no_flag(self):
        previous = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020-01",
                    "end_date": "2023-06",
                    "position": None,
                },
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020-01",
                    "end_date": "2023-06",
                    "position": None,
                },
                {
                    "company": "B사",
                    "start_date": "2023-07",
                    "end_date": None,
                    "position": None,
                },
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 0


class TestEducationChanged:
    def test_degree_changed_red(self):
        previous = {
            "careers": [],
            "educations": [
                {
                    "institution": "서울대학교",
                    "degree": "경영학 학사",
                    "start_year": 2014,
                    "end_year": 2018,
                },
            ],
        }
        current = {
            "careers": [],
            "educations": [
                {
                    "institution": "서울대학교",
                    "degree": "경영학 석사",
                    "start_year": 2014,
                    "end_year": 2018,
                },
            ],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 1
        assert flags[0]["type"] == "EDUCATION_CHANGED"
        assert flags[0]["severity"] == "RED"
        assert "학사" in flags[0]["detail"]
        assert "석사" in flags[0]["detail"]

    def test_institution_changed_red(self):
        previous = {
            "careers": [],
            "educations": [
                {
                    "institution": "고려대학교",
                    "degree": "경영학 학사",
                    "start_year": 2014,
                    "end_year": 2018,
                },
            ],
        }
        current = {
            "careers": [],
            "educations": [
                {
                    "institution": "서울대학교",
                    "degree": "경영학 학사",
                    "start_year": 2014,
                    "end_year": 2018,
                },
            ],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 1
        assert flags[0]["type"] == "EDUCATION_CHANGED"
        assert flags[0]["severity"] == "RED"
        assert "고려대학교" in flags[0]["detail"]
        assert "서울대학교" in flags[0]["detail"]

    def test_same_education_no_flag(self):
        data = {
            "careers": [],
            "educations": [
                {
                    "institution": "서울대학교",
                    "degree": "경영학 학사",
                    "start_year": 2014,
                    "end_year": 2018,
                },
            ],
        }
        assert compare_versions(data, data) == []

    def test_education_added_no_flag(self):
        previous = {
            "careers": [],
            "educations": [
                {
                    "institution": "서울대학교",
                    "degree": "경영학 학사",
                    "start_year": 2014,
                    "end_year": 2018,
                },
            ],
        }
        current = {
            "careers": [],
            "educations": [
                {
                    "institution": "서울대학교",
                    "degree": "경영학 학사",
                    "start_year": 2014,
                    "end_year": 2018,
                },
                {
                    "institution": "MIT",
                    "degree": "MBA",
                    "start_year": 2019,
                    "end_year": 2021,
                },
            ],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 0

    def test_degree_none_to_value_no_flag(self):
        previous = {
            "careers": [],
            "educations": [
                {
                    "institution": "서울대학교",
                    "degree": None,
                    "start_year": 2014,
                    "end_year": 2018,
                },
            ],
        }
        current = {
            "careers": [],
            "educations": [
                {
                    "institution": "서울대학교",
                    "degree": "경영학 학사",
                    "start_year": 2014,
                    "end_year": 2018,
                },
            ],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 0

    @pytest.mark.parametrize(
        "prev_degree,cur_degree",
        [
            ("BA, BSC", "학사"),
            ("학사", "BA, BSC"),
            ("MA", "석사"),
            ("MA", "Master"),
            ("MBA", "석사"),
            ("BSc", "Bachelor"),
            ("PhD", "박사"),
            ("Ph.D.", "박사"),
            ("Bachelor of Arts", "학사"),
            ("Master of Engineering", "석사"),
            ("Diploma", "전문학사"),
            ("학부", "Bachelor"),
        ],
    )
    def test_degree_abbreviation_treated_same(self, prev_degree, cur_degree):
        """동일 학위 한국어 표기 ↔ 영문 약어/풀네임은 학위 변경으로 잡지 않는다.

        근본 원인: LLM Step 1이 같은 영문 이력서를 추출할 때 degree 표기가
        20% 비결정성으로 한글/영문 사이를 오간다 (verify 결과 — 상대현 케이스).
        _normalize_degree가 이 변형을 모두 같은 토큰으로 매핑해야 cross-version
        false positive RED를 방지한다.
        """
        previous = {
            "careers": [],
            "educations": [
                {
                    "institution": "단국대학교",
                    "degree": prev_degree,
                    "start_year": 2007,
                    "end_year": 2011,
                },
            ],
        }
        current = {
            "careers": [],
            "educations": [
                {
                    "institution": "단국대학교",
                    "degree": cur_degree,
                    "start_year": 2007,
                    "end_year": 2011,
                },
            ],
        }
        flags = compare_versions(current, previous)
        education_changed = [f for f in flags if f["type"] == "EDUCATION_CHANGED"]
        assert education_changed == [], (
            f"{prev_degree!r} ↔ {cur_degree!r} 는 같은 학위인데 변경으로 분류됨"
        )

    def test_real_degree_change_still_detected(self):
        """약어 매핑 강화 후에도 진짜 학위 변경은 RED로 잡혀야 한다."""
        previous = {
            "careers": [],
            "educations": [
                {
                    "institution": "서울대학교",
                    "degree": "Bachelor",
                    "start_year": 2014,
                    "end_year": 2018,
                },
            ],
        }
        current = {
            "careers": [],
            "educations": [
                {
                    "institution": "서울대학교",
                    "degree": "PhD",
                    "start_year": 2014,
                    "end_year": 2018,
                },
            ],
        }
        flags = compare_versions(current, previous)
        education_changed = [f for f in flags if f["type"] == "EDUCATION_CHANGED"]
        assert len(education_changed) == 1
        assert education_changed[0]["severity"] == "RED"

    @pytest.mark.parametrize(
        "prev_inst,cur_inst",
        [
            ("동국대학교", "Dongguk University"),
            ("Dongguk University", "동국대학교"),
            ("한국외국어대학교", "Hankuk University of Foreign Language"),
            ("Hankuk University of Foreign Studies", "한국외국어대학교"),
            ("한국외국어대학교 (Hankuk University of Foreign Language)", "Hankuk University of Foreign Language"),
            ("한양대학교", "Hanyang University"),
            ("성균관대학교", "Sungkyunkwan University"),
            ("고려대학교", "Korea University"),
            ("서울대학교", "Seoul National University"),
            ("Korea Maritime and Ocean University", "한국해양대학교"),
            ("이화여자대학교", "Ewha Womans University"),
            ("KAIST", "한국과학기술원"),
        ],
    )
    def test_institution_alias_treated_same(self, prev_inst, cur_inst):
        """동일 학교의 한↔영 표기는 cross-version에서 변경으로 잡지 않는다.

        근본 원인: LLM이 같은 영문 이력서에서도 institution을 한글/영문/병기
        형태로 비결정적으로 출력 (강수연 5/5 한글 vs batch 1회 영문). alias
        map으로 한↔영 변형을 같은 canonical로 매핑해야 cross-version FP를
        막는다.
        """
        previous = {
            "careers": [],
            "educations": [
                {
                    "institution": prev_inst,
                    "degree": "학사",
                    "start_year": 2010,
                    "end_year": 2014,
                },
            ],
        }
        current = {
            "careers": [],
            "educations": [
                {
                    "institution": cur_inst,
                    "degree": "학사",
                    "start_year": 2010,
                    "end_year": 2014,
                },
            ],
        }
        flags = compare_versions(current, previous)
        edu_changed = [f for f in flags if f["type"] == "EDUCATION_CHANGED"]
        assert edu_changed == [], (
            f"{prev_inst!r} ↔ {cur_inst!r} 는 같은 학교인데 변경으로 분류됨"
        )

    def test_real_institution_change_still_detected(self):
        """alias map 도입 후에도 다른 학교는 RED로 잡혀야 한다."""
        previous = {
            "careers": [],
            "educations": [
                {
                    "institution": "서울대학교",
                    "degree": "학사",
                    "start_year": 2014,
                    "end_year": 2018,
                },
            ],
        }
        current = {
            "careers": [],
            "educations": [
                {
                    "institution": "Korea University",  # 고려대 — 다른 학교
                    "degree": "학사",
                    "start_year": 2014,
                    "end_year": 2018,
                },
            ],
        }
        flags = compare_versions(current, previous)
        edu_changed = [f for f in flags if f["type"] == "EDUCATION_CHANGED"]
        assert len(edu_changed) == 1


class TestCareerReclassifiedToEtc:
    """Career → career_etc 재분류 시 cross-version에서 '삭제됨' RED 방지."""

    def test_career_reclassified_to_etc_not_deleted(self):
        """이전 careers 항목이 새 추출에서 career_etc로 옮겨지면 삭제 아님.

        근본 원인: P3 prompt 강화로 인턴/짧은경력이 career_etc로 분류되는
        케이스가 늘었는데 (고지연), cross-version은 careers끼리만 비교해서
        '경력 삭제됨' RED 폭발. career_etc까지 검색해야 정보 보존 인식.
        """
        previous = {
            "careers": [
                {
                    "company": "KOTRA",
                    "start_date": "2006-01",
                    "end_date": "2006-03",
                    "position": "Intern",
                },
                {
                    "company": "롯데쇼핑",
                    "start_date": "2006-07",
                    "end_date": "2008-03",
                    "position": "주임",
                },
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {
                    "company": "롯데쇼핑",
                    "start_date": "2006-07",
                    "end_date": "2008-03",
                    "position": "주임",
                },
            ],
            "career_etc": [
                {
                    "type": "인턴/기타경력",
                    "company": "KOTRA",
                    "role": "전시컨벤션 인턴",
                    "start_date": "2006-01",
                    "end_date": "2006-03",
                },
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        deleted = [f for f in flags if f["type"] == "CAREER_DELETED"]
        assert deleted == [], (
            "이전 careers가 새 career_etc에 보존됐는데 '삭제됨'으로 분류됨"
        )

    def test_career_truly_deleted_still_detected(self):
        """완전히 사라진 경력은 여전히 CAREER_DELETED로 잡혀야 한다."""
        previous = {
            "careers": [
                {
                    "company": "삼성전자",
                    "start_date": "2018-01",
                    "end_date": "2022-12",
                    "position": "사원",
                },
            ],
            "educations": [],
        }
        current = {
            "careers": [],
            "career_etc": [],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        deleted = [f for f in flags if f["type"] == "CAREER_DELETED"]
        assert len(deleted) == 1


class TestCrossVersionComprehensive:
    def test_multiple_flag_types_combined(self):
        previous = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020-01",
                    "end_date": "2023-06",
                    "position": "과장",
                },
                {
                    "company": "B사",
                    "start_date": "2017-01",
                    "end_date": "2019-12",
                    "position": "대리",
                },
            ],
            "educations": [
                {
                    "institution": "서울대학교",
                    "degree": "경영학 학사",
                    "start_year": 2012,
                    "end_year": 2016,
                },
            ],
        }
        current = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2019-07",
                    "end_date": "2023-06",
                    "position": "과장",
                },
                {
                    "company": "C사",
                    "start_date": "2015-01",
                    "end_date": "2016-12",
                    "position": "사원",
                },
            ],
            "educations": [
                {
                    "institution": "서울대학교",
                    "degree": "경영학 석사",
                    "start_year": 2012,
                    "end_year": 2016,
                },
            ],
        }
        flags = compare_versions(current, previous)
        types = {f["type"] for f in flags}
        assert "CAREER_DELETED" in types
        assert "CAREER_PERIOD_CHANGED" in types
        assert "CAREER_ADDED_RETROACTIVELY" in types
        assert "EDUCATION_CHANGED" in types

    def test_flag_format_complete(self):
        previous = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020-01",
                    "end_date": "2023-06",
                    "position": None,
                },
                {
                    "company": "B사",
                    "start_date": "2017-01",
                    "end_date": "2019-12",
                    "position": None,
                },
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020-01",
                    "end_date": "2023-06",
                    "position": None,
                },
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        required_keys = {
            "type",
            "severity",
            "field",
            "detail",
            "chosen",
            "alternative",
            "reasoning",
        }
        for flag in flags:
            assert set(flag.keys()) == required_keys

    def test_exactly_3_month_diff_not_flagged(self):
        previous = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020-01",
                    "end_date": "2023-06",
                    "position": None,
                },
            ],
            "educations": [],
        }
        current = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020-04",
                    "end_date": "2023-06",
                    "position": None,
                },
            ],
            "educations": [],
        }
        flags = compare_versions(current, previous)
        assert len(flags) == 0

    def test_exactly_24_month_career_deleted_yellow(self):
        previous = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020-01",
                    "end_date": "2022-01",
                    "position": None,
                },
            ],
            "educations": [],
        }
        current = {"careers": [], "educations": []}
        flags = compare_versions(current, previous)
        assert len(flags) == 1
        assert flags[0]["severity"] == "YELLOW"

    def test_25_month_career_deleted_red(self):
        previous = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020-01",
                    "end_date": "2022-02",
                    "position": None,
                },
            ],
            "educations": [],
        }
        current = {"careers": [], "educations": []}
        flags = compare_versions(current, previous)
        assert len(flags) == 1
        assert flags[0]["severity"] == "RED"


# ===========================================================================
# Validators tests
# ===========================================================================


class TestValidateStep1:
    def test_pass_complete_data(self):
        raw_data = {
            "careers": [
                {"source_section": "경력사항", "duration_text": "2년 3개월"},
                {"source_section": "해외경력", "duration_text": None},
            ],
        }
        resume_text = "삼성전자 경력사항에서 근무 후 해외경력 섹션에 기재."
        issues = validate_step1(raw_data, resume_text)
        assert issues == []

    def test_single_source_section_warning(self):
        raw_data = {
            "careers": [
                {"source_section": "경력사항"},
                {"source_section": "경력사항"},
                {"source_section": "경력사항"},
            ],
        }
        resume_text = "일반적인 이력서 텍스트입니다."
        issues = validate_step1(raw_data, resume_text)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert "same source_section" in issues[0]["message"]

    def test_single_career_no_diversity_warning(self):
        raw_data = {
            "careers": [
                {"source_section": "경력사항"},
            ],
        }
        resume_text = "단일 경력 이력서."
        issues = validate_step1(raw_data, resume_text)
        assert issues == []

    def test_japanese_present_no_section(self):
        raw_data = {
            "careers": [
                {"source_section": "경력사항"},
                {"source_section": "자격증"},
            ],
        }
        resume_text = "東京本社にて勤務。カタカナテスト。경력사항 기재."
        issues = validate_step1(raw_data, resume_text)
        jp_issues = [i for i in issues if "Japanese" in i["message"]]
        assert len(jp_issues) == 1
        assert jp_issues[0]["severity"] == "warning"

    def test_japanese_present_with_section(self):
        raw_data = {
            "careers": [
                {"source_section": "경력사항"},
                {"source_section": "にほんご経歴"},
            ],
        }
        resume_text = "東京本社にて勤務。경력사항도 있음."
        issues = validate_step1(raw_data, resume_text)
        jp_issues = [i for i in issues if "Japanese" in i["message"]]
        assert jp_issues == []

    def test_japanese_katakana_only(self):
        raw_data = {
            "careers": [
                {"source_section": "경력사항"},
            ],
        }
        resume_text = "ソフトウェアエンジニア として勤務"
        issues = validate_step1(raw_data, resume_text)
        jp_issues = [i for i in issues if "Japanese" in i["message"]]
        assert len(jp_issues) == 1

    def test_english_present_no_section(self):
        raw_data = {
            "careers": [
                {"source_section": "경력사항"},
            ],
        }
        resume_text = "SoftwareEngineeringDepartment 에서 근무했습니다."
        issues = validate_step1(raw_data, resume_text)
        en_issues = [i for i in issues if "English" in i["message"]]
        assert len(en_issues) == 1
        assert en_issues[0]["severity"] == "warning"

    def test_english_short_no_warning(self):
        raw_data = {
            "careers": [
                {"source_section": "경력사항"},
            ],
        }
        resume_text = "Samsung에서 Manager로 근무."
        issues = validate_step1(raw_data, resume_text)
        en_issues = [i for i in issues if "English" in i["message"]]
        assert en_issues == []

    def test_english_present_with_section(self):
        raw_data = {
            "careers": [
                {"source_section": "EnglishResumeSection with details"},
            ],
        }
        resume_text = "WorkedAtSoftwareEngineeringDepartment for 5 years."
        issues = validate_step1(raw_data, resume_text)
        en_issues = [i for i in issues if "English" in i["message"]]
        assert en_issues == []

    def test_duration_text_missing_with_parenthetical(self):
        raw_data = {
            "careers": [
                {"source_section": "경력사항", "duration_text": None},
                {"source_section": "기타경력", "duration_text": ""},
            ],
        }
        resume_text = "삼성전자 (11개월) 근무 후 LG전자 (2Y 6M) 근무."
        issues = validate_step1(raw_data, resume_text)
        dur_issues = [i for i in issues if "duration_text" in i["message"]]
        assert len(dur_issues) == 1
        assert dur_issues[0]["severity"] == "warning"

    def test_duration_text_present(self):
        raw_data = {
            "careers": [
                {"source_section": "경력사항", "duration_text": "11개월"},
                {"source_section": "기타경력", "duration_text": None},
            ],
        }
        resume_text = "삼성전자 (11개월) 근무."
        issues = validate_step1(raw_data, resume_text)
        dur_issues = [i for i in issues if "duration_text" in i["message"]]
        assert dur_issues == []

    def test_duration_pattern_2y_6m(self):
        raw_data = {
            "careers": [
                {"source_section": "경력사항"},
            ],
        }
        resume_text = "해외법인 근무 (2Y 6M) 발령."
        issues = validate_step1(raw_data, resume_text)
        dur_issues = [i for i in issues if "duration_text" in i["message"]]
        assert len(dur_issues) == 1

    def test_empty_careers(self):
        raw_data = {"careers": []}
        resume_text = "빈 이력서."
        issues = validate_step1(raw_data, resume_text)
        assert issues == []

    def test_no_source_section_field(self):
        raw_data = {
            "careers": [
                {"company": "A사"},
                {"company": "B사"},
            ],
        }
        resume_text = "일반 이력서."
        issues = validate_step1(raw_data, resume_text)
        assert issues == []


class TestValidateStep1_5:
    def test_pass_well_grouped(self):
        grouping = {
            "groups": [
                {"canonical_name": "삼성", "entry_indices": [0, 1, 2]},
                {"canonical_name": "LG", "entry_indices": [3, 4]},
            ],
        }
        issues = validate_step1_5(grouping, total_careers=5, total_educations=2)
        assert issues == []

    def test_high_ungrouped_ratio(self):
        grouping = {
            "groups": [
                {"canonical_name": "삼성", "entry_indices": [0]},
            ],
        }
        issues = validate_step1_5(grouping, total_careers=5, total_educations=1)
        assert len(issues) == 1
        assert issues[0]["severity"] == "warning"
        assert "4/5" in issues[0]["message"]
        assert "80%" in issues[0]["message"]

    def test_exactly_50_percent_no_warning(self):
        grouping = {
            "groups": [
                {"canonical_name": "A", "entry_indices": [0, 1]},
            ],
        }
        issues = validate_step1_5(grouping, total_careers=4, total_educations=0)
        assert issues == []

    def test_all_ungrouped(self):
        grouping = {"groups": []}
        issues = validate_step1_5(grouping, total_careers=3, total_educations=0)
        assert len(issues) == 1
        assert "3/3" in issues[0]["message"]

    def test_zero_careers(self):
        grouping = {"groups": []}
        issues = validate_step1_5(grouping, total_careers=0, total_educations=0)
        assert issues == []

    def test_all_grouped(self):
        grouping = {
            "groups": [
                {"canonical_name": "A", "entry_indices": [0, 1, 2]},
            ],
        }
        issues = validate_step1_5(grouping, total_careers=3, total_educations=1)
        assert issues == []

    def test_overlapping_group_indices(self):
        grouping = {
            "groups": [
                {"canonical_name": "A", "entry_indices": [0, 1]},
                {"canonical_name": "B", "entry_indices": [1, 2]},
            ],
        }
        issues = validate_step1_5(grouping, total_careers=6, total_educations=0)
        assert issues == []


class TestValidateStep2:
    def test_pass_complete_data(self):
        normalized = {
            "careers": [
                {"company": "삼성전자", "start_date": "2020-01", "end_date": "2022-06"},
                {"company": "LG전자", "start_date": "2022-07", "end_date": None},
            ],
            "flags": [
                {"severity": "YELLOW", "reasoning": "Short overlap during transition"},
            ],
        }
        issues = validate_step2(normalized)
        assert issues == []

    def test_missing_company(self):
        normalized = {
            "careers": [{"company": "", "start_date": "2020-01"}],
            "flags": [],
        }
        issues = validate_step2(normalized)
        errors = [i for i in issues if i["severity"] == "error"]
        assert len(errors) == 1
        assert "company" in errors[0]["message"]

    def test_missing_start_date(self):
        normalized = {
            "careers": [{"company": "삼성전자", "start_date": None}],
            "flags": [],
        }
        issues = validate_step2(normalized)
        errors = [i for i in issues if i["severity"] == "error"]
        assert len(errors) == 1
        assert "start_date" in errors[0]["message"]

    def test_missing_both_required(self):
        normalized = {
            "careers": [{"company": None, "start_date": ""}],
            "flags": [],
        }
        issues = validate_step2(normalized)
        errors = [i for i in issues if i["severity"] == "error"]
        assert len(errors) == 2

    def test_invalid_start_date_format(self):
        normalized = {
            "careers": [{"company": "A사", "start_date": "2020/01"}],
            "flags": [],
        }
        issues = validate_step2(normalized)
        errors = [i for i in issues if i["severity"] == "error"]
        assert any(
            "start_date" in e["message"] and "YYYY-MM" in e["message"] for e in errors
        )

    def test_invalid_end_date_format(self):
        normalized = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "June 2022"}
            ],
            "flags": [],
        }
        issues = validate_step2(normalized)
        errors = [i for i in issues if i["severity"] == "error"]
        assert any("end_date" in e["message"] for e in errors)

    def test_invalid_date_month_13(self):
        normalized = {
            "careers": [{"company": "A사", "start_date": "2020-13"}],
            "flags": [],
        }
        issues = validate_step2(normalized)
        errors = [i for i in issues if i["severity"] == "error"]
        assert any("YYYY-MM" in e["message"] for e in errors)

    def test_flag_without_reasoning(self):
        normalized = {
            "careers": [{"company": "A사", "start_date": "2020-01"}],
            "flags": [{"severity": "RED", "type": "PERIOD_OVERLAP"}],
        }
        issues = validate_step2(normalized)
        warnings = [i for i in issues if i["severity"] == "warning"]
        assert len(warnings) == 1
        assert "reasoning" in warnings[0]["message"]

    def test_flag_with_reasoning_ok(self):
        normalized = {
            "careers": [{"company": "A사", "start_date": "2020-01"}],
            "flags": [{"severity": "RED", "reasoning": "Repeated overlap pattern"}],
        }
        issues = validate_step2(normalized)
        warnings = [i for i in issues if i["severity"] == "warning"]
        assert warnings == []

    def test_flag_no_severity_no_warning(self):
        normalized = {
            "careers": [{"company": "A사", "start_date": "2020-01"}],
            "flags": [{"type": "INFO", "detail": "some info"}],
        }
        issues = validate_step2(normalized)
        assert issues == []

    def test_empty_careers(self):
        normalized = {"careers": [], "flags": []}
        issues = validate_step2(normalized)
        assert issues == []

    def test_multiple_careers_mixed_issues(self):
        normalized = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2022-06"},
                {"company": "", "start_date": "bad-date"},
                {"company": "C사", "start_date": "2023-01", "end_date": "not-a-date"},
            ],
            "flags": [{"severity": "YELLOW"}],
        }
        issues = validate_step2(normalized)
        errors = [i for i in issues if i["severity"] == "error"]
        warnings = [i for i in issues if i["severity"] == "warning"]
        assert len(errors) == 3
        assert len(warnings) == 1

    def test_no_integrity_flags_key(self):
        normalized = {
            "careers": [{"company": "A사", "start_date": "2020-01"}],
        }
        issues = validate_step2(normalized)
        assert issues == []


# ===========================================================================
# Pipeline integration tests
# ===========================================================================


MOCK_RAW_DATA_IS_CURRENT = {
    "name": "테스트",
    "name_en": None,
    "birth_year": 1990,
    "gender": None,
    "email": "test@test.com",
    "phone": "010-1234-5678",
    "address": None,
    "total_experience_years": 5,
    "resume_reference_date": None,
    "careers": [
        {
            "company": "X사",
            "start_date": "2020.01",
            "end_date": "2023.06",
            "is_current": True,
            "source_section": "경력란",
            "duration_text": None,
            "duties": None,
        },
    ],
    "educations": [],
    "certifications": [],
    "language_skills": [],
}

MOCK_RAW_DATA = {
    "name": "테스트",
    "name_en": None,
    "birth_year": 1990,
    "gender": None,
    "email": "test@test.com",
    "phone": "010-1234-5678",
    "address": None,
    "total_experience_years": 5,
    "resume_reference_date": None,
    "careers": [
        {
            "company": "A사",
            "start_date": "2020.01",
            "end_date": "2022.06",
            "is_current": False,
            "source_section": "경력란",
            "duration_text": None,
            "duties": None,
        },
    ],
    "educations": [
        {
            "institution": "서울대",
            "degree": "학사",
            "major": "컴퓨터",
            "start_year": 2010,
            "end_year": 2014,
            "is_abroad": False,
            "status": "졸업",
            "source_section": "학력란",
        },
    ],
    "certifications": [],
    "language_skills": [],
}

MOCK_CAREER_RESULT = {
    "careers": [
        {
            "company": "A사",
            "start_date": "2020-01",
            "end_date": "2022-06",
            "is_current": False,
            "order": 0,
        },
    ],
    "flags": [],
}

MOCK_EDU_RESULT = {
    "educations": [
        {
            "institution": "서울대",
            "degree": "학사",
            "major": "컴퓨터",
            "start_year": 2010,
            "end_year": 2014,
            "is_abroad": False,
        },
    ],
    "flags": [],
}


class TestPipelineSuccess:
    @patch("data_extraction.services.extraction.integrity.normalize_education_group")
    @patch("data_extraction.services.extraction.integrity.normalize_career_group")
    @patch("data_extraction.services.extraction.integrity.extract_raw_data")
    @patch("data_extraction.services.extraction.integrity.validate_step1")
    def test_full_pipeline(self, mock_v1, mock_s1, mock_s2c, mock_s2e):
        mock_v1.return_value = []
        mock_s1.return_value = MOCK_RAW_DATA
        mock_s2c.return_value = MOCK_CAREER_RESULT
        mock_s2e.return_value = MOCK_EDU_RESULT

        result = run_integrity_pipeline("이력서 텍스트")

        assert result is not None
        assert result["name"] == "테스트"
        assert len(result["careers"]) == 1
        assert result["careers"][0]["order"] == 0
        assert len(result["educations"]) == 1
        assert result["integrity_flags"] == []

    @patch("data_extraction.services.extraction.integrity.normalize_education_group")
    @patch("data_extraction.services.extraction.integrity.normalize_career_group")
    @patch("data_extraction.services.extraction.integrity.extract_raw_data")
    @patch("data_extraction.services.extraction.integrity.validate_step1")
    def test_flags_collected(self, mock_v1, mock_s1, mock_s2c, mock_s2e):
        mock_v1.return_value = []
        mock_s1.return_value = MOCK_RAW_DATA
        mock_s2c.return_value = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020-01",
                    "end_date": "2022-06",
                    "is_current": False,
                    "order": 0,
                }
            ],
            "flags": [
                {
                    "type": "DATE_CONFLICT",
                    "severity": "RED",
                    "field": "start_date",
                    "detail": "test",
                    "chosen": "a",
                    "alternative": "b",
                    "reasoning": "test",
                }
            ],
        }
        mock_s2e.return_value = MOCK_EDU_RESULT

        result = run_integrity_pipeline("이력서 텍스트")
        assert len(result["integrity_flags"]) == 1
        assert result["integrity_flags"][0]["type"] == "DATE_CONFLICT"


class TestPipelineFailure:
    @patch("data_extraction.services.extraction.integrity.extract_raw_data")
    def test_step1_failure(self, mock_s1):
        mock_s1.return_value = None
        assert run_integrity_pipeline("텍스트") is None


class TestPipelineRetry:
    @patch("data_extraction.services.extraction.integrity.normalize_education_group")
    @patch("data_extraction.services.extraction.integrity.normalize_career_group")
    @patch("data_extraction.services.extraction.integrity.extract_raw_data")
    @patch("data_extraction.services.extraction.integrity.validate_step1")
    def test_step1_retry_on_warning(self, mock_v1, mock_s1, mock_s2c, mock_s2e):
        mock_v1.return_value = [{"severity": "warning", "message": "일문 섹션 누락"}]
        mock_s1.side_effect = [MOCK_RAW_DATA, MOCK_RAW_DATA]
        mock_s2c.return_value = MOCK_CAREER_RESULT
        mock_s2e.return_value = MOCK_EDU_RESULT

        result = run_integrity_pipeline("텍스트")
        assert result is not None
        assert result["pipeline_meta"]["retries"] == 1
        assert mock_s1.call_count == 2


class TestPipelineCrossVersion:
    @patch("data_extraction.services.extraction.integrity.normalize_education_group")
    @patch("data_extraction.services.extraction.integrity.normalize_career_group")
    @patch("data_extraction.services.extraction.integrity.extract_raw_data")
    @patch("data_extraction.services.extraction.integrity.validate_step1")
    def test_cross_version_flags_included(self, mock_v1, mock_s1, mock_s2c, mock_s2e):
        mock_v1.return_value = []
        mock_s1.return_value = MOCK_RAW_DATA
        mock_s2c.return_value = MOCK_CAREER_RESULT
        mock_s2e.return_value = MOCK_EDU_RESULT

        previous = {
            "careers": [
                {"company": "A사", "start_date": "2020-01", "end_date": "2022-06"},
                {"company": "B사", "start_date": "2018-01", "end_date": "2019-12"},
            ],
            "educations": [],
        }
        result = run_integrity_pipeline("텍스트", previous_data=previous)
        assert result is not None
        cv_flags = [
            f for f in result["integrity_flags"] if f["type"] == "CAREER_DELETED"
        ]
        assert len(cv_flags) >= 1


class TestAutoCorrectIsCurrentEndDate:
    """is_current=True with end_date should be auto-corrected to is_current=False."""

    @patch("data_extraction.services.extraction.integrity.normalize_education_group")
    @patch("data_extraction.services.extraction.integrity.normalize_career_group")
    @patch("data_extraction.services.extraction.integrity.extract_raw_data")
    @patch("data_extraction.services.extraction.integrity.validate_step1")
    def test_is_current_corrected_when_end_date_present(
        self, mock_v1, mock_s1, mock_s2c, mock_s2e
    ):
        mock_v1.return_value = []
        mock_s1.return_value = MOCK_RAW_DATA_IS_CURRENT
        mock_s2c.return_value = {
            "careers": [
                {
                    "company": "X사",
                    "start_date": "2020-01",
                    "end_date": "2023-06",
                    "is_current": True,
                    "order": 0,
                },
            ],
            "flags": [
                {
                    "type": "DATE_CONFLICT",
                    "severity": "YELLOW",
                    "field": "is_current",
                    "detail": "X사: is_current가 true이지만 end_date가 존재",
                    "chosen": "true",
                    "alternative": "false",
                    "reasoning": "모순",
                },
            ],
        }
        mock_s2e.return_value = MOCK_EDU_RESULT

        result = run_integrity_pipeline("텍스트")
        assert result is not None

        # Career should be auto-corrected
        career = result["careers"][0]
        assert career["is_current"] is False

        # The contradiction flag should be removed
        is_current_flags = [
            f
            for f in result["integrity_flags"]
            if "is_current" in (f.get("field") or "")
            or "is_current" in (f.get("detail") or "")
        ]
        assert len(is_current_flags) == 0

    @patch("data_extraction.services.extraction.integrity.normalize_education_group")
    @patch("data_extraction.services.extraction.integrity.normalize_career_group")
    @patch("data_extraction.services.extraction.integrity.extract_raw_data")
    @patch("data_extraction.services.extraction.integrity.validate_step1")
    def test_no_correction_when_no_end_date(self, mock_v1, mock_s1, mock_s2c, mock_s2e):
        mock_v1.return_value = []
        mock_s1.return_value = MOCK_RAW_DATA
        mock_s2c.return_value = {
            "careers": [
                {
                    "company": "A사",
                    "start_date": "2020-01",
                    "end_date": None,
                    "is_current": True,
                    "order": 0,
                },
            ],
            "flags": [],
        }
        mock_s2e.return_value = MOCK_EDU_RESULT

        result = run_integrity_pipeline("텍스트")
        assert result is not None

        # No end_date → is_current should stay True
        career = result["careers"][0]
        assert career["is_current"] is True

    @patch("data_extraction.services.extraction.integrity.normalize_education_group")
    @patch("data_extraction.services.extraction.integrity.normalize_career_group")
    @patch("data_extraction.services.extraction.integrity.extract_raw_data")
    @patch("data_extraction.services.extraction.integrity.validate_step1")
    def test_unrelated_flags_preserved(self, mock_v1, mock_s1, mock_s2c, mock_s2e):
        mock_v1.return_value = []
        mock_s1.return_value = MOCK_RAW_DATA_IS_CURRENT
        mock_s2c.return_value = {
            "careers": [
                {
                    "company": "X사",
                    "start_date": "2020-01",
                    "end_date": "2023-06",
                    "is_current": True,
                    "order": 0,
                },
            ],
            "flags": [
                {
                    "type": "DATE_CONFLICT",
                    "severity": "YELLOW",
                    "field": "is_current",
                    "detail": "X사: is_current가 true이지만 end_date가 존재",
                    "chosen": "true",
                    "alternative": "false",
                    "reasoning": "모순",
                },
                {
                    "type": "DATE_CONFLICT",
                    "severity": "YELLOW",
                    "field": "start_date",
                    "detail": "X사의 시작일이 불명확함",
                    "chosen": "2020-01",
                    "alternative": "2019-12",
                    "reasoning": "추정",
                },
            ],
        }
        mock_s2e.return_value = MOCK_EDU_RESULT

        result = run_integrity_pipeline("텍스트")
        assert result is not None

        # is_current flag removed, but start_date flag preserved
        remaining_flags = result["integrity_flags"]
        is_current_flags = [
            f for f in remaining_flags if "is_current" in (f.get("field") or "")
        ]
        start_date_flags = [
            f for f in remaining_flags if "start_date" in (f.get("field") or "")
        ]
        assert len(is_current_flags) == 0
        assert len(start_date_flags) == 1
