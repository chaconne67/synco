"""P19: Comprehensive tests for Chrome Extension API endpoints."""

import json

from django.test import TestCase, Client as DjangoClient

from accounts.models import Membership, Organization, User
from candidates.models import Candidate, Education, ExtractionLog


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

AUTH_URL = "/candidates/extension/auth-status/"
SAVE_URL = "/candidates/extension/save-profile/"
CHECK_URL = "/candidates/extension/check-duplicate/"
SEARCH_URL = "/candidates/extension/search/"
STATS_URL = "/candidates/extension/stats/"


def _base_payload(**overrides):
    """Minimal valid save-profile payload."""
    data = {
        "name": "홍길동",
        "current_company": "삼성전자",
        "current_position": "부장",
        "email": "hong@test.com",
        "phone": "010-1234-5678",
        "external_profile_url": "https://linkedin.com/in/hong",
        "careers": [],
        "educations": [],
        "skills": [],
        "source_site": "linkedin",
        "source_url": "https://linkedin.com/in/hong",
    }
    data.update(overrides)
    return data


def _post_json(client, url, data):
    return client.post(url, data=json.dumps(data), content_type="application/json")


class _ExtensionTestMixin:
    """Common setup: user + org + logged-in client."""

    def _setup(self):
        self.org = Organization.objects.create(name="Test Org")
        self.user = User.objects.create_user(username="ext_user", password="pass1234")
        Membership.objects.create(user=self.user, organization=self.org)
        self.client = DjangoClient()
        self.client.login(username="ext_user", password="pass1234")


# ===========================================================================
# Auth
# ===========================================================================


class TestExtensionAuth(TestCase):
    """인증 테스트."""

    def setUp(self):
        self.org = Organization.objects.create(name="Auth Org")
        self.user = User.objects.create_user(
            username="authuser", password="pass1234", first_name="길동", last_name="홍"
        )

    def test_unauthenticated_returns_401_json(self):
        resp = self.client.get(AUTH_URL)
        self.assertEqual(resp.status_code, 401)
        body = resp.json()
        self.assertEqual(body["status"], "error")

    def test_authenticated_returns_user_and_org(self):
        Membership.objects.create(user=self.user, organization=self.org)
        self.client.login(username="authuser", password="pass1234")
        resp = self.client.get(AUTH_URL)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "success")
        self.assertTrue(body["data"]["authenticated"])
        self.assertEqual(body["data"]["organization"], "Auth Org")
        # user should be full_name or username
        self.assertIn("홍", body["data"]["user"])

    def test_no_membership_returns_null_org(self):
        self.client.login(username="authuser", password="pass1234")
        resp = self.client.get(AUTH_URL)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertIsNone(body["data"]["organization"])


# ===========================================================================
# Save Profile
# ===========================================================================


