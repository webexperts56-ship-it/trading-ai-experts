from config import CONFIG
from app.rtfeed.engine import RTEngine


def main():
    engine = RTEngine(CONFIG)
    try:
        engine.start()
        import app.web.server as web
        web.bind(engine.state, engine.store, engine.crowd, engine.consensus)
        url = "http://{}:{}".format(CONFIG.host, CONFIG.port)
        print("=" * 60)
        print(" Trading AI Experts - Real-time Signal System")
        print(" Dashboard: {}".format(url))
        print("=" * 60)
        import uvicorn
        uvicorn.run(web.app, host=CONFIG.host, port=CONFIG.port, log_level="info")
    finally:
        engine.stop()


if __name__ == "__main__":
    main()
