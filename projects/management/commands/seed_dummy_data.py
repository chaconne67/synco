"""디자인 테스트용 더미 데이터 시딩.

사용법:
    uv run python manage.py seed_dummy_data              # 기본 조직(테스트조직)에 시딩
    uv run python manage.py seed_dummy_data --org "Test"
    uv run python manage.py seed_dummy_data --wipe       # 기존 더미 제거 후 재생성

더미 표시는 Client.notes / Project.note / Candidate.summary 에
``[DUMMY]`` 프리픽스로 남긴다. --wipe 는 해당 프리픽스가 붙은 레코드만 지운다.
"""

from __future__ import annotations

import random
from datetime import timedelta

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction
from django.utils import timezone

from accounts.models import Organization
from candidates.models import Candidate, Career, Education
from clients.models import Client
from projects.models import (
    ActionChannel,
    ActionItem,
    ActionItemStatus,
    ActionType,
    Application,
    Project,
    ProjectPhase,
    ProjectStatus,
)

DUMMY_TAG = "[DUMMY]"

CLIENT_SEEDS = [
    ("삼성전자", "제조/전자", "대기업", "수원"),
    ("네이버", "IT/플랫폼", "대기업", "판교"),
    ("카카오", "IT/플랫폼", "대기업", "판교"),
    ("현대자동차", "자동차", "대기업", "서울"),
    ("토스", "핀테크", "스타트업", "서울"),
    ("쿠팡", "이커머스", "대기업", "서울"),
    ("LG에너지솔루션", "2차전지", "대기업", "서울"),
    ("SK하이닉스", "반도체", "대기업", "이천"),
    ("배달의민족", "플랫폼", "중견", "서울"),
    ("당근마켓", "플랫폼", "스타트업", "서울"),
]

PROJECT_TITLES = [
    "AI/ML 엔지니어",
    "백엔드 리드",
    "시니어 프론트엔드 개발자",
    "프로덕트 매니저",
    "데이터 사이언티스트",
    "CTO 후보",
    "HR 팀장",
    "재무회계 이사",
    "SRE/인프라 엔지니어",
    "UX 디자인 리드",
    "글로벌 세일즈 디렉터",
    "반도체 공정 엔지니어",
    "마케팅 총괄",
    "전략기획 임원",
    "법무 실장",
]

CANDIDATE_NAMES = [
    "김민준",
    "이서연",
    "박지후",
    "최수아",
    "정도윤",
    "강하은",
    "조시우",
    "윤지민",
    "장예준",
    "임서윤",
    "한도현",
    "오유진",
    "서지호",
    "신은서",
    "권태윤",
    "홍민서",
    "고하준",
    "문채원",
    "백시현",
    "남주하",
    "유건우",
    "허나연",
    "송지안",
    "안예서",
    "노승우",
    "구민재",
    "배시은",
    "전우빈",
    "황수빈",
    "양재현",
]

COMPANIES = [
    "삼성전자",
    "네이버",
    "카카오",
    "SK텔레콤",
    "현대자동차",
    "LG전자",
    "쿠팡",
    "토스",
    "당근마켓",
    "우아한형제들",
    "넥슨",
    "엔씨소프트",
    "넷마블",
    "라인",
    "하이브",
]

POSITIONS = [
    "선임 연구원",
    "책임 연구원",
    "수석 연구원",
    "팀장",
    "파트장",
    "시니어 매니저",
    "디렉터",
    "그룹장",
    "실장",
    "매니저",
]

UNIVERSITIES = [
    "서울대학교",
    "연세대학교",
    "고려대학교",
    "KAIST",
    "POSTECH",
    "한양대학교",
    "성균관대학교",
    "서강대학교",
    "중앙대학교",
    "경희대학교",
]

MAJORS = [
    "컴퓨터공학",
    "전자공학",
    "산업공학",
    "경영학",
    "경제학",
    "통계학",
    "화학공학",
    "기계공학",
    "신소재공학",
    "수학",
]

ACTION_CODES_PENDING = [
    "reach_out",
    "re_reach_out",
    "schedule_pre_meet",
    "pre_meeting",
    "share_jd",
    "convert_resume",
]

ACTION_CODES_DONE = [
    "search_db",
    "reach_out",
    "receive_resume",
    "convert_resume",
    "pre_meeting",
]