class TestExtensionSaveProfile(_ExtensionTestMixin, TestCase):
    """프로필 저장 테스트."""

    def setUp(self):
        self._setup()

    # --- Happy path ---

    def test_create_new_candidate_201(self):
        resp = _post_json(self.client, SAVE_URL, _base_payload())
        self.assertEqual(resp.status_code, 201)
        body = resp.json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["data"]["operation"], "created")
        self.assertTrue(
            Candidate.objects.filter(name="홍길동", owned_by=self.org).exists()
        )

    def test_create_with_careers_and_educations(self):
        payload = _base_payload(
            careers=[
                {
                    "company": "삼성전자",
                    "position": "부장",
                    "start_date": "2020-01",
                    "end_date": "",
                    "is_current": "true",
                    "department": "개발",
                    "duties": "소프트웨어 개발",
                },
            ],
            educations=[
                {
                    "institution": "서울대학교",
                    "degree": "학사",
                    "major": "컴퓨터공학",
                    "start_year": "2010",
                    "end_year": "2014",
                },
            ],
        )
        resp = _post_json(self.client, SAVE_URL, payload)
        self.assertEqual(resp.status_code, 201)
        cid = resp.json()["data"]["candidate_id"]
        candidate = Candidate.objects.get(id=cid)
        self.assertEqual(candidate.careers.count(), 1)
        self.assertEqual(candidate.educations.count(), 1)
        career = candidate.careers.first()
        self.assertEqual(career.company, "삼성전자")
        self.assertTrue(career.is_current)
        edu = candidate.educations.first()
        self.assertEqual(edu.start_year, 2010)
        self.assertEqual(edu.end_year, 2014)

    # --- Validation errors ---

    def test_missing_name_returns_400(self):
        resp = _post_json(self.client, SAVE_URL, _base_payload(name=""))
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertIn("name is required", body["errors"])

    def test_missing_all_secondary_identifiers_400(self):
        payload = _base_payload(
            current_company="",
            current_position="",
            email="",
            phone="",
            external_profile_url="",
        )
        resp = _post_json(self.client, SAVE_URL, payload)
        self.assertEqual(resp.status_code, 400)

    def test_name_plus_phone_accepted(self):
        payload = _base_payload(
            current_company="",
            current_position="",
            email="",
            external_profile_url="",
            phone="010-9999-8888",
        )
        resp = _post_json(self.client, SAVE_URL, payload)
        self.assertEqual(resp.status_code, 201)

    # --- Sanitization ---

    def test_html_stripped_from_fields(self):
        payload = _base_payload(
            name="<b>홍길동</b>",
            current_company="<script>alert(1)</script>삼성",
            external_profile_url="https://linkedin.com/in/hong-clean",
        )
        resp = _post_json(self.client, SAVE_URL, payload)
        self.assertEqual(resp.status_code, 201)
        cid = resp.json()["data"]["candidate_id"]
        c = Candidate.objects.get(id=cid)
        self.assertNotIn("<b>", c.name)
        self.assertNotIn("<script>", c.current_company)
        self.assertEqual(c.name, "홍길동")

    def test_none_values_become_empty_string(self):
        payload = _base_payload(
            address=None,
            current_position=None,
            # keep at least one secondary: company
            current_company="삼성전자",
        )
        resp = _post_json(self.client, SAVE_URL, payload)
        self.assertEqual(resp.status_code, 201)
        cid = resp.json()["data"]["candidate_id"]
        c = Candidate.objects.get(id=cid)
        self.assertEqual(c.address, "")

    # --- Duplicate detection ---

    def test_duplicate_url_returns_409_with_diff(self):
        # Create initial
        _post_json(self.client, SAVE_URL, _base_payload())
        # Try duplicate
        resp = _post_json(
            self.client, SAVE_URL, _base_payload(current_company="LG전자")
        )
        self.assertEqual(resp.status_code, 409)
        body = resp.json()
        self.assertIn(body["status"], ("duplicate_found", "possible_match"))

    def test_possible_match_returns_409(self):
        # Create initial with no URL so only name+company match
        _post_json(
            self.client,
            SAVE_URL,
            _base_payload(
                email="first@test.com",
                external_profile_url="https://linkedin.com/in/first",
                phone="010-1111-2222",
            ),
        )
        # Different email/url/phone, same name+company → possible match
        resp = _post_json(
            self.client,
            SAVE_URL,
            _base_payload(
                email="second@test.com",
                external_profile_url="https://linkedin.com/in/second",
                phone="010-3333-4444",
            ),
        )
        self.assertEqual(resp.status_code, 409)
        body = resp.json()
        self.assertEqual(body["status"], "possible_match")

    def test_concurrent_save_same_url_one_succeeds(self):
        """Two sequential saves with the same URL: first succeeds, second is duplicate."""
        payload = _base_payload()
        resp1 = _post_json(self.client, SAVE_URL, payload)
        self.assertEqual(resp1.status_code, 201)

        # Second save with identical URL → 409 duplicate
        resp2 = _post_json(self.client, SAVE_URL, payload)
        self.assertEqual(resp2.status_code, 409)

    # --- Org isolation ---

    def test_cross_org_isolation(self):
        """Same URL in different org should create independently."""
        other_org = Organization.objects.create(name="Other Org")
        other_user = User.objects.create_user(username="other_ext", password="pass1234")
        Membership.objects.create(user=other_user, organization=other_org)

        # Save in org1
        resp1 = _post_json(self.client, SAVE_URL, _base_payload())
        self.assertEqual(resp1.status_code, 201)

        # Save same URL in org2
        other_client = DjangoClient()
        other_client.login(username="other_ext", password="pass1234")
        resp2 = _post_json(other_client, SAVE_URL, _base_payload())
        self.assertEqual(resp2.status_code, 201)

    # --- Rate limit ---

    def test_rate_limit_101st_returns_429(self):
        # Pre-seed 100 extraction logs for today
        candidate = Candidate.objects.create(
            name="Seed", owned_by=self.org, current_company="Test"
        )
        for _ in range(100):
            ExtractionLog.objects.create(
                candidate=candidate,
                action=ExtractionLog.Action.EXTENSION_SAVE,
                actor=self.user,
                details={},
            )
        payload = _base_payload(
            email="fresh@new.com",
            external_profile_url="https://linkedin.com/in/fresh",
        )
        resp = _post_json(self.client, SAVE_URL, payload)
        self.assertEqual(resp.status_code, 429)

    # --- Size / format guards ---

    def test_payload_too_large_returns_413(self):
        # Build a payload > 100KB
        huge = "x" * (101 * 1024)
        resp = self.client.post(
            SAVE_URL,
            data=huge,
            content_type="application/json",
        )
        self.assertEqual(resp.status_code, 413)

    def test_invalid_json_returns_400(self):
        resp = self.client.post(
            SAVE_URL, data="not json", content_type="application/json"
        )
        self.assertEqual(resp.status_code, 400)

    def test_non_object_json_returns_400(self):
        resp = self.client.post(
            SAVE_URL, data=json.dumps([1, 2, 3]), content_type="application/json"
        )
        self.assertEqual(resp.status_code, 400)
        self.assertIn("Expected JSON object", resp.json()["errors"])

    # --- Metadata ---

    def test_source_set_to_chrome_ext(self):
        resp = _post_json(self.client, SAVE_URL, _base_payload())
        self.assertEqual(resp.status_code, 201)
        cid = resp.json()["data"]["candidate_id"]
        c = Candidate.objects.get(id=cid)
        self.assertEqual(c.source, Candidate.Source.CHROME_EXT)

    def test_consent_status_not_requested(self):
        resp = _post_json(self.client, SAVE_URL, _base_payload())
        self.assertEqual(resp.status_code, 201)
        cid = resp.json()["data"]["candidate_id"]
        c = Candidate.objects.get(id=cid)
        self.assertEqual(c.consent_status, "not_requested")

    def test_extraction_log_created_with_actor_details(self):
        resp = _post_json(self.client, SAVE_URL, _base_payload())
        self.assertEqual(resp.status_code, 201)
        cid = resp.json()["data"]["candidate_id"]
        log = ExtractionLog.objects.filter(
            candidate_id=cid,
            action=ExtractionLog.Action.EXTENSION_SAVE,
        ).first()
        self.assertIsNotNone(log)
        self.assertEqual(log.actor, self.user)
        self.assertEqual(log.details["operation"], "created")
        self.assertEqual(log.details["source_site"], "linkedin")

    # --- Education year parsing ---

    def test_education_year_string_parsed(self):
        payload = _base_payload(
            educations=[
                {
                    "institution": "MIT",
                    "degree": "MS",
                    "major": "CS",
                    "start_year": "2010",
                    "end_year": "2012",
                },
            ],
        )
        resp = _post_json(self.client, SAVE_URL, payload)
        self.assertEqual(resp.status_code, 201)
        cid = resp.json()["data"]["candidate_id"]
        edu = Education.objects.filter(candidate_id=cid).first()
        self.assertEqual(edu.start_year, 2010)
        self.assertEqual(edu.end_year, 2012)

    def test_education_year_invalid_becomes_none(self):
        payload = _base_payload(
            educations=[
                {
                    "institution": "MIT",
                    "degree": "MS",
                    "major": "CS",
                    "start_year": "not-a-year",
                    "end_year": "",
                },
            ],
        )
        resp = _post_json(self.client, SAVE_URL, payload)
        self.assertEqual(resp.status_code, 201)
        cid = resp.json()["data"]["candidate_id"]
        edu = Education.objects.filter(candidate_id=cid).first()
        self.assertIsNone(edu.start_year)
        self.assertIsNone(edu.end_year)

    # --- Malformed array items ---

    def test_malformed_career_item_skipped(self):
        payload = _base_payload(
            careers=[
                "not a dict",
                42,
                {"company": "삼성전자", "position": "과장"},
            ],
        )
        resp = _post_json(self.client, SAVE_URL, payload)
        self.assertEqual(resp.status_code, 201)
        cid = resp.json()["data"]["candidate_id"]
        c = Candidate.objects.get(id=cid)
        self.assertEqual(c.careers.count(), 1)

    # --- Field length limits ---

    def test_long_email_rejected(self):
        long_email = "a" * 250 + "@test.com"  # > 254 chars
        payload = _base_payload(email=long_email)
        resp = _post_json(self.client, SAVE_URL, payload)
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(any("email" in e for e in resp.json()["errors"]))

    def test_long_url_rejected(self):
        long_url = "https://linkedin.com/in/" + "x" * 500  # > 500 chars
        payload = _base_payload(external_profile_url=long_url)
        resp = _post_json(self.client, SAVE_URL, payload)
        self.assertEqual(resp.status_code, 400)
        self.assertTrue(any("external_profile_url" in e for e in resp.json()["errors"]))


