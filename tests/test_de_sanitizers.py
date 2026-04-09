"""Tests for data_extraction.services.extraction.sanitizers.parse_llm_json."""

from data_extraction.services.extraction.sanitizers import parse_llm_json


class TestParseLlmJsonValid:
    """Valid JSON passes through unchanged."""

    def test_valid_json_dict(self):
        raw = '{"name": "홍길동", "careers": []}'
        result = parse_llm_json(raw)
        assert result == {"name": "홍길동", "careers": []}

    def test_valid_json_nested(self):
        raw = '{"name": "김철수", "careers": [{"company": "삼성"}]}'
        result = parse_llm_json(raw)
        assert result == {"name": "김철수", "careers": [{"company": "삼성"}]}


class TestParseLlmJsonFencedBlock:
    """Markdown code-block wrapper removed."""

    def test_fenced_json(self):
        raw = '```json\n{"name": "홍길동"}\n```'
        result = parse_llm_json(raw)
        assert result == {"name": "홍길동"}

    def test_fenced_no_lang(self):
        raw = '```\n{"name": "홍길동"}\n```'
        result = parse_llm_json(raw)
        assert result == {"name": "홍길동"}


class TestParseLlmJsonTrailingComma:
    """Trailing commas are recovered."""

    def test_trailing_comma_object(self):
        raw = '{"name": "\ud64d\uae38\ub3d9",}'
        result = parse_llm_json(raw)
        assert result is not None
        assert result["name"] == "\ud64d\uae38\ub3d9"

    def test_trailing_comma_array(self):
        raw = '{"skills": ["Python", "Java",]}'
        result = parse_llm_json(raw)
        assert result == {"skills": ["Python", "Java"]}


class TestParseLlmJsonListUnwrap:
    """Single-element list [{...}] is unwrapped."""

    def test_single_element_list(self):
        raw = '[{"name": "\ud64d\uae38\ub3d9"}]'
        result = parse_llm_json(raw)
        assert result is not None
        assert result["name"] == "\ud64d\uae38\ub3d9"

    def test_multi_element_list_returns_none(self):
        raw = '[{"name": "\ud64d\uae38\ub3d9"}, {"name": "\uae40\ucca0\uc218"}]'
        result = parse_llm_json(raw)
        assert result is None


class TestParseLlmJsonExtraTrailingText:
    """Extra trailing text after valid JSON is handled via raw_decode."""

    def test_extra_text_after_json(self):
        raw = '{"name": "홍길동"} some extra text here'
        result = parse_llm_json(raw)
        assert result == {"name": "홍길동"}


class TestParseLlmJsonTruncated:
    """Truncated JSON recovery via brace closing."""

    def test_truncated_missing_closing_bracket_and_brace(self):
        # Missing ]} at end — _try_close_truncated should fix it
        raw = '{"name": "\ud64d\uae38\ub3d9", "careers": [{"company": "\uc0bc\uc131"}'
        result = parse_llm_json(raw)
        assert result is not None
        assert result["name"] == "\ud64d\uae38\ub3d9"

    def test_balanced_invalid_json_not_recovered(self):
        """Balanced but invalid content is not over-corrected."""
        raw = "{not valid json at all}"
        result = parse_llm_json(raw)
        assert result is None


class TestParseLlmJsonUnrecoverable:
    """Completely garbled input returns None."""

    def test_garbled_text(self):
        result = parse_llm_json("이것은 JSON이 아닙니다 완전히 깨진 텍스트")
        assert result is None

    def test_empty_string(self):
        result = parse_llm_json("")
        assert result is None

    def test_none_input(self):
        result = parse_llm_json(None)
        assert result is None

    def test_whitespace_only(self):
        result = parse_llm_json("   \n\t  ")
        assert result is None


class TestParseLlmJsonBomAndControlChars:
    """BOM and control characters are cleaned."""

    def test_bom_prefix(self):
        raw = '\ufeff{"name": "홍길동"}'
        result = parse_llm_json(raw)
        assert result == {"name": "홍길동"}

    def test_nan_replaced(self):
        raw = '{"name": "\ud64d\uae38\ub3d9", "score": NaN}'
        result = parse_llm_json(raw)
        assert result is not None
        assert result["name"] == "\ud64d\uae38\ub3d9"
        assert result["score"] is None
