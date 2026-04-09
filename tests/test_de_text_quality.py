from data_extraction.services.text import classify_text_quality


class TestClassifyTextQuality:
    def test_empty_string(self):
        assert classify_text_quality("") == "empty"

    def test_none(self):
        assert classify_text_quality(None) == "empty"

    def test_whitespace_only(self):
        assert classify_text_quality("   \n\t  ") == "empty"

    def test_bom_only(self):
        assert classify_text_quality("\ufeff\n\n\n") == "garbled"

    def test_too_short(self):
        assert classify_text_quality("짧은 텍스트") == "too_short"

    def test_normal_resume(self):
        text = (
            "김철수\n서울시 강남구\n이메일: test@test.com\n경력사항\n삼성전자 2020-2024 개발팀 "
            * 5
        )
        assert classify_text_quality(text) == "ok"

    def test_garbled_special_chars(self):
        text = "###$$$%%%&&&***!!!" * 10
        assert classify_text_quality(text) == "garbled"

    def test_borderline_50_chars(self):
        text = "가" * 50
        assert classify_text_quality(text) == "ok"

    def test_just_under_50_chars(self):
        text = "가" * 49
        assert classify_text_quality(text) == "too_short"
