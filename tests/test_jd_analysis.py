"""P03a: JD analysis service tests.

Tests for JD requirements extraction, search filter mapping,
text extraction from files, and Gemini API error handling.
"""

import pytest
from unittest.mock import MagicMock, patch


class TestRequirementsToSearchFilters:
    def test_basic_mapping(self):
        """requirements -> search filters 기본 매핑."""
        from projects.services.jd_analysis import requirements_to_search_filters

        reqs = {
            "position": "품질기획팀장",
            "min_experience_years": 12,
            "max_experience_years": 16,
            "birth_year_from": 1982,
            "birth_year_to": 1986,
            "gender": "male",
            "education_fields": ["전자공학", "재료공학"],
            "required_certifications": ["품질경영기사"],
            "preferred_certifications": ["6Sigma BB"],
            "keywords": ["QMS", "ISO"],
        }
        filters = requirements_to_search_filters(reqs)

        assert filters["position_keywords"] == ["품질기획팀장"]
        assert filters["min_experience_years"] == 12
        assert filters["max_experience_years"] == 16
        assert filters["major_keywords"] == ["전자공학", "재료공학"]
        assert "품질경영기사" in filters["certification_keywords"]
        assert "6Sigma BB" in filters["certification_keywords"]
        assert filters["skill_keywords"] == ["QMS", "ISO"]
        assert filters["gender"] == "male"
        assert filters["birth_year_from"] == 1982
        assert filters["birth_year_to"] == 1986

    def test_empty_requirements(self):
        """빈 requirements -> 빈 dict."""
        from projects.services.jd_analysis import requirements_to_search_filters

        assert requirements_to_search_filters({}) == {}
        assert requirements_to_search_filters(None) == {}

    def test_partial_requirements(self):
        """일부 필드만 있는 requirements도 정상 처리."""
        from projects.services.jd_analysis import requirements_to_search_filters

        reqs = {"position": "개발자", "keywords": ["Python"]}
        filters = requirements_to_search_filters(reqs)
        assert filters["position_keywords"] == ["개발자"]
        assert filters["skill_keywords"] == ["Python"]
        assert filters["gender"] is None
        assert filters["min_experience_years"] is None

    def test_no_position(self):
        """position이 없으면 position_keywords는 빈 리스트."""
        from projects.services.jd_analysis import requirements_to_search_filters

        reqs = {"keywords": ["Python"]}
        filters = requirements_to_search_filters(reqs)
        assert filters["position_keywords"] == []

    def test_certifications_merged(self):
        """required와 preferred 자격증이 하나의 리스트로 합쳐진다."""
        from projects.services.jd_analysis import requirements_to_search_filters

        reqs = {
            "position": "Test",
            "required_certifications": ["A", "B"],
            "preferred_certifications": ["C"],
        }
        filters = requirements_to_search_filters(reqs)
        assert filters["certification_keywords"] == ["A", "B", "C"]


class TestExtractJDRequirements:
    @patch("projects.services.jd_analysis._get_gemini_client")
    def test_successful_extraction(self, mock_client):
        """Gemini가 정상 응답 시 requirements를 반환한다."""
        from projects.services.jd_analysis import extract_jd_requirements

        mock_response = MagicMock()
        mock_response.text = '{"position": "개발자", "keywords": ["Python"]}'
        mock_client.return_value.models.generate_content.return_value = mock_response

        result = extract_jd_requirements("JD 텍스트")
        assert result["requirements"]["position"] == "개발자"
        assert result["full_analysis"]["position"] == "개발자"

    @patch("projects.services.jd_analysis._get_gemini_client")
    def test_all_retries_fail(self, mock_client):
        """3회 재시도 모두 실패 시 RuntimeError."""
        from projects.services.jd_analysis import extract_jd_requirements

        mock_client.return_value.models.generate_content.side_effect = Exception(
            "API error"
        )

        with pytest.raises(RuntimeError, match="JD 분석에 실패"):
            extract_jd_requirements("JD 텍스트")

    @patch("projects.services.jd_analysis._get_gemini_client")
    def test_invalid_response_retries(self, mock_client):
        """유효하지 않은 응답(position 키 없음)은 재시도한다."""
        from projects.services.jd_analysis import extract_jd_requirements

        bad_response = MagicMock()
        bad_response.text = '{"invalid": true}'
        good_response = MagicMock()
        good_response.text = '{"position": "개발자"}'

        mock_client.return_value.models.generate_content.side_effect = [
            bad_response,
            good_response,
        ]

        result = extract_jd_requirements("JD 텍스트")
        assert result["requirements"]["position"] == "개발자"


class TestAnalyzeJD:
    @patch("projects.services.jd_analysis.extract_jd_requirements")
    def test_reads_jd_raw_text_first(self, mock_extract):
        """jd_raw_text를 우선 읽는다."""
        from projects.services.jd_analysis import analyze_jd

        mock_extract.return_value = {
            "full_analysis": {"position": "개발자"},
            "requirements": {"position": "개발자"},
        }

        project = MagicMock()
        project.jd_raw_text = "raw text"
        project.jd_text = "user text"

        analyze_jd(project)
        mock_extract.assert_called_once_with("raw text")

    @patch("projects.services.jd_analysis.extract_jd_requirements")
    def test_falls_back_to_jd_text(self, mock_extract):
        """jd_raw_text가 비어있으면 jd_text를 읽는다."""
        from projects.services.jd_analysis import analyze_jd

        mock_extract.return_value = {
            "full_analysis": {"position": "개발자"},
            "requirements": {"position": "개발자"},
        }

        project = MagicMock()
        project.jd_raw_text = ""
        project.jd_text = "user text"

        analyze_jd(project)
        mock_extract.assert_called_once_with("user text")

    def test_raises_when_no_text(self):
        """JD 텍스트가 전혀 없으면 ValueError."""
        from projects.services.jd_analysis import analyze_jd

        project = MagicMock()
        project.jd_raw_text = ""
        project.jd_text = ""

        with pytest.raises(ValueError, match="분석할 JD 텍스트가 없습니다"):
            analyze_jd(project)

    @patch("projects.services.jd_analysis.extract_jd_requirements")
    def test_saves_results_to_project(self, mock_extract):
        """분석 결과가 프로젝트 필드에 저장된다."""
        from projects.services.jd_analysis import analyze_jd

        analysis_data = {"position": "개발자", "keywords": ["Python"]}
        mock_extract.return_value = {
            "full_analysis": analysis_data,
            "requirements": analysis_data,
        }

        project = MagicMock()
        project.jd_raw_text = "some text"
        project.jd_text = ""

        analyze_jd(project)

        assert project.jd_analysis == analysis_data
        assert project.requirements == analysis_data
        project.save.assert_called_once_with(
            update_fields=["jd_analysis", "requirements", "updated_at"]
        )


class TestExtractTextFromFile:
    def test_extracts_from_pdf(self, tmp_path):
        """PDF FileField에서 텍스트 추출."""
        import fitz

        from projects.services.jd_analysis import extract_text_from_file

        pdf_path = tmp_path / "test.pdf"
        doc = fitz.open()
        page = doc.new_page()
        # Use ASCII text to avoid font/encoding issues in CI
        page.insert_text((72, 72), "Software Engineer Job Description")
        doc.save(str(pdf_path))
        doc.close()

        # FileField mock
        mock_file = MagicMock()
        mock_file.name = "test.pdf"
        with open(pdf_path, "rb") as f:
            file_bytes = f.read()
        mock_file.chunks.return_value = [file_bytes]

        result = extract_text_from_file(mock_file)
        assert "Software Engineer" in result
