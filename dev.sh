#!/bin/bash
# Start Tailwind CSS watch + Django dev server

# Kill background processes on exit
cleanup() {
  echo "Stopping Tailwind watch..."
  kill $TAILWIND_PID 2>/dev/null
  exit 0
}
trap cleanup SIGINT SIGTERM

# Start Tailwind CSS watch
echo "Starting Tailwind CSS watch..."
npx tailwindcss -i ./static/css/input.css -o ./static/css/output.css --watch &
TAILWIND_PID=$!

# Start Django dev server
echo "Starting Django dev server on :8000..."
uv run python manage.py runserver 0.0.0.0:8000

# If Django exits, clean up Tailwind
cleanup