# ===========================================================================
# Update Mode
# ===========================================================================


class TestExtensionUpdateMode(_ExtensionTestMixin, TestCase):
    """업데이트 모드 테스트."""

    def setUp(self):
        self._setup()
        # Create a candidate to update
        resp = _post_json(self.client, SAVE_URL, _base_payload())
        self.assertEqual(resp.status_code, 201)
        self.candidate_id = resp.json()["data"]["candidate_id"]

    def _update_payload(self, **overrides):
        data = {
            "name": "홍길동",
            "update_mode": True,
            "candidate_id": self.candidate_id,
            "fields": [],
            "current_company": "삼성전자",
            "current_position": "부장",
            "email": "hong@test.com",
            "external_profile_url": "https://linkedin.com/in/hong",
            "new_careers_confirmed": [],
            "new_educations_confirmed": [],
            "source_site": "linkedin",
            "source_url": "https://linkedin.com/in/hong",
        }
        data.update(overrides)
        return data

    def test_update_confirmed_fields(self):
        payload = self._update_payload(
            fields=["current_company", "current_position"],
            current_company="LG전자",
            current_position="상무",
        )
        resp = _post_json(self.client, SAVE_URL, payload)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["data"]["operation"], "updated")
        c = Candidate.objects.get(id=self.candidate_id)
        self.assertEqual(c.current_company, "LG전자")
        self.assertEqual(c.current_position, "상무")

    def test_update_external_url(self):
        payload = self._update_payload(
            fields=["external_profile_url"],
            external_profile_url="https://linkedin.com/in/hong-new",
        )
        resp = _post_json(self.client, SAVE_URL, payload)
        self.assertEqual(resp.status_code, 200)
        c = Candidate.objects.get(id=self.candidate_id)
        # URL should be normalized (lowercase, no trailing slash)
        self.assertEqual(c.external_profile_url, "https://linkedin.com/in/hong-new")

    def test_update_new_careers_confirmed(self):
        payload = self._update_payload(
            new_careers_confirmed=[
                {
                    "company": "LG전자",
                    "position": "상무",
                    "start_date": "2024-01",
                    "end_date": "",
                    "is_current": "true",
                    "department": "경영",
                    "duties": "경영 총괄",
                },
            ],
        )
        resp = _post_json(self.client, SAVE_URL, payload)
        self.assertEqual(resp.status_code, 200)
        c = Candidate.objects.get(id=self.candidate_id)
        self.assertTrue(c.careers.filter(company="LG전자").exists())

    def test_update_new_educations_confirmed(self):
        payload = self._update_payload(
            new_educations_confirmed=[
                {
                    "institution": "KAIST",
                    "degree": "석사",
                    "major": "AI",
                    "start_year": "2018",
                    "end_year": "2020",
                },
            ],
        )
        resp = _post_json(self.client, SAVE_URL, payload)
        self.assertEqual(resp.status_code, 200)
        c = Candidate.objects.get(id=self.candidate_id)
        self.assertTrue(c.educations.filter(institution="KAIST").exists())

    def test_update_wrong_org_returns_404(self):
        other_org = Organization.objects.create(name="Wrong Org")
        other_user = User.objects.create_user(
            username="wrong_user", password="pass1234"
        )
        Membership.objects.create(user=other_user, organization=other_org)
        other_client = DjangoClient()
        other_client.login(username="wrong_user", password="pass1234")
        payload = self._update_payload()
        resp = _post_json(other_client, SAVE_URL, payload)
        self.assertEqual(resp.status_code, 404)

    def test_update_url_conflict_returns_409(self):
        # Create a second candidate with a different URL
        resp2 = _post_json(
            self.client,
            SAVE_URL,
            _base_payload(
                email="other@test.com",
                external_profile_url="https://linkedin.com/in/other",
                phone="010-5555-6666",
                name="김철수",
                current_company="현대",
            ),
        )
        self.assertEqual(resp2.status_code, 201)
        second_id = resp2.json()["data"]["candidate_id"]

        # Try to update second candidate's URL to first candidate's URL
        payload = {
            "name": "김철수",
            "update_mode": True,
            "candidate_id": second_id,
            "fields": ["external_profile_url"],
            "external_profile_url": "https://linkedin.com/in/hong",
            "current_company": "현대",
            "source_site": "linkedin",
            "source_url": "https://linkedin.com/in/other",
        }
        resp = _post_json(self.client, SAVE_URL, payload)
        self.assertEqual(resp.status_code, 409)


