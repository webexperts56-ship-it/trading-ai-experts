import os
import threading
from config import CONFIG
from app.rtfeed.engine import RTEngine
import app.web.server as web

# Initialize engine & bind web server
engine = RTEngine(CONFIG)
web.bind(engine.state, engine.store, engine.crowd, engine.consensus)

# Start background market data loop
engine_thread = threading.Thread(target=engine.start, daemon=True, name="engine-worker")
engine_thread.start()

app = web.app

if __name__ == "__main__":
    import uvicorn
    port = int(os.getenv("PORT", 7860))
    print(f"Starting Trading AI Experts on port {port}...")
    uvicorn.run(app, host="0.0.0.0", port=port)
