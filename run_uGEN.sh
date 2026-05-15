#!/bin/bash

REPEAT_COUNT=1
SLEEP_SECONDS=1 # 5 minutes
CSV_FILE="run_times.csv"

usage() {
  echo "Usage: $0 [--repeat N] [--sleep SECONDS]"
  echo "Defaults: --repeat 1, --sleep 1"
  exit 1
}

# Parse arguments
while [[ $# -gt 0 ]]; do
  case "$1" in
    --repeat)
      REPEAT_COUNT="$2"
      shift 2
      ;;
    --sleep)
      SLEEP_SECONDS="$2"
      shift 2
      ;;
    *)
      usage
      ;;
  esac
done

# Write CSV header if file doesn't exist
if [[ ! -f "$CSV_FILE" ]]; then
  echo "run,start_time,end_time,elapsed_seconds" > "$CSV_FILE"
fi

docker compose down 2>/dev/null || true
for ((i = 1; i <= REPEAT_COUNT; i++)); do
    START_TIME=$(date +"%Y-%m-%d %H:%M:%S")
    START_SEC=$(date +%s)
    echo "[$i/$REPEAT_COUNT] Starting run at $START_TIME"

    # Build the image first, then run container
    docker compose build 2>&1 | grep -v "no such file or directory" || true
    docker compose run --rm app 2>&1
    
    # Wait briefly after completion
    sleep 1
    

    END_TIME=$(date +"%Y-%m-%d %H:%M:%S")
    END_SEC=$(date +%s)
    ELAPSED=$((END_SEC - START_SEC))

    echo "[$i/$REPEAT_COUNT] Run complete. Execution time: ${ELAPSED} seconds."
    echo "$i,$START_TIME,$END_TIME,$ELAPSED" >> "$CSV_FILE"

    if [[ $i -lt $REPEAT_COUNT ]]; then
      echo "Sleeping for $SLEEP_SECONDS seconds..."
      sleep "$SLEEP_SECONDS"
    fi
done

echo "All $REPEAT_COUNT runs completed."