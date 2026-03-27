# synco 서버 셋업 핸드오프

**서버:** 49.247.46.171 (개발 = 운영 동일 서버)
**도메인:** https://synco.kr
**경로:** /home/work/synco
**유저:** chaconne
**배포:** Docker Stack (Swarm mode active)
**SSL:** Let's Encrypt (자동 갱신, 만료 2026-06-25)

---

## 1. 서버 환경 현황

| 항목 | 상태 |
|------|------|
| Docker | 29.2.0, Swarm active |
| Python | 3.10.12 |
| uv | 0.8.6 |
| PostgreSQL | Docker 컨테이너로 운영 |

> 개발과 운영이 같은 서버. 로컬 개발 환경 없이 서버에서 직접 작업한다.

---

## 2. 환경 변수 설정

```bash
cp .env.example .env
vi .env
```

필수 설정:
```
SECRET_KEY=<python3 -c "import secrets; print(secrets.token_hex(32))">
DATABASE_URL=postgresql+asyncpg://synco:synco@db:5432/synco
KAKAO_CLIENT_ID=<https://developers.kakao.com 에서 발급>
KAKAO_CLIENT_SECRET=<카카오 앱 설정에서 발급>
KAKAO_REDIRECT_URI=http://49.247.46.171/auth/kakao/callback
OPENAI_API_KEY=<OpenAI API 키>
```

> DB 호스트가 `localhost`가 아닌 `db` (Docker 서비스명)

### 카카오 개발자 설정
1. https://developers.kakao.com → 내 애플리케이션 → 앱 생성
2. 앱 키 → REST API 키 = `KAKAO_CLIENT_ID`
3. 제품 설정 → 카카오 로그인 → 활성화
4. Redirect URI 등록: `http://49.247.46.171/auth/kakao/callback`
5. 동의항목: 닉네임(필수), 프로필사진(선택), 이메일(선택)
6. 보안 → Client Secret 발급 → `KAKAO_CLIENT_SECRET`

---

## 3. Docker Stack 배포

### 구조
```
synco stack
├── app       — FastAPI (uvicorn)
├── db        — PostgreSQL 16
└── nginx     — Reverse proxy + static files
```

### 배포 명령
```bash
# 빌드 + 배포
sudo docker build -t synco-app .
sudo docker stack deploy -c docker-stack.yml synco

# 상태 확인
sudo docker stack services synco
sudo docker service logs synco_app -f

# 업데이트 (코드 변경 시)
sudo docker build -t synco-app .
sudo docker service update --force synco_app
```

### DB 마이그레이션
```bash
# 컨테이너 안에서 실행
sudo docker exec -it $(sudo docker ps -qf "name=synco_app") \
  alembic upgrade head

# 새 마이그레이션 생성
sudo docker exec -it $(sudo docker ps -qf "name=synco_app") \
  alembic revision --autogenerate -m "description"
```

### 개발 모드 (직접 실행)
```bash
cd /home/work/synco
source .venv/bin/activate
uvicorn app.main:app --host 0.0.0.0 --port 8000 --reload
```

> 개발 중에는 직접 실행, 안정화 후 Docker Stack으로 전환

---

## 4. 도메인 + SSL

- **도메인:** synco.kr (Gabia, 만료 2027-03-25)
- **DNS:** A레코드 `@`+`www` → 49.247.46.171 (Gabia DNS)
- **SSL:** Let's Encrypt, certbot 자동 갱신 (만료 2026-06-25)
- **Nginx:** Moa_nginx가 80/443 → synco_app:8000 프록시
  - 설정 파일: `/home/docker/nginx/nginx.conf`
  - synco_app은 Moa_net 네트워크에 연결됨
- **카카오 Redirect URI:** `https://synco.kr/auth/kakao/callback`으로 변경 필요

---

## 5. 프로젝트 구조

```
/home/work/synco/
├── app/
│   ├── api/          — 라우터 (auth, contacts, meetings 등)
│   ├── core/         — config, database, security
│   ├── models/       — SQLAlchemy 모델 (6개 테이블)
│   ├── schemas/      — Pydantic 스키마 (Week 2)
│   ├── services/     — 비즈니스 로직 (Week 2)
│   ├── static/       — PWA manifest, service worker
│   └── templates/    — Jinja2 + HTMX 템플릿
├── alembic/          — DB 마이그레이션
├── Dockerfile        — 앱 컨테이너 이미지
├── docker-stack.yml  — Docker Stack 배포 설정
├── nginx.conf        — Nginx 리버스 프록시 설정
├── .env              — 환경 변수 (git 미포함)
├── requirements.txt
└── alembic.ini
```

---

## 6. 현재 구현 상태

| 기능 | 상태 | 파일 |
|------|------|------|
| 카카오 로그인 | 완료 | app/api/auth.py |
| JWT 인증 | 완료 | app/core/security.py |
| 역할 선택 (FC/CEO) | 완료 | app/api/auth.py |
| 대시보드 | 완료 (빈 상태) | templates/pages/dashboard.html |
| 연락처 CRUD | 완료 | app/api/contacts.py |
| 미팅/일정 | 스텁 | app/api/meetings.py → Week 3 |
| 접점 기록 | 스텁 | app/api/interactions.py → Week 2 |
| AI 브리핑 | 스텁 | app/api/briefs.py → Week 3 |
| 매칭 엔진 | 스텁 | app/api/matches.py → Week 4 |

---

## 7. 다음 작업 (Week 2)

1. Dockerfile + docker-stack.yml + nginx.conf 작성
2. 연락처 상세 화면 + 편집/삭제
3. 접점 기록 CRUD (메모 입력 + 음성 입력)
4. 연락처 검색/필터
5. 접점 히스토리 타임라인
6. 대시보드에 최근 연락처 표시

---

## 빠른 시작 체크리스트

```
[ ] .env 파일 작성 (DB호스트: db)
[ ] 카카오 개발자 앱 생성 + Redirect URI 등록
[ ] Dockerfile + docker-stack.yml 작성
[ ] docker build + docker stack deploy
[ ] alembic upgrade head (컨테이너 내)
[ ] 브라우저 접속 확인 (http://49.247.46.171)
[ ] 카카오 로그인 테스트
```
