import os
import sys
import threading
from a2wsgi import ASGIMiddleware

project_home = os.path.dirname(os.path.abspath(__file__))
if project_home not in sys.path:
    sys.path.insert(0, project_home)

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