# ===========================================================================
# Check Duplicate
# ===========================================================================


class TestExtensionCheckDuplicate(_ExtensionTestMixin, TestCase):
    """중복 체크 테스트."""

    def setUp(self):
        self._setup()
        # Seed a candidate
        self.candidate = Candidate.objects.create(
            name="박영희",
            current_company="삼성전자",
            current_position="과장",
            email="park@test.com",
            phone="010-9876-5432",
            phone_normalized="01098765432",
            external_profile_url="https://linkedin.com/in/park",
            owned_by=self.org,
        )

    def test_exact_match_by_url(self):
        resp = _post_json(
            self.client,
            CHECK_URL,
            {"external_profile_url": "https://linkedin.com/in/park"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "duplicate_found")
        self.assertEqual(body["data"]["candidate_id"], str(self.candidate.id))

    def test_exact_match_by_email(self):
        resp = _post_json(
            self.client,
            CHECK_URL,
            {"email": "park@test.com"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "duplicate_found")
        self.assertEqual(body["data"]["match_reason"], "email")

    def test_exact_match_by_phone(self):
        resp = _post_json(
            self.client,
            CHECK_URL,
            {"phone": "010-9876-5432"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "duplicate_found")
        self.assertEqual(body["data"]["match_reason"], "phone")

    def test_possible_match_by_name_company_iexact(self):
        resp = _post_json(
            self.client,
            CHECK_URL,
            {
                "name": "박영희",
                "current_company": "삼성전자",
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        # Could be duplicate_found (by empty url/email/phone) or possible_match
        # Since we didn't supply url/email/phone the identity check falls through to name+company
        self.assertEqual(body["status"], "possible_match")
        self.assertTrue(len(body["data"]["possible_matches"]) >= 1)

    def test_no_match(self):
        resp = _post_json(
            self.client,
            CHECK_URL,
            {
                "name": "신규인물",
                "current_company": "없는회사",
            },
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "success")
        self.assertFalse(body["data"]["exists"])

    def test_cross_org_isolation(self):
        """Other org cannot see this org's candidates."""
        other_org = Organization.objects.create(name="Isolated Org")
        other_user = User.objects.create_user(username="isolated", password="pass1234")
        Membership.objects.create(user=other_user, organization=other_org)
        other_client = DjangoClient()
        other_client.login(username="isolated", password="pass1234")

        resp = _post_json(
            other_client,
            CHECK_URL,
            {"email": "park@test.com"},
        )
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "success")
        self.assertFalse(body["data"]["exists"])

    def test_invalid_json_returns_400(self):
        resp = self.client.post(
            CHECK_URL, data="invalid", content_type="application/json"
        )
        self.assertEqual(resp.status_code, 400)


# ===========================================================================
# Search
# ===========================================================================


class TestExtensionSearch(_ExtensionTestMixin, TestCase):
    """검색 테스트."""

    def setUp(self):
        self._setup()
        # Seed candidates
        self.c1 = Candidate.objects.create(
            name="이영수",
            current_company="삼성전자",
            current_position="부장",
            owned_by=self.org,
        )
        self.c2 = Candidate.objects.create(
            name="김철호",
            current_company="LG전자",
            current_position="과장",
            owned_by=self.org,
        )

    def test_search_by_name(self):
        resp = self.client.get(SEARCH_URL, {"q": "이영수"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["data"]["total"], 1)
        self.assertEqual(body["data"]["results"][0]["name"], "이영수")

    def test_search_by_company(self):
        resp = self.client.get(SEARCH_URL, {"q": "삼성전자"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["data"]["total"], 1)
        self.assertEqual(body["data"]["results"][0]["company"], "삼성전자")

    def test_search_min_query_length(self):
        resp = self.client.get(SEARCH_URL, {"q": "이"})
        self.assertEqual(resp.status_code, 400)
        body = resp.json()
        self.assertIn("at least 2 characters", body["errors"][0])

    def test_search_pagination(self):
        # Create 25 candidates to test pagination (page_size=20)
        for i in range(25):
            Candidate.objects.create(
                name=f"테스트인원{i:02d}",
                current_company="일괄회사",
                owned_by=self.org,
            )
        resp = self.client.get(SEARCH_URL, {"q": "일괄회사", "page": "1"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(len(body["data"]["results"]), 20)
        self.assertEqual(body["data"]["total"], 25)
        self.assertEqual(body["data"]["page"], 1)

        # Page 2
        resp2 = self.client.get(SEARCH_URL, {"q": "일괄회사", "page": "2"})
        body2 = resp2.json()
        self.assertEqual(len(body2["data"]["results"]), 5)
        self.assertEqual(body2["data"]["page"], 2)

    def test_search_invalid_page(self):
        resp = self.client.get(SEARCH_URL, {"q": "이영수", "page": "abc"})
        # Invalid page defaults to 1
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["data"]["page"], 1)

    def test_cross_org_isolation(self):
        other_org = Organization.objects.create(name="Search Isolated")
        other_user = User.objects.create_user(
            username="search_iso", password="pass1234"
        )
        Membership.objects.create(user=other_user, organization=other_org)
        other_client = DjangoClient()
        other_client.login(username="search_iso", password="pass1234")

        resp = other_client.get(SEARCH_URL, {"q": "이영수"})
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["data"]["total"], 0)


# ===========================================================================
# Stats
# ===========================================================================


class TestExtensionStats(_ExtensionTestMixin, TestCase):
    """통계 테스트."""

    def setUp(self):
        self._setup()

    def test_returns_org_candidate_count(self):
        Candidate.objects.create(name="A", owned_by=self.org, current_company="X")
        Candidate.objects.create(name="B", owned_by=self.org, current_company="Y")
        resp = self.client.get(STATS_URL)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["status"], "success")
        self.assertEqual(body["data"]["total_candidates"], 2)

    def test_cross_org_isolation(self):
        other_org = Organization.objects.create(name="Stats Isolated")
        other_user = User.objects.create_user(username="stats_iso", password="pass1234")
        Membership.objects.create(user=other_user, organization=other_org)

        # Create candidates in the original org
        Candidate.objects.create(name="A", owned_by=self.org, current_company="X")

        # Other org should see 0
        other_client = DjangoClient()
        other_client.login(username="stats_iso", password="pass1234")
        resp = other_client.get(STATS_URL)
        self.assertEqual(resp.status_code, 200)
        body = resp.json()
        self.assertEqual(body["data"]["total_candidates"], 0)
