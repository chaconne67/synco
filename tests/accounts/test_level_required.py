import pytest
from django.contrib.auth.models import AnonymousUser
from django.http import HttpResponse

from accounts.decorators import level_required, superuser_required


@level_required(1)
def staff_view(request):
    return HttpResponse("ok")


@level_required(2)
def boss_view(request):
    return HttpResponse("ok")


@superuser_required
def dev_view(request):
    return HttpResponse("ok")


@pytest.mark.django_db
def test_pending_redirected_to_approval(rf, pending_user):
    req = rf.get("/")
    req.user = pending_user
    resp = staff_view(req)
    assert resp.status_code == 302
    assert resp["Location"].endswith("/accounts/pending/")


@pytest.mark.django_db
def test_staff_passes_level_1(rf, staff_user):
    req = rf.get("/")
    req.user = staff_user
    resp = staff_view(req)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_staff_forbidden_on_level_2(rf, staff_user):
    req = rf.get("/")
    req.user = staff_user
    resp = boss_view(req)
    assert resp.status_code == 403


@pytest.mark.django_db
def test_boss_passes_level_2(rf, boss_user):
    req = rf.get("/")
    req.user = boss_user
    resp = boss_view(req)
    assert resp.status_code == 200


@pytest.mark.django_db
def test_superuser_passes_all_levels(rf, dev_user):
    req = rf.get("/")
    req.user = dev_user
    assert staff_view(req).status_code == 200
    assert boss_view(req).status_code == 200
    assert dev_view(req).status_code == 200


@pytest.mark.django_db
def test_boss_blocked_from_superuser_view(rf, boss_user):
    req = rf.get("/")
    req.user = boss_user
    resp = dev_view(req)
    assert resp.status_code == 403


@pytest.mark.django_db
def test_anonymous_redirected_to_login(rf):
    req = rf.get("/")
    req.user = AnonymousUser()
    resp = staff_view(req)
    assert resp.status_code == 302
    assert "/accounts/login" in resp["Location"]
