#!/bin/bash
set -e

# Start supercronic in background; if it dies, kill the container so fly.io restarts it
supercronic /app/crontab &
CRON_PID=$!

# Monitor supercronic in background — if it exits, kill uvicorn so container restarts
(wait $CRON_PID; echo "supercronic exited unexpectedly, shutting down container"; kill -TERM 1) &

exec uvicorn app.main:app --host 0.0.0.0 --port 8080
