import os
import sys
sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from config import CONFIG
from app.rtfeed.engine import RTEngine


def main():
    engine = RTEngine(CONFIG)
    try:
        engine.start()
        import app.web.server as web
        web.bind(engine.state, engine.store, engine.crowd, engine.consensus)
        import uvicorn
        host = os.getenv("HOST", "0.0.0.0")
        port = int(os.getenv("PORT", os.getenv("PORT", "8000")))
        uvicorn.run(web.app, host=host, port=port, log_level="info")
    finally:
        engine.stop()


if __name__ == "__main__":
    main()
