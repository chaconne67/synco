#!/bin/bash
# 5세션 병렬 이력서 임포트 — nohup으로 VSCode 종료해도 계속 실행
# 사용법: bash scripts/run_import_parallel.sh

set -e
cd /home/work/synco
PF="1k_VtpvJo8P8ynGTvVWS8DtYtK4gZDF_Y"
LOGDIR="/home/work/synco/logs/import"
mkdir -p "$LOGDIR"
TIMESTAMP=$(date +%Y%m%d_%H%M%S)

echo "=== 5세션 병렬 임포트 시작: $(date) ==="
echo "로그 디렉토리: $LOGDIR"

# 세션 1: Accounting, EHS, Engineer, Finance
for folder in Accounting EHS Engineer Finance; do
    nohup uv run python manage.py import_resumes --folder "$folder" --limit 0 --workers 1 --parent-folder-id $PF \
        >> "$LOGDIR/session1_${TIMESTAMP}.log" 2>&1
done &
S1=$!
echo "세션1 PID: $S1 (Accounting, EHS, Engineer, Finance)"

# 세션 2: HR, Law, Logistics, Marketing
for folder in HR Law Logistics Marketing; do
    nohup uv run python manage.py import_resumes --folder "$folder" --limit 0 --workers 1 --parent-folder-id $PF \
        >> "$LOGDIR/session2_${TIMESTAMP}.log" 2>&1
done &
S2=$!
echo "세션2 PID: $S2 (HR, Law, Logistics, Marketing)"

# 세션 3: MD, MR, Plant, PR+AD
for folder in MD MR Plant "PR+AD"; do
    nohup uv run python manage.py import_resumes --folder "$folder" --limit 0 --workers 1 --parent-folder-id $PF \
        >> "$LOGDIR/session3_${TIMESTAMP}.log" 2>&1
done &
S3=$!
echo "세션3 PID: $S3 (MD, MR, Plant, PR+AD)"

# 세션 4: Procurement, Production, Quality, R&D
for folder in Procurement Production Quality "R&D"; do
    nohup uv run python manage.py import_resumes --folder "$folder" --limit 0 --workers 1 --parent-folder-id $PF \
        >> "$LOGDIR/session4_${TIMESTAMP}.log" 2>&1
done &
S4=$!
echo "세션4 PID: $S4 (Procurement, Production, Quality, R&D)"

# 세션 5: Sales, SCM, SI+IT, VMD
for folder in Sales SCM "SI+IT" VMD; do
    nohup uv run python manage.py import_resumes --folder "$folder" --limit 0 --workers 1 --parent-folder-id $PF \
        >> "$LOGDIR/session5_${TIMESTAMP}.log" 2>&1
done &
S5=$!
echo "세션5 PID: $S5 (Sales, SCM, SI+IT, VMD)"

echo ""
echo "=== 전체 PID: $S1 $S2 $S3 $S4 $S5 ==="
echo "모니터링: tail -f $LOGDIR/session*_${TIMESTAMP}.log"
echo "진행확인: grep -c 'OK:' $LOGDIR/session*_${TIMESTAMP}.log"
echo "중지: kill $S1 $S2 $S3 $S4 $S5"

# PID 파일 저장 (나중에 중지용)
echo "$S1 $S2 $S3 $S4 $S5" > "$LOGDIR/pids_${TIMESTAMP}.txt"

wait $S1 $S2 $S3 $S4 $S5
echo "=== 전체 완료: $(date) ==="
