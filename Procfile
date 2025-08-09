web: gunicorn app:app --bind 0.0.0.0:$PORT --workers 1 --timeout 300 --worker-class sync --max-requests 100 --max-requests-jitter 10 --preload
worker: python auto_monitor.py