import pytest
from django.contrib.auth import get_user_model
from candidates.models import Candidate


@pytest.fixture
def auth_client(client, db):
    User = get_user_model()
    u = User.objects.create_user(username="creator", password="x")
    client.force_login(u)
    return client


@pytest.mark.django_db
def test_new_page_renders(auth_client):
    resp = auth_client.get("/candidates/new/")
    assert resp.status_code == 200
    assert b'name="name"' in resp.content


@pytest.mark.django_db
def test_create_requires_email_or_phone(auth_client):
    resp = auth_client.post("/candidates/new/", {"name": "테스트이름A"})
    assert resp.status_code in (400, 200)
    assert not Candidate.objects.filter(name="테스트이름A").exists()


@pytest.mark.django_db
def test_create_with_email_succeeds(auth_client):
    resp = auth_client.post(
        "/candidates/new/",
        {
            "name": "테스트이름B",
            "email": "holong@ex.com",
            "current_company": "네이버",
        },
    )
    assert resp.status_code in (302, 200)
    assert Candidate.objects.filter(name="테스트이름B", email="holong@ex.com").exists()


@pytest.mark.django_db
def test_duplicate_email_warns(auth_client):
    Candidate.objects.create(name="기존후보자A", email="dup@ex.com")
    resp = auth_client.post(
        "/candidates/new/",
        {
            "name": "신규후보자A",
            "email": "dup@ex.com",
        },
    )
    assert resp.status_code == 200
    assert b"duplicate" in resp.content.lower() or "기존후보자A".encode("utf-8") in resp.content
    # Should NOT have created the new one (still duplicate warning screen)
    assert not Candidate.objects.filter(name="신규후보자A").exists()


@pytest.mark.django_db
def test_duplicate_phone_warns(auth_client):
    Candidate.objects.create(name="기존후보자B", phone="010-1234-5678")
    resp = auth_client.post(
        "/candidates/new/",
        {
            "name": "신규후보자B",
            "phone": "01012345678",
        },
    )
    assert resp.status_code == 200
    assert "기존후보자B".encode("utf-8") in resp.content
    assert not Candidate.objects.filter(name="신규후보자B").exists()


from django.core.files.uploadedfile import SimpleUploadedFile


@pytest.mark.django_db
def test_resume_upload_rejects_large_file(auth_client, monkeypatch):
    # Prevent any real Drive call
    monkeypatch.setattr(
        "candidates.services.candidate_create._upload_to_drive",
        lambda path, name: None,
    )
    big = SimpleUploadedFile("big.pdf", b"x" * (11 * 1024 * 1024), content_type="application/pdf")
    auth_client.post(
        "/candidates/new/",
        {"name": "업로드큼", "email": "toobig@ex.com", "resume_file": big},
    )
    # Candidate is created; Resume is not (size rejected via messages)
    from candidates.models import Resume
    c = Candidate.objects.filter(email="toobig@ex.com").first()
    if c:
        assert not Resume.objects.filter(candidate=c).exists()


@pytest.mark.django_db
def test_resume_upload_rejects_bad_extension(auth_client, monkeypatch):
    monkeypatch.setattr(
        "candidates.services.candidate_create._upload_to_drive",
        lambda path, name: None,
    )
    bad = SimpleUploadedFile("resume.exe", b"x", content_type="application/octet-stream")
    auth_client.post(
        "/candidates/new/",
        {"name": "업로드나쁨", "email": "badext@ex.com", "resume_file": bad},
    )
    from candidates.models import Resume
    assert not Resume.objects.filter(file_name__endswith=".exe").exists()


@pytest.mark.django_db
def test_resume_upload_success_creates_pending_resume(auth_client, monkeypatch):
    monkeypatch.setattr(
        "candidates.services.candidate_create._upload_to_drive",
        lambda path, name: None,  # Simulate Drive-unavailable; placeholder id is generated
    )
    good = SimpleUploadedFile("cv.pdf", b"%PDF-1.4", content_type="application/pdf")
    auth_client.post(
        "/candidates/new/",
        {"name": "업로드성공", "email": "upload@ex.com", "resume_file": good},
    )
    from candidates.models import Resume
    c = Candidate.objects.get(email="upload@ex.com")
    assert c.current_resume is not None
    assert c.current_resume.processing_status == Resume.ProcessingStatus.PENDING
    assert c.current_resume.drive_folder == "수동등록"
    assert c.current_resume.drive_file_id.startswith("manual-")
