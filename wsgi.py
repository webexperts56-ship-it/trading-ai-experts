import os
import sys
import threading

project_home = os.path.dirname(os.path.abspath(__file__))
if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.chdir(project_home)
os.makedirs(os.path.join(project_home, "data"), exist_ok=True)
os.makedirs(os.path.join(project_home, "models"), exist_ok=True)

try:
    from a2wsgi import ASGIMiddleware
except ImportError:
    import subprocess
    subprocess.check_call([sys.executable, "-m", "pip", "install", "--user", "a2wsgi"])
    from a2wsgi import ASGIMiddleware

from config import CONFIG
from app.rtfeed.engine import RTEngine
import app.web.server as web

# Initialize engine & bind web server
engine = RTEngine(CONFIG)
web.bind(engine.state, engine.store, engine.crowd, engine.consensus)

# Start background data worker
engine_thread = threading.Thread(target=engine.start, daemon=True, name="engine-worker")
engine_thread.start()

# WSGI application adapter for PythonAnywhere
application = ASGIMiddleware(web.app)
