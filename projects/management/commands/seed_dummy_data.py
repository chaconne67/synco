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
from decimal import Decimal

from django.core.management.base import BaseCommand
from django.db import transaction
from django.utils import timezone

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

# (title keyword → 연봉 범위 원 단위, 태그 키워드 3종)
# 포지션 레벨에 따른 연봉/수수료율 차등
PROJECT_COMPENSATION = {
    "CTO 후보":           {"salary": 250_000_000, "fee": "25.00", "keywords": ["기술전략", "CTO 15Y+", "조직 빌딩"]},
    "전략기획 임원":      {"salary": 200_000_000, "fee": "25.00", "keywords": ["M&A", "IR", "CXO 경력"]},
    "재무회계 이사":      {"salary": 180_000_000, "fee": "22.00", "keywords": ["IPO 준비", "CFO 경력", "15Y+"]},
    "마케팅 총괄":        {"salary": 170_000_000, "fee": "22.00", "keywords": ["B2C", "CMO", "D2C"]},
    "법무 실장":          {"salary": 160_000_000, "fee": "22.00", "keywords": ["변호사", "컴플라이언스", "12Y+"]},
    "글로벌 세일즈 디렉터": {"salary": 180_000_000, "fee": "22.00", "keywords": ["영문 비즈니스", "B2B", "APAC"]},
    "HR 팀장":            {"salary": 130_000_000, "fee": "20.00", "keywords": ["HRBP", "채용 설계", "10Y+"]},
    "UX 디자인 리드":     {"salary": 140_000_000, "fee": "20.00", "keywords": ["디자인 시스템", "모바일", "15Y+"]},
    "프로덕트 매니저":    {"salary": 130_000_000, "fee": "20.00", "keywords": ["PMF", "B2C 앱", "그로스"]},
    "백엔드 리드":        {"salary": 150_000_000, "fee": "20.00", "keywords": ["분산시스템", "Java/Kotlin", "100만 MAU+"]},
    "시니어 프론트엔드 개발자": {"salary": 120_000_000, "fee": "20.00", "keywords": ["React", "TypeScript", "10Y+"]},
    "AI/ML 엔지니어":     {"salary": 160_000_000, "fee": "22.00", "keywords": ["LLM", "PyTorch", "논문 5편+"]},
    "데이터 사이언티스트": {"salary": 140_000_000, "fee": "20.00", "keywords": ["ML Ops", "A/B 테스트", "SQL"]},
    "SRE/인프라 엔지니어": {"salary": 140_000_000, "fee": "20.00", "keywords": ["k8s", "IaC", "관제"]},
    "반도체 공정 엔지니어": {"salary": 130_000_000, "fee": "20.00", "keywords": ["EUV", "수율", "파운드리"]},
}
DEFAULT_COMP = {"salary": 120_000_000, "fee": "20.00", "keywords": ["리더십", "기술전문성", "글로벌 경험"]}

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

        creator = self._resolve_creator()

        if opts["wipe"]:
            self._wipe()

        clients = self._seed_clients()
        candidates = self._resolve_candidates(opts["candidates"])
        projects = self._seed_projects(clients, creator, opts["projects"])
        self._seed_applications(projects, candidates, creator)

        self.stdout.write(self.style.SUCCESS("seed_dummy_data done"))
        self.stdout.write(f"  clients: {Client.objects.count()}")
        self.stdout.write(f"  projects: {Project.objects.count()}")
        self.stdout.write(f"  candidates: {Candidate.objects.count()}")
        self.stdout.write(
            "  applications: "
            f"{Application.objects.count()}"
        )
        self.stdout.write(
            "  action_items: "
            f"{ActionItem.objects.count()}"
        )

    def _resolve_creator(self):
        """Return a level>=2 (boss) user for dummy data attribution."""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        # Prefer boss-level user
        creator = User.objects.filter(level__gte=2, is_active=True).first()
        if creator:
            return creator
        # Fall back to superuser
        creator = User.objects.filter(is_superuser=True).first()
        if creator:
            return creator
        # Last resort: any active user
        return User.objects.filter(is_active=True).first()

    # ------------------------------------------------------------------
    def _wipe(self):
        self.stdout.write("wiping existing [DUMMY] records...")
        # ActionItems/Applications cascade via Project/Candidate deletion
        candidates = Candidate.objects.filter(summary__startswith=DUMMY_TAG)
        c_cnt = candidates.count()
        candidates.delete()
        projects = Project.objects.filter(note__startswith=DUMMY_TAG)
        p_cnt = projects.count()
        projects.delete()
        clients = Client.objects.filter(notes__startswith=DUMMY_TAG)
        cl_cnt = clients.count()
        clients.delete()
        self.stdout.write(
            f"  wiped {cl_cnt} clients / {p_cnt} projects / {c_cnt} candidates"
        )

    # ------------------------------------------------------------------
    def _seed_clients(self) -> list[Client]:
        created: list[Client] = []
        for name, industry, size, region in CLIENT_SEEDS:
            client, was_created = Client.objects.get_or_create(
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
        clients: list[Client],
        creator,
        count: int,
    ) -> list[Project]:
        projects: list[Project] = []
        now = timezone.now()
        titles = random.sample(PROJECT_TITLES, min(count, len(PROJECT_TITLES)))
        # 강제 분포: 진행중(서칭) 45%, 심사중 30%, 완료(성공) 25%
        n_total = len(titles)
        n_searching = max(int(n_total * 0.45), 1)
        n_screening = max(int(n_total * 0.30), 1)
        n_closed = n_total - n_searching - n_screening
        intents = (
            ["searching"] * n_searching
            + ["screening"] * n_screening
            + ["closed"] * n_closed
        )
        random.shuffle(intents)

        for i, title in enumerate(titles):
            client = random.choice(clients)
            intent = intents[i]
            deadline = (now + timedelta(days=random.randint(-5, 45))).date()

            comp = PROJECT_COMPENSATION.get(title, DEFAULT_COMP)
            salary_base = comp["salary"]
            salary = int(salary_base * random.uniform(0.85, 1.15))
            salary = (salary // 1_000_000) * 1_000_000

            # 모두 기본 상태(phase=searching, status=open)로 생성.
            # 승격은 _seed_applications 에서 submit_to_client DONE / hire 로 유도 → 시그널이 반영
            project = Project.objects.create(
                client=client,
                title=title,
                jd_text=(
                    f"{client.name} {title} 포지션.\n\n"
                    "- 요구 경력: 8년 이상\n"
                    "- 필요 역량: 리더십/커뮤니케이션/기술 전문성\n"
                    "- 보상: 업계 상위 수준\n"
                ),
                phase=ProjectPhase.SEARCHING,
                status=ProjectStatus.OPEN,
                deadline=deadline,
                annual_salary=salary,
                fee_percent=Decimal(comp["fee"]),
                note=f"{DUMMY_TAG} 디자인 테스트용 더미 프로젝트",
                created_by=creator,
                requirements={
                    "min_years": random.choice([5, 8, 10, 12]),
                    "keywords": comp["keywords"],
                    "must_have": comp["keywords"][:2],
                    "nice_to_have": ["글로벌 경험"],
                },
            )
            if creator is not None:
                project.assigned_consultants.add(creator)
            # 인텐트 저장 (승격용)
            project._seed_intent = intent
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

        submit_at = ActionType.objects.filter(code="submit_to_client").first()

        now = timezone.now()
        app_count = 0
        item_count = 0
        for project in projects:
            intent = getattr(project, "_seed_intent", "searching")
            # 2~5 후보자 매칭
            match_count = random.randint(2, 5)
            matched = random.sample(candidates, match_count)
            created_apps: list[Application] = []
            for idx, cand in enumerate(matched):
                application, created = Application.objects.get_or_create(
                    project=project,
                    candidate=cand,
                    defaults={"created_by": creator},
                )
                if not created:
                    continue
                app_count += 1
                created_apps.append(application)

                # 각 application 당 1~2 pending + 0~2 done ActionItem
                # random.sample 로 중복 ActionType 방지 (같은 ActionType이 2번 생성되지 않도록)
                pending_n = min(random.randint(1, 2), len(pending_action_types))
                pending_picks = random.sample(pending_action_types, pending_n)
                for at in pending_picks:
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

                done_n = min(random.randint(0, 2), len(done_action_types))
                done_picks = random.sample(done_action_types, done_n) if done_n else []
                for at in done_picks:
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

            # ── 인텐트 승격 ──────────────────────────────────────────────────
            # screening / closed 는 submit_to_client DONE 으로 phase 승격
            if intent in ("screening", "closed") and created_apps and submit_at:
                target = created_apps[0]
                submit_completed = now - timedelta(days=random.randint(3, 14))
                ActionItem.objects.create(
                    application=target,
                    action_type=submit_at,
                    title=f"클라이언트 제출 — {target.candidate.name}",
                    channel=ActionChannel.EMAIL,
                    due_at=submit_completed,
                    scheduled_at=submit_completed,
                    completed_at=submit_completed,
                    status=ActionItemStatus.DONE,
                    result="제출 완료 (더미)",
                    assigned_to=creator,
                    created_by=creator,
                )
                item_count += 1

            # closed: 먼저 프로젝트를 닫고(phase 고정), 그 다음 hired_at 세팅
            if intent == "closed" and created_apps:
                hire_date = now - timedelta(days=random.randint(1, 45))
                # 1) project close (signal 우회 — status/result/closed_at 동시 세팅)
                Project.objects.filter(pk=project.pk).update(
                    closed_at=hire_date,
                    result="success",
                    status=ProjectStatus.CLOSED,
                )
                # 2) 첫 application hire + 나머지 drop (update 로 시그널 영향 최소화)
                hired_app = created_apps[0]
                Application.objects.filter(pk=hired_app.pk).update(hired_at=hire_date)
                Application.objects.filter(
                    project=project, hired_at__isnull=True, dropped_at__isnull=True
                ).update(
                    dropped_at=hire_date,
                    drop_reason="other",
                    drop_note=f"입사자({hired_app.candidate.name}) 확정으로 포지션 마감",
                )

        self.stdout.write(
            f"  applications: {app_count} created, action_items: {item_count}"
        )
