"""
Gunicorn configuration file
"""
import json
import multiprocessing
import os

# Server socket
bind = f"0.0.0.0:{os.getenv('PORT', '8000')}"
backlog = 2048

# Worker processes
core_workers = multiprocessing.cpu_count()
workers = int(os.getenv('GUNICORN_WORKERS', core_workers))
worker_class = 'uvicorn.workers.UvicornWorker'
worker_connections = 1000
timeout = 120
keepalive = 15

# Logging
accesslog = '-'
errorlog = '-'
loglevel = os.getenv('LOG_LEVEL', 'info')
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s" %(D)s'

# Process naming
proc_name = 'rooted-core-api'

# Server mechanics
daemon = False
pidfile = None
umask = 0
user = None
group = None
tmp_upload_dir = None

# Worker timeout and graceful shutdown
graceful_timeout = 150
preload_app = True
if os.path.isdir("/dev/shm"):
    worker_tmp_dir = "/dev/shm"  # nosec

# Max requests per worker to prevent memory leaks
max_requests = 100000
max_requests_jitter = 2000

# SSL (uncomment if using HTTPS)
# keyfile = None
# certfile = None

# Performance tuning
limit_request_line = 4094
limit_request_fields = 100
limit_request_field_size = 8190

# For debugging and testing
log_data = {
    "loglevel": loglevel,
    "workers": workers,
    "bind": bind,
    "graceful_timeout": graceful_timeout,
    "timeout": timeout,
    "keepalive": keepalive,
    "errorlog": errorlog,
    "accesslog": accesslog,
    # Additional, non-gunicorn variables
    "workers_per_core": workers
}
print(json.dumps(log_data))


def post_fork(server, worker):
    server.log.info("Worker spawned (pid: %s)", worker.pid)
