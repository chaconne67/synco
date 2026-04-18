import pytest
from django.urls import reverse


@pytest.mark.django_db
def test_project_detail_has_area_a_and_b(client, user, project):
    """project_detail 페이지는 영역 A(id=project-area-a)와 영역 B(id=project-area-b)를 반드시 포함."""
    client.force_login(user)
    resp = client.get(reverse("projects:project_detail", args=[project.pk]))
    assert resp.status_code == 200
    content = resp.content.decode()
    assert 'id="project-area-a"' in content
    assert 'id="project-area-b"' in content
