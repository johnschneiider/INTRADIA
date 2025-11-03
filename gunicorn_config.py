"""
Configuración de Gunicorn para INTRADIA
"""
import multiprocessing

# Dirección y puerto
# IMPORTANTE: Usar puerto 8002 para no interferir con predicta.com.co (8001) y appo.com.co
bind = "127.0.0.1:8002"
backlog = 2048

# Workers
workers = multiprocessing.cpu_count() * 2 + 1
worker_class = "sync"
worker_connections = 1000
timeout = 30
keepalive = 5

# Logging
accesslog = "/var/log/gunicorn/intradia_access.log"
errorlog = "/var/log/gunicorn/intradia_error.log"

# NOTA: Asegúrate de crear el directorio: sudo mkdir -p /var/log/gunicorn
loglevel = "info"
access_log_format = '%(h)s %(l)s %(u)s %(t)s "%(r)s" %(s)s %(b)s "%(f)s" "%(a)s"'

# Process naming
proc_name = "intradia"

# SSL (comentar si no se usa SSL)
# keyfile = "/path/to/keyfile"
# certfile = "/path/to/certfile"

# Reload en cambios (solo desarrollo)
reload = False

def when_ready(server):
    """Callback cuando el servidor está listo"""
    server.log.info("INTRADIA server is ready. Spawning workers")

def worker_int(worker):
    """Callback cuando un worker inicia"""
    worker.log.info("Worker spawned (pid: %s)", worker.pid)

def pre_fork(server, worker):
    """Callback antes de forkar un worker"""
    pass

def post_fork(server, worker):
    """Callback después de forkar un worker"""
    server.log.info("Worker spawned (pid: %s)", worker.pid)

def post_worker_init(worker):
    """Callback después de inicializar un worker"""
    worker.log.info("Worker initialized (pid: %s)", worker.pid)

