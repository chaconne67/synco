#!/bin/bash
set -e
cd /home/work/synco

echo "=== Build ==="
sudo docker build -t synco-app:latest .

echo "=== Deploy ==="
sudo docker service update --force synco_app 2>&1 | tail -1

echo "=== Verify ==="
sleep 3
STATUS=$(curl -s -o /dev/null -w "%{http_code}" http://localhost:8000/)
if [ "$STATUS" = "200" ]; then
    echo "OK ($STATUS) — https://synco.kr"
else
    echo "FAIL ($STATUS)"
    sudo docker service logs synco_app --tail 15 --no-task-ids 2>&1 | grep -i "error\|Error\|Traceback" | tail -5
fi