class Command(BaseCommand):
    help = "디자인 테스트용 더미 데이터 시딩 (clients/projects/candidates/applications/action_items)"

    def add_arguments(self, parser):
        parser.add_argument("--org", type=str, default=None, help="대상 조직 이름")
        parser.add_argument(
            "--wipe",
            action="store_true",
            help="기존 [DUMMY] 레코드 제거 후 재생성",
        )
        parser.add_argument(
            "--candidates",
            type=int,
            default=30,
            help="생성할 후보자 수 (기본 30)",
        )
        parser.add_argument(
            "--projects",
            type=int,
            default=12,
            help="생성할 프로젝트 수 (기본 12)",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=42,
            help="random seed (기본 42)",
        )

    @transaction.atomic
    def handle(self, *args, **opts):
        random.seed(opts["seed"])

        org = self._resolve_org(opts["org"])
        self.stdout.write(f"target org: {org.name} ({org.id})")

        creator = self._resolve_creator(org)

        if opts["wipe"]:
            self._wipe(org)

        clients = self._seed_clients(org)
        candidates = self._resolve_candidates(opts["candidates"])
        projects = self._seed_projects(org, clients, creator, opts["projects"])
        self._seed_applications(projects, candidates, creator)

        self.stdout.write(self.style.SUCCESS("seed_dummy_data done"))
        self.stdout.write(
            f"  clients: {Client.objects.filter(organization=org).count()}"
        )
        self.stdout.write(
            f"  projects: {Project.objects.filter(organization=org).count()}"
        )
        self.stdout.write(f"  candidates: {Candidate.objects.count()}")
        self.stdout.write(
            "  applications: "
            f"{Application.objects.filter(project__organization=org).count()}"
        )
        self.stdout.write(
            "  action_items: "
            f"{ActionItem.objects.filter(application__project__organization=org).count()}"
        )

    # ------------------------------------------------------------------
    def _resolve_org(self, name: str | None) -> Organization:
        if name:
            try:
                return Organization.objects.get(name=name)
            except Organization.DoesNotExist as e:
                raise CommandError(f"Organization '{name}' not found") from e
        org = Organization.objects.filter(name="테스트조직").first()
        if org:
            return org
        org = Organization.objects.first()
        if org:
            return org
        raise CommandError("No Organization exists. Create one first.")

    def _resolve_creator(self, org: Organization):
        from django.contrib.auth import get_user_model

        User = get_user_model()
        m = org.memberships.filter(status="active").select_related("user").first()
        if m:
            return m.user
        return User.objects.filter(is_superuser=True).first()

    # ------------------------------------------------------------------
    def _wipe(self, org: Organization):
        self.stdout.write("wiping existing [DUMMY] records...")
        # ActionItems/Applications cascade via Project/Candidate deletion
        candidates = Candidate.objects.filter(summary__startswith=DUMMY_TAG)
        c_cnt = candidates.count()
        candidates.delete()
        projects = Project.objects.filter(organization=org, note__startswith=DUMMY_TAG)
        p_cnt = projects.count()
        projects.delete()
        clients = Client.objects.filter(organization=org, notes__startswith=DUMMY_TAG)
        cl_cnt = clients.count()
        clients.delete()
        self.stdout.write(
            f"  wiped {cl_cnt} clients / {p_cnt} projects / {c_cnt} candidates"
        )

    # ------------------------------------------------------------------
    def _seed_clients(self, org: Organization) -> list[Client]:
        created: list[Client] = []
        for name, industry, size, region in CLIENT_SEEDS:
            client, was_created = Client.objects.get_or_create(
                organization=org,
                name=name,
                defaults={
                    "industry": industry,
                    "size": size,
                    "region": region,
                    "notes": f"{DUMMY_TAG} 디자인 테스트용 더미 고객사",
                    "contact_persons": [
                        {
                            "name": "김담당",
                            "title": "인사팀장",
                            "email": f"hr@{name.lower()}.test",
                            "phone": "010-1234-5678",
                        },
                    ],
                },
            )
            created.append(client)
        self.stdout.write(f"  clients: {len(created)} ready")
        return created

    # ------------------------------------------------------------------
    def _resolve_candidates(self, sample_size: int) -> list[Candidate]:
        """Prefer real candidates from DB; only fall back to dummy generation."""
        existing = list(
            Candidate.objects.filter(status=Candidate.Status.ACTIVE).order_by("?")[
                : max(sample_size, 1)
            ]
        )
        if len(existing) >= max(sample_size // 2, 1):
            self.stdout.write(
                f"  candidates: reusing {len(existing)} real records (no dummy insert)"
            )
            return existing
        self.stdout.write(
            f"  candidates: only {len(existing)} real records found, seeding dummies"
        )
        return self._seed_candidates(sample_size)

    # ------------------------------------------------------------------
    def _seed_candidates(self, count: int) -> list[Candidate]:
        pool: list[Candidate] = []
        used_names = set(Candidate.objects.values_list("name", flat=True))
        now_year = timezone.now().year
        idx = 0
        while len(pool) < count:
            base = CANDIDATE_NAMES[idx % len(CANDIDATE_NAMES)]
            suffix = idx // len(CANDIDATE_NAMES)
            name = base if suffix == 0 else f"{base}{suffix + 1}"
            idx += 1
            if name in used_names:
                continue
            used_names.add(name)

            years_exp = random.randint(3, 22)
            start_year = now_year - years_exp
            current_company = random.choice(COMPANIES)
            current_position = random.choice(POSITIONS)
            candidate = Candidate.objects.create(
                name=name,
                email=f"cand{idx}@example.test",
                phone=f"010-{random.randint(1000, 9999)}-{random.randint(1000, 9999)}",
                birth_year=random.randint(1975, 1998),
                gender=random.choice(["남", "여"]),
                status=Candidate.Status.ACTIVE,
                source=Candidate.Source.MANUAL,
                total_experience_years=years_exp,
                current_company=current_company,
                current_position=current_position,
                current_salary=random.randint(6000, 14000),
                desired_salary=random.randint(7000, 18000),
                summary=(
                    f"{DUMMY_TAG} {years_exp}년차 {current_position}. "
                    f"{current_company} 재직 중. 디자인 테스트용 더미 데이터."
                ),
            )
            # Education
            Education.objects.create(
                candidate=candidate,
                institution=random.choice(UNIVERSITIES),
                degree="학사",
                major=random.choice(MAJORS),
                start_year=start_year - 4,
                end_year=start_year,
            )
            if random.random() < 0.4:
                Education.objects.create(
                    candidate=candidate,
                    institution=random.choice(UNIVERSITIES),
                    degree="석사",
                    major=random.choice(MAJORS),
                    start_year=start_year,
                    end_year=start_year + 2,
                )

            # Careers — 1~3개, 최신 하나는 is_current=True
            career_count = random.randint(1, 3)
            year_cursor = start_year
            for i in range(career_count):
                duration = random.randint(2, max(2, years_exp // career_count))
                is_current = i == career_count - 1
                end_year = "" if is_current else f"{year_cursor + duration}.12"
                Career.objects.create(
                    candidate=candidate,
                    company=random.choice(COMPANIES),
                    position=random.choice(POSITIONS),
                    department=random.choice(
                        ["연구개발", "플랫폼", "전략기획", "마케팅", "영업"]
                    ),
                    start_date=f"{year_cursor}.01",
                    end_date=end_year,
                    duration_text=f"{duration}년",
                    is_current=is_current,
                    duties="제품 개발/운영, 팀 리딩, 주요 이해관계자 협업",
                    achievements="서비스 성과 지표 20% 이상 개선, 팀 빌딩 성공",
                    salary=random.randint(5500, 15000),
                    order=i,
                )
                year_cursor += duration
            pool.append(candidate)
        self.stdout.write(f"  candidates: {len(pool)} created")
        return pool

    # ------------------------------------------------------------------
    def _seed_projects(
        self,
        org: Organization,
        clients: list[Client],
        creator,
        count: int,
    ) -> list[Project]:
        projects: list[Project] = []
        now = timezone.now()
        titles = random.sample(PROJECT_TITLES, min(count, len(PROJECT_TITLES)))
        for i, title in enumerate(titles):
            client = random.choice(clients)
            # 80% open, 20% closed
            is_open = random.random() < 0.8
            phase = random.choice([ProjectPhase.SEARCHING, ProjectPhase.SCREENING])
            deadline = (now + timedelta(days=random.randint(-5, 45))).date()
            project = Project.objects.create(
                client=client,
                organization=org,
                title=f"{client.name} - {title}",
                jd_text=(
                    f"{client.name} {title} 포지션.\n\n"
                    "- 요구 경력: 8년 이상\n"
                    "- 필요 역량: 리더십/커뮤니케이션/기술 전문성\n"
                    "- 보상: 업계 상위 수준\n"
                ),
                phase=phase,
                status=ProjectStatus.OPEN if is_open else ProjectStatus.CLOSED,
                deadline=deadline,
                closed_at=None
                if is_open
                else now - timedelta(days=random.randint(1, 30)),
                result="" if is_open else random.choice(["success", "fail"]),
                note=f"{DUMMY_TAG} 디자인 테스트용 더미 프로젝트",
                created_by=creator,
                requirements={
                    "min_years": random.choice([5, 8, 10, 12]),
                    "must_have": ["리더십", "기술전문성"],
                    "nice_to_have": ["글로벌 경험"],
                },
            )
            if creator is not None:
                project.assigned_consultants.add(creator)
            projects.append(project)
        self.stdout.write(f"  projects: {len(projects)} created")
        return projects

    # ------------------------------------------------------------------
    def _seed_applications(
        self,
        projects: list[Project],
        candidates: list[Candidate],
        creator,
    ) -> None:
        pending_action_types = list(
            ActionType.objects.filter(code__in=ACTION_CODES_PENDING)
        )
        done_action_types = list(ActionType.objects.filter(code__in=ACTION_CODES_DONE))
        if not pending_action_types:
            self.stdout.write(
                self.style.WARNING("  ActionType 시드 없음 — action_items 생성 건너뜀")
            )
            return

        now = timezone.now()
        app_count = 0
        item_count = 0
        for project in projects:
            # 2~5 후보자 매칭
            match_count = random.randint(2, 5)
            matched = random.sample(candidates, match_count)
            for cand in matched:
                application, created = Application.objects.get_or_create(
                    project=project,
                    candidate=cand,
                    defaults={"created_by": creator},
                )
                if not created:
                    continue
                app_count += 1

                # 각 application 당 1~2 pending + 0~2 done ActionItem
                pending_n = random.randint(1, 2)
                for _ in range(pending_n):
                    at = random.choice(pending_action_types)
                    # 분포: overdue 25%, today 25%, upcoming 50%
                    r = random.random()
                    if r < 0.25:
                        due = now - timedelta(
                            days=random.randint(1, 5),
                            hours=random.randint(0, 8),
                        )
                    elif r < 0.5:
                        due = now.replace(
                            hour=random.randint(14, 18),
                            minute=0,
                            second=0,
                            microsecond=0,
                        )
                    else:
                        due = now + timedelta(
                            days=random.randint(1, 5),
                            hours=random.randint(0, 8),
                        )
                    ActionItem.objects.create(
                        application=application,
                        action_type=at,
                        title=f"{at.label_ko} — {cand.name}",
                        channel=random.choice(
                            [
                                ActionChannel.PHONE,
                                ActionChannel.EMAIL,
                                ActionChannel.KAKAO,
                                ActionChannel.LINKEDIN,
                            ]
                        ),
                        due_at=due,
                        scheduled_at=due,
                        status=ActionItemStatus.PENDING,
                        assigned_to=creator,
                        created_by=creator,
                    )
                    item_count += 1

                done_n = random.randint(0, 2)
                for _ in range(done_n):
                    at = random.choice(done_action_types)
                    completed = now - timedelta(days=random.randint(1, 30))
                    ActionItem.objects.create(
                        application=application,
                        action_type=at,
                        title=f"{at.label_ko} — {cand.name}",
                        channel=random.choice(
                            [
                                ActionChannel.PHONE,
                                ActionChannel.EMAIL,
                                ActionChannel.KAKAO,
                            ]
                        ),
                        due_at=completed,
                        scheduled_at=completed,
                        completed_at=completed,
                        status=ActionItemStatus.DONE,
                        result="완료 처리 — 디자인 테스트용 더미",
                        assigned_to=creator,
                        created_by=creator,
                    )
                    item_count += 1
        self.stdout.write(
            f"  applications: {app_count} created, action_items: {item_count}"
        )
