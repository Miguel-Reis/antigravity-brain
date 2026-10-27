import os
from web_dashboard import run_server

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 3000))
    host = os.environ.get("HOST", "0.0.0.0")
    run_server(port=port, host=host)
