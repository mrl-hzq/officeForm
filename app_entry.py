import os

from app import create_app

app = create_app()

if __name__ == "__main__":
    host = os.environ.get("APP_HOST", "127.0.0.1")
    port = int(os.environ.get("APP_PORT", 3000))
    app.run(host=host, port=port, debug=False, threaded=False)
