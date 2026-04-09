from data_extraction.services.filters import apply_regex_field_filters


def test_filters_phone_email_and_birth_year():
    extracted = {
        "email": " Contact: TEST.USER@Example.COM / alt ",
        "phone": "+966-5078-50224 / +82-10-9034-5062",
        "birth_year": "71년생",
    }

    normalized = apply_regex_field_filters(extracted)

    assert normalized["email"] == "test.user@example.com"
    assert normalized["phone"] == "+82-10-9034-5062"
    assert normalized["birth_year"] == 1971


def test_filters_dates_and_gender():
    extracted = {
        "gender": "남성",
        "resume_reference_date": "2025년 12월 31일 기준",
        "careers": [
            {
                "start_date": "2019.3 입사",
                "end_date": "2021년 7월 퇴사",
                "end_date_inferred": "2021/08 추정",
            }
        ],
        "certifications": [{"acquired_date": "2018년 5월 취득"}],
    }

    normalized = apply_regex_field_filters(extracted)

    assert normalized["gender"] == "male"
    assert normalized["resume_reference_date"] == "2025-12-31"
    assert normalized["careers"][0]["start_date"] == "2019-03"
    assert normalized["careers"][0]["end_date"] == "2021-07"
    assert normalized["careers"][0]["end_date_inferred"] == "2021-08"
    assert normalized["certifications"][0]["acquired_date"] == "2018-05"


def test_filters_language_score():
    extracted = {
        "language_skills": [
            {"score": "TOEIC 900점"},
            {"score": "OPIc IH"},
            {"score": "HSK 6급"},
        ]
    }

    normalized = apply_regex_field_filters(extracted)

    assert normalized["language_skills"][0]["score"] == "900점"
    assert normalized["language_skills"][1]["score"] == "IH"
    assert normalized["language_skills"][2]["score"] == "6급"
