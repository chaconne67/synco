"""P03a: Candidate matching service tests.

Tests for 5-dimension scoring system, gap report generation,
and score-to-level conversion.
"""

from unittest.mock import MagicMock


def _make_candidate(**kwargs):
    """테스트용 mock 후보자 생성."""
    c = MagicMock()
    c.name = kwargs.get("name", "테스트")
    c.total_experience_years = kwargs.get("exp", 10)
    c.gender = kwargs.get("gender", "")
    c.birth_year = kwargs.get("birth_year", None)
    c.current_company = kwargs.get("company", "")
    c.current_position = kwargs.get("position", "")
    c.summary = kwargs.get("summary", "")
    c.skills = kwargs.get("skills", [])
    c.careers.all.return_value = kwargs.get("careers", [])
    c.certifications.all.return_value = kwargs.get("certifications", [])
    c.educations.all.return_value = kwargs.get("educations", [])
    return c


def _make_cert(name):
    cert = MagicMock()
    cert.name = name
    return cert


def _make_education(institution="", major=""):
    edu = MagicMock()
    edu.institution = institution
    edu.major = major
    return edu


class TestScoreExperience:
    def test_in_range(self):
        from projects.services.candidate_matching import _score_experience

        c = _make_candidate(exp=14)
        score, _ = _score_experience(
            c, {"min_experience_years": 12, "max_experience_years": 16}
        )
        assert score == 1.0

    def test_slightly_out_of_range(self):
        from projects.services.candidate_matching import _score_experience

        c = _make_candidate(exp=10)
        score, _ = _score_experience(
            c, {"min_experience_years": 12, "max_experience_years": 16}
        )
        assert score == 0.5

    def test_far_out_of_range(self):
        from projects.services.candidate_matching import _score_experience

        c = _make_candidate(exp=5)
        score, _ = _score_experience(
            c, {"min_experience_years": 12, "max_experience_years": 16}
        )
        assert score == 0.0

    def test_no_exp_data(self):
        from projects.services.candidate_matching import _score_experience

        c = _make_candidate(exp=None)
        score, reason = _score_experience(c, {"min_experience_years": 12})
        assert score == 0.5
        assert "판정 불가" in reason

    def test_no_requirements(self):
        from projects.services.candidate_matching import _score_experience

        c = _make_candidate(exp=10)
        score, _ = _score_experience(c, {})
        assert score == 1.0

    def test_exact_boundary(self):
        from projects.services.candidate_matching import _score_experience

        c = _make_candidate(exp=12)
        score, _ = _score_experience(
            c, {"min_experience_years": 12, "max_experience_years": 16}
        )
        assert score == 1.0

    def test_over_max_within_2(self):
        from projects.services.candidate_matching import _score_experience

        c = _make_candidate(exp=18)
        score, _ = _score_experience(
            c, {"min_experience_years": 12, "max_experience_years": 16}
        )
        assert score == 0.5


class TestScoreKeywords:
    def test_full_match(self):
        from projects.services.candidate_matching import _score_keywords

        c = _make_candidate(summary="QMS ISO IATF 경험 보유")
        score, _ = _score_keywords(c, {"keywords": ["QMS", "ISO", "IATF"]})
        assert score == 1.0

    def test_partial_match(self):
        from projects.services.candidate_matching import _score_keywords

        c = _make_candidate(summary="QMS 시스템 구축")
        score, _ = _score_keywords(c, {"keywords": ["QMS", "ISO", "IATF"]})
        assert abs(score - 1 / 3) < 0.01

    def test_no_keywords_requirement(self):
        from projects.services.candidate_matching import _score_keywords

        c = _make_candidate(summary="anything")
        score, _ = _score_keywords(c, {})
        assert score == 1.0

    def test_no_match(self):
        from projects.services.candidate_matching import _score_keywords

        c = _make_candidate(summary="마케팅 전문가")
        score, _ = _score_keywords(c, {"keywords": ["QMS", "ISO"]})
        assert score == 0.0


class TestScoreCertifications:
    def test_required_met(self):
        from projects.services.candidate_matching import _score_certifications

        c = _make_candidate(certifications=[_make_cert("품질경영기사")])
        score, _ = _score_certifications(
            c, {"required_certifications": ["품질경영기사"]}
        )
        assert score == 1.0

    def test_required_not_met(self):
        from projects.services.candidate_matching import _score_certifications

        c = _make_candidate(certifications=[])
        score, _ = _score_certifications(
            c, {"required_certifications": ["품질경영기사"]}
        )
        assert score == 0.0

    def test_preferred_bonus(self):
        from projects.services.candidate_matching import _score_certifications

        c = _make_candidate(certifications=[_make_cert("6Sigma BB")])
        score, _ = _score_certifications(
            c,
            {
                "required_certifications": [],
                "preferred_certifications": ["6Sigma BB"],
            },
        )
        # base_score=1.0 (no required), bonus=0.3
        assert score == 1.0  # capped at 1.0

    def test_no_cert_requirements(self):
        from projects.services.candidate_matching import _score_certifications

        c = _make_candidate()
        score, _ = _score_certifications(c, {})
        assert score == 1.0


