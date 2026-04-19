import pytest
from candidates.models import Candidate, Category


@pytest.mark.django_db
def test_candidate_count_auto_increments_on_category_add():
    cat = Category.objects.create(name="Tech")
    assert cat.candidate_count == 0

    c = Candidate.objects.create(name="홍길동")
    c.categories.add(cat)

    cat.refresh_from_db()
    assert cat.candidate_count == 1


@pytest.mark.django_db
def test_candidate_count_decrements_on_category_remove():
    cat = Category.objects.create(name="Tech")
    c = Candidate.objects.create(name="홍길동")
    c.categories.add(cat)
    c.categories.remove(cat)

    cat.refresh_from_db()
    assert cat.candidate_count == 0


@pytest.mark.django_db
def test_candidate_count_decrements_on_candidate_delete():
    cat = Category.objects.create(name="Tech")
    c = Candidate.objects.create(name="홍길동")
    c.categories.add(cat)
    c.delete()

    cat.refresh_from_db()
    assert cat.candidate_count == 0
