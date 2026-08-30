import asyncio
import io
import os
import sys
import threading

project_home = os.path.dirname(os.path.abspath(__file__))
if project_home not in sys.path:
    sys.path.insert(0, project_home)

os.chdir(project_home)
os.makedirs(os.path.join(project_home, "data"), exist_ok=True)
os.makedirs(os.path.join(project_home, "models"), exist_ok=True)

from config import CONFIG
from app.rtfeed.engine import RTEngine
import app.web.server as web

# Initialize engine & bind web server
engine = RTEngine(CONFIG)
web.bind(engine.state, engine.store, engine.crowd, engine.consensus)

# Start background data worker
engine_thread = threading.Thread(target=engine.start, daemon=True, name="engine-worker")
engine_thread.start()

# Pure built-in zero-dependency ASGI to WSGI Bridge
class PureASGItoWSGI:
    def __init__(self, asgi_app):
        self.asgi_app = asgi_app

    def __call__(self, environ, start_response):
        status_code = [200]
        headers = []
        body = []

        path = environ.get("PATH_INFO", "/") or "/"
        query_string = environ.get("QUERY_STRING", "").encode("utf-8")
        method = environ.get("REQUEST_METHOD", "GET")
        headers_list = []
        for k, v in environ.items():
            if k.startswith("HTTP_"):
                headers_list.append((k[5:].lower().replace("_", "-").encode("utf-8"), v.encode("utf-8")))
            elif k in ("CONTENT_TYPE", "CONTENT_LENGTH") and v:
                headers_list.append((k.lower().replace("_", "-").encode("utf-8"), v.encode("utf-8")))

        scope = {
            "type": "http",
            "http_version": "1.1",
            "method": method,
            "path": path,
            "raw_path": path.encode("utf-8"),
            "query_string": query_string,
            "headers": headers_list,
            "scheme": environ.get("wsgi.url_scheme", "http"),
            "server": (environ.get("SERVER_NAME", "localhost"), int(environ.get("SERVER_PORT", 80))),
        }

        input_stream = environ.get("wsgi.input")
        input_body = b""
        if input_stream:
            try:
                length = int(environ.get("CONTENT_LENGTH", 0))
                input_body = input_stream.read(length) if length > 0 else b""
            except Exception:
                input_body = b""

        async def receive():
            return {
                "type": "http.request",
                "body": input_body,
                "more_body": False,
            }

        async def send(message):
            if message["type"] == "http.response.start":
                status_code[0] = message["status"]
                for k, v in message.get("headers", []):
                    headers.append((k.decode("latin1"), v.decode("latin1")))
            elif message["type"] == "http.response.body":
                body.append(message.get("body", b""))

        loop = asyncio.new_event_loop()
        asyncio.set_event_loop(loop)
        try:
            loop.run_until_complete(self.asgi_app(scope, receive, send))
        finally:
            loop.close()

        status_text = f"{status_code[0]} OK"
        start_response(status_text, headers)
        return body

try:
    from a2wsgi import ASGIMiddleware
    application = ASGIMiddleware(web.app)
except Exception:
    application = PureASGItoWSGI(web.app)
