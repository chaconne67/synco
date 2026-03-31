from unittest.mock import patch


from candidates.services.llm_extraction import (
    EXTRACTION_SYSTEM_PROMPT,
    build_extraction_prompt,
    extract_candidate_data,
)


SAMPLE_RESUME = """
이름: 홍길동
생년월일: 1985년 3월 15일
이메일: hong@example.com
연락처: 010-1234-5678

[경력]
2020.03 ~ 현재  삼성전자 반도체사업부 수석연구원
2015.01 ~ 2020.02  LG전자 TV사업부 책임연구원

[학력]
2009.03 ~ 2013.02  서울대학교 전자공학 학사

[자격증]
정보처리기사 (2014.06, 한국산업인력공단)
"""

VALID_LLM_RESPONSE = {
    "name": "홍길동",
    "name_en": "Hong Gildong",
    "birth_year": 1985,
    "gender": "male",
    "email": "hong@example.com",
    "phone": "010-1234-5678",
    "address": None,
    "current_company": "삼성전자",
    "current_position": "수석연구원",
    "total_experience_years": 11,
    "core_competencies": ["반도체", "전자공학"],
    "summary": "삼성전자 반도체사업부 수석연구원으로 재직 중인 11년차 엔지니어",
    "educations": [
        {
            "institution": "서울대학교",
            "degree": "학사",
            "major": "전자공학",
            "gpa": None,
            "start_year": 2009,
            "end_year": 2013,
            "is_abroad": False,
        }
    ],
    "careers": [
        {
            "company": "삼성전자",
            "company_en": "Samsung Electronics",
            "position": "수석연구원",
            "department": "반도체사업부",
            "start_date": "2020-03",
            "end_date": None,
            "is_current": True,
            "duties": "반도체 연구개발",
            "achievements": None,
            "order": 0,
        },
        {
            "company": "LG전자",
            "company_en": "LG Electronics",
            "position": "책임연구원",
            "department": "TV사업부",
            "start_date": "2015-01",
            "end_date": "2020-02",
            "is_current": False,
            "duties": "TV 연구개발",
            "achievements": None,
            "order": 1,
        },
    ],
    "certifications": [
        {
            "name": "정보처리기사",
            "issuer": "한국산업인력공단",
            "acquired_date": "2014-06",
        }
    ],
    "language_skills": [],
    "field_confidences": {
        "name": 1.0,
        "birth_year": 0.95,
        "careers": 0.9,
        "educations": 0.85,
        "certifications": 0.9,
        "overall": 0.9,
    },
}


class TestBuildPrompt:
    def test_includes_resume_text(self):
        """Resume text appears in the built prompt."""
        prompt = build_extraction_prompt(SAMPLE_RESUME)
        assert "홍길동" in prompt
        assert "삼성전자" in prompt
        assert "서울대학교" in prompt

    def test_includes_json_schema(self):
        """JSON schema keywords appear in the built prompt."""
        prompt = build_extraction_prompt(SAMPLE_RESUME)
        assert "birth_year" in prompt
        assert "careers" in prompt
        assert "confidence" in prompt.lower() or "confidences" in prompt.lower()

    def test_system_prompt_exists(self):
        """System prompt is a substantial string."""
        assert len(EXTRACTION_SYSTEM_PROMPT) > 100


class TestExtractCandidateData:
    @patch("candidates.services.llm_extraction.call_llm_json")
    def test_successful_extraction(self, mock_llm):
        """Successful LLM call returns the parsed dict."""
        mock_llm.return_value = VALID_LLM_RESPONSE

        result = extract_candidate_data(SAMPLE_RESUME)

        assert result is not None
        assert result["name"] == "홍길동"
        assert len(result["careers"]) == 2
        assert result["careers"][0]["is_current"] is True
        assert result["field_confidences"]["overall"] == 0.9
        mock_llm.assert_called_once()

    @patch("candidates.services.llm_extraction.call_llm_json")
    def test_retry_on_json_error(self, mock_llm):
        """Retries on exception, succeeds on second call."""
        mock_llm.side_effect = [Exception("JSON parse error"), VALID_LLM_RESPONSE]

        result = extract_candidate_data(SAMPLE_RESUME)

        assert result is not None
        assert result["name"] == "홍길동"
        assert mock_llm.call_count == 2

    @patch("candidates.services.llm_extraction.call_llm_json")
    def test_all_retries_fail(self, mock_llm):
        """Returns None when all retries are exhausted."""
        mock_llm.side_effect = Exception("LLM unavailable")

        result = extract_candidate_data(SAMPLE_RESUME, max_retries=3)

        assert result is None
        assert mock_llm.call_count == 3

    @patch("candidates.services.llm_extraction.call_llm_json")
    def test_invalid_response_no_name(self, mock_llm):
        """Returns None when LLM returns dict without name key."""
        mock_llm.return_value = {"careers": [], "educations": []}

        result = extract_candidate_data(SAMPLE_RESUME)

        assert result is None

    @patch("candidates.services.llm_extraction.call_llm_json")
    def test_returns_none_for_non_dict(self, mock_llm):
        """Returns None when LLM returns a list instead of dict."""
        mock_llm.return_value = [{"name": "홍길동"}]

        result = extract_candidate_data(SAMPLE_RESUME)

        assert result is None


class TestBuildPromptFewshot:
    def test_build_extraction_prompt_with_fewshot(self):
        prompt = build_extraction_prompt("이력서 텍스트", fewshot_section="## 예시\n삼성전자")
        assert "예시" in prompt
        assert "삼성전자" in prompt
        assert "이력서 텍스트" in prompt

    def test_build_extraction_prompt_without_fewshot(self):
        prompt = build_extraction_prompt("이력서 텍스트")
        assert "예시" not in prompt
        assert "이력서 텍스트" in prompt
