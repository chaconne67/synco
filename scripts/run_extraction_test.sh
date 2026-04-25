#!/usr/bin/env bash
# 100건 데이터 추출 테스트: 리얼타임 vs 배치 (시간/비용/품질)
#
# Usage:
#   nohup bash scripts/run_extraction_test.sh > logs/extraction-test/main.log 2>&1 &
#   disown
#
# 진행 상황 확인:
#   tail -f logs/extraction-test/main.log
#   tail -f logs/extraction-test/realtime.log
#   tail -f logs/extraction-test/batch.log
#
# 완료 후 결과:
#   cat snapshots/comparison.md

set -euo pipefail

# ---- 설정 ----
DRIVE_ID="${DRIVE_ID:-1k_VtpvJo8P8ynGTvVWS8DtYtK4gZDF_Y}"
LIMIT="${LIMIT:-100}"
WORKERS_REALTIME="${WORKERS_REALTIME:-1}"
LOG_DIR="logs/extraction-test"
SNAP_DIR="snapshots"

mkdir -p "$LOG_DIR" "$SNAP_DIR"

# Python unbuffered 필수 (백그라운드 로그 즉시 flush)
export PYTHONUNBUFFERED=1

main_log="$LOG_DIR/main.log"
echo "=== Extraction test started: $(date '+%F %T') ===" | tee -a "$main_log"
echo "Drive folder: $DRIVE_ID" | tee -a "$main_log"
echo "Limit: $LIMIT, realtime workers: $WORKERS_REALTIME (순차)" | tee -a "$main_log"
echo "" | tee -a "$main_log"

# ---- Phase 1: Realtime (integrity, workers=1) ----
SINCE_RT=$(date '+%Y-%m-%dT%H:%M:%S')
echo "[$(date '+%T')] Phase 1: Realtime extract since=$SINCE_RT" | tee -a "$main_log"

uv run python manage.py extract \
  --drive "$DRIVE_ID" \
  --workers "$WORKERS_REALTIME" \
  --integrity \
  --limit "$LIMIT" \
  --token-usage-output "$SNAP_DIR/realtime_tokens.json" \
  >> "$LOG_DIR/realtime.log" 2>&1

echo "[$(date '+%T')] Realtime extract done" | tee -a "$main_log"

uv run python manage.py extraction_snapshot \
  --since "$SINCE_RT" \
  --label realtime \
  --output "$SNAP_DIR/realtime.json" \
  >> "$main_log" 2>&1

echo "[$(date '+%T')] Realtime snapshot saved" | tee -a "$main_log"
echo "" | tee -a "$main_log"

# ---- Phase 2: Batch (integrity, force로 같은 100건 재처리) ----
SINCE_BATCH=$(date '+%Y-%m-%dT%H:%M:%S')
echo "[$(date '+%T')] Phase 2: Batch extract since=$SINCE_BATCH (force)" | tee -a "$main_log"

uv run python manage.py extract \
  --drive "$DRIVE_ID" \
  --batch \
  --integrity \
  --limit "$LIMIT" \
  --force \
  --token-usage-output "$SNAP_DIR/batch_tokens.json" \
  >> "$LOG_DIR/batch.log" 2>&1

echo "[$(date '+%T')] Batch extract done" | tee -a "$main_log"

uv run python manage.py extraction_snapshot \
  --since "$SINCE_BATCH" \
  --label batch \
  --output "$SNAP_DIR/batch.json" \
  >> "$main_log" 2>&1

echo "[$(date '+%T')] Batch snapshot saved" | tee -a "$main_log"
echo "" | tee -a "$main_log"

# ---- Phase 3: Compare ----
echo "[$(date '+%T')] Phase 3: Compare" | tee -a "$main_log"

uv run python manage.py extraction_compare \
  --realtime "$SNAP_DIR/realtime.json" \
  --batch "$SNAP_DIR/batch.json" \
  --realtime-tokens "$SNAP_DIR/realtime_tokens.json" \
  --batch-tokens "$SNAP_DIR/batch_tokens.json" \
  --output "$SNAP_DIR/comparison.md" \
  >> "$main_log" 2>&1

echo "[$(date '+%T')] === All done ===" | tee -a "$main_log"
echo "Report: $SNAP_DIR/comparison.md" | tee -a "$main_log"
