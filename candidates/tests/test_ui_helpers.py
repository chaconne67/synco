from types import SimpleNamespace
from candidates.templatetags.candidate_ui import language_level_bars, review_notice_pill


def _lang(level="", test_name="", score=""):
    return SimpleNamespace(level=level, test_name=test_name, score=score)


def test_language_level_bars_native():
    assert language_level_bars(_lang(level="Native")) == 4
    assert language_level_bars(_lang(level="원어민")) == 4


def test_language_level_bars_business():
    assert language_level_bars(_lang(level="Business")) == 3
    assert language_level_bars(_lang(level="고급")) == 3


def test_language_level_bars_intermediate():
    assert language_level_bars(_lang(level="중급")) == 2
    assert language_level_bars(_lang(test_name="TOEIC", score="750")) == 2  # default


def test_language_level_bars_basic():
    assert language_level_bars(_lang(level="Basic")) == 1
    assert language_level_bars(_lang(level="초급")) == 1


def test_language_level_bars_empty_returns_default_2():
    assert language_level_bars(_lang()) == 2


def test_review_notice_pill_red_highest():
    c = SimpleNamespace(
        review_notice_red_count=2,
        review_notice_yellow_count=5,
        review_notice_blue_count=1,
    )
    pill = review_notice_pill(c)
    assert pill["severity"] == "red"
    assert pill["count"] == 2
    assert "중요" in pill["label"]


def test_review_notice_pill_yellow_when_no_red():
    c = SimpleNamespace(
        review_notice_red_count=0,
        review_notice_yellow_count=3,
        review_notice_blue_count=1,
    )
    pill = review_notice_pill(c)
    assert pill["severity"] == "yellow"
    assert pill["count"] == 3


def test_review_notice_pill_none_when_all_zero():
    c = SimpleNamespace(
        review_notice_red_count=0,
        review_notice_yellow_count=0,
        review_notice_blue_count=0,
    )
    assert review_notice_pill(c) is None
