import pytest

from candidates.models import ParseExample
from candidates.services.fewshot_store import (
    format_fewshot_prompt,
    get_fewshot_examples,
)


@pytest.mark.django_db
def test_get_fewshot_examples_empty():
    result = get_fewshot_examples("Plant")
    assert result == []


@pytest.mark.django_db
def test_get_fewshot_examples_returns_matching_category():
    ParseExample.objects.create(
        category="Plant",
        resume_pattern="영문+국문 혼합",
        input_excerpt="Daehan Solution LLC / President",
        correct_output={"company": "대한솔루션"},
    )
    ParseExample.objects.create(
        category="HR",
        resume_pattern="국문 전용",
        input_excerpt="삼성전자 인사팀",
        correct_output={"company": "삼성전자"},
    )
    result = get_fewshot_examples("Plant")
    assert len(result) == 1
    assert result[0].category == "Plant"


@pytest.mark.django_db
def test_get_fewshot_examples_max_3():
    for i in range(5):
        ParseExample.objects.create(
            category="Plant",
            resume_pattern=f"패턴{i}",
            input_excerpt=f"텍스트{i}",
            correct_output={"idx": i},
        )
    result = get_fewshot_examples("Plant", max_count=3)
    assert len(result) == 3


@pytest.mark.django_db
def test_format_fewshot_prompt_empty():
    assert format_fewshot_prompt([]) == ""


@pytest.mark.django_db
def test_format_fewshot_prompt_with_examples():
    ex = ParseExample.objects.create(
        category="Plant",
        resume_pattern="영문+국문 혼합",
        input_excerpt="Daehan Solution LLC",
        correct_output={"company": "대한솔루션"},
    )
    result = format_fewshot_prompt([ex])
    assert "대한솔루션" in result
    assert "Daehan Solution LLC" in result
