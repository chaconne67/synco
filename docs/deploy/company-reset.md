# 운영 DB 초기화 + 슈퍼유저 시드

Single-tenant 리팩터 이후 최초 배포 시 1회 실행.

## 사전 조건

- 코드가 `main` 기준이며 Organization/Membership 이 제거되고 새 `0001_initial.py` 마이그레이션만 남아 있어야 한다.
- `.env.prod` 에 `SYNCO_SUPERUSER_EMAIL=chaconne67@gmail.com` 존재.

## 절차

1. 운영 DB 백업 (선택):
   ```bash
   ssh chaconne@49.247.45.243 \
     "docker exec synco-pg pg_dump -U synco synco > /tmp/synco-preresfresh.sql"
   ```

2. 운영 DB drop + recreate:
   ```bash
   ssh chaconne@49.247.45.243 \
     "docker exec synco-pg psql -U postgres -c 'DROP DATABASE synco;'"
   ssh chaconne@49.247.45.243 \
     "docker exec synco-pg psql -U postgres -c 'CREATE DATABASE synco OWNER synco;'"
   ```

3. 배포 (deploy.sh 가 마이그레이션 자동 실행):
   ```bash
   ./deploy.sh
   ```

4. Superuser 시드:
   ```bash
   ssh chaconne@49.247.46.171 \
     "docker exec \$(docker ps -qf name=synco_web) python manage.py seed_superuser"
   ```

5. 확인:
   - chaconne67@gmail.com 으로 카카오 로그인 → 대시보드 진입
   - `/admin` 접근 가능 (is_superuser=True)

## 차후: 두 번째 회사 배포

`deploy.sh --company=B` 구현 시점에 본 문서를 회사별 절차로 확장.
