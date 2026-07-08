import os
import sys
import uvicorn

from api import app
try:
    if __name__ == "__main__":
        host = os.getenv("HOST", "0.0.0.0")
        port = int(os.getenv("PORT", "8000"))

        uvicorn.run(
            app,
            host=host,
            port=port,
            log_level="info"
        )

except Exception as e:
    print(f"Startup error: {e}")
    sys.exit(1)
