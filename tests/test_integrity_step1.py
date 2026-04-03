import pytest
from unittest.mock import patch

from candidates.services.integrity.step1_extract import (
    STEP1_SYSTEM_PROMPT,
    build_step1_prompt,
    extract_raw_data,
)


class TestStep1Prompt:
    def test_system_prompt_has_key_principles(self):
        """프롬프트에 핵심 원칙이 포함되어 있는지"""
        assert "정규화 시스템" in STEP1_SYSTEM_PROMPT  # 출력 용도
        assert "source_section" in STEP1_SYSTEM_PROMPT  # 섹션별 독립 추출
        assert "duration_text" in STEP1_SYSTEM_PROMPT  # 부가 정보 보존
        assert "누락" in STEP1_SYSTEM_PROMPT  # 실패 비용

    def test_build_prompt_includes_text(self):
        prompt = build_step1_prompt("이력서 텍스트 내용")
        assert "이력서 텍스트 내용" in prompt

    def test_build_prompt_includes_schema(self):
        prompt = build_step1_prompt("테스트")
        assert "source_section" in prompt
        assert "duration_text" in prompt


class TestStep1Extract:
    @patch("candidates.services.integrity.step1_extract._call_gemini")
    def test_returns_raw_data_on_success(self, mock_call):
        mock_call.return_value = {
            "name": "테스트",
            "careers": [{"company": "A사", "source_section": "경력란"}],
            "educations": [],
        }
        result = extract_raw_data("이력서 텍스트")
        assert result["name"] == "테스트"
        assert len(result["careers"]) == 1

    @patch("candidates.services.integrity.step1_extract._call_gemini")
    def test_returns_none_on_failure(self, mock_call):
        mock_call.return_value = None
        result = extract_raw_data("이력서 텍스트")
        assert result is None

    @patch("candidates.services.integrity.step1_extract._call_gemini")
    def test_retries_with_feedback(self, mock_call):
        """첫 번째 실패 시 피드백과 함께 재시도"""
        mock_call.side_effect = [
            {"name": "테스트", "careers": [{"company": "A사", "source_section": "경력란"}], "educations": []},
        ]
        result = extract_raw_data(
            "이력서 텍스트",
            feedback="일문 섹션이 누락되었습니다.",
        )
        # feedback가 프롬프트에 포함되는지 확인
        call_args = mock_call.call_args
        assert "일문 섹션" in call_args[0][1]  # prompt에 피드백 포함

    def test_build_prompt_includes_feedback_when_provided(self):
        prompt = build_step1_prompt("이력서 텍스트", feedback="경력 섹션 누락")
        assert "이전 추출에 대한 피드백" in prompt
        assert "경력 섹션 누락" in prompt

    def test_build_prompt_no_feedback_section_when_none(self):
        prompt = build_step1_prompt("이력서 텍스트")
        assert "이전 추출에 대한 피드백" not in prompt