class TestScoreDemographics:
    def test_gender_mismatch(self):
        from projects.services.candidate_matching import _score_demographics

        c = _make_candidate(gender="female")
        score, _ = _score_demographics(c, {"gender": "male"})
        assert score == 0.0

    def test_gender_match(self):
        from projects.services.candidate_matching import _score_demographics

        c = _make_candidate(gender="male")
        score, _ = _score_demographics(c, {"gender": "male"})
        assert score == 1.0

    def test_birth_year_out_of_range(self):
        from projects.services.candidate_matching import _score_demographics

        c = _make_candidate(birth_year=1990)
        score, _ = _score_demographics(
            c, {"birth_year_from": 1982, "birth_year_to": 1986}
        )
        assert score == 0.0

    def test_birth_year_in_range(self):
        from projects.services.candidate_matching import _score_demographics

        c = _make_candidate(birth_year=1984)
        score, _ = _score_demographics(
            c, {"birth_year_from": 1982, "birth_year_to": 1986}
        )
        assert score == 1.0

    def test_no_demographic_requirements(self):
        from projects.services.candidate_matching import _score_demographics

        c = _make_candidate()
        score, _ = _score_demographics(c, {})
        assert score == 1.0


class TestScoreEducation:
    def test_major_match(self):
        from projects.services.candidate_matching import _score_education

        edu = _make_education(institution="한양대학교", major="전자공학과")
        c = _make_candidate()
        c.educations.all.return_value = [edu]
        score, reason = _score_education(c, {"education_fields": ["전자공학"]})
        assert score >= 0.7
        assert "전공" in reason

    def test_no_education_data(self):
        from projects.services.candidate_matching import _score_education

        c = _make_candidate()
        c.educations.all.return_value = []
        score, reason = _score_education(c, {"education_fields": ["전자공학"]})
        assert score == 0.5
        assert "판정 불가" in reason

    def test_no_education_requirements(self):
        from projects.services.candidate_matching import _score_education

        c = _make_candidate()
        score, _ = _score_education(c, {})
        assert score == 1.0


class TestScoreToLevel:
    def test_levels(self):
        from projects.services.candidate_matching import _score_to_level

        assert _score_to_level(0.8) == "높음"
        assert _score_to_level(0.7) == "높음"
        assert _score_to_level(0.5) == "보통"
        assert _score_to_level(0.4) == "보통"
        assert _score_to_level(0.39) == "낮음"
        assert _score_to_level(0.2) == "낮음"
        assert _score_to_level(0.0) == "낮음"


class TestGenerateGapReport:
    def test_report_structure(self):
        from projects.services.candidate_matching import generate_gap_report

        c = _make_candidate(name="홍길동", exp=14, summary="QMS ISO")
        reqs = {"min_experience_years": 12, "keywords": ["QMS", "ISO"]}
        report = generate_gap_report(c, reqs)

        assert report["candidate_name"] == "홍길동"
        assert "overall_score" in report
        assert "overall_level" in report
        assert isinstance(report["met"], list)
        assert isinstance(report["unmet"], list)
        assert isinstance(report["unknown"], list)

    def test_perfect_candidate(self):
        from projects.services.candidate_matching import generate_gap_report

        c = _make_candidate(name="완벽", exp=14, summary="QMS ISO IATF")
        reqs = {
            "min_experience_years": 12,
            "max_experience_years": 16,
            "keywords": ["QMS", "ISO", "IATF"],
        }
        report = generate_gap_report(c, reqs)
        assert report["overall_level"] in ("높음", "보통")

    def test_poor_candidate(self):
        from projects.services.candidate_matching import generate_gap_report

        c = _make_candidate(name="부적합", exp=3, gender="female", birth_year=2000)
        reqs = {
            "min_experience_years": 12,
            "gender": "male",
            "birth_year_from": 1982,
            "birth_year_to": 1986,
            "keywords": ["QMS", "ISO"],
        }
        report = generate_gap_report(c, reqs)
        assert report["overall_level"] == "낮음"
        assert len(report["unmet"]) > 0
