#!/bin/bash
set -e

echo "🚀 Starting Indian Food Calorie Tracker..."

# Start FastAPI backend in background
echo "📡 Starting FastAPI backend on port 8000..."
python -m uvicorn main:app --host 0.0.0.0 --port 8000 &
BACKEND_PID=$!

# Wait for backend to start
sleep 3

# Start Streamlit frontend
echo "🎨 Starting Streamlit frontend on port 8501..."
python -m streamlit run app_frontend.py --server.port=8501 --server.address=0.0.0.0

# If we get here, Streamlit crashed. Kill backend and exit.
kill $BACKEND_PID 2>/dev/null || true
exit 1