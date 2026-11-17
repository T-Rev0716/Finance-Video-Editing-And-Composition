"""Video Prep Studio - start with:  python app.py"""
from __future__ import annotations

import argparse
import socket
import sys
import threading
import webbrowser


def _free_port(preferred: int) -> int:
    for port in range(preferred, preferred + 20):
        with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
            try:
                sock.bind(("127.0.0.1", port))
                return port
            except OSError:
                continue
    return preferred


def main() -> None:
    parser = argparse.ArgumentParser(description="Video Prep Studio")
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-browser", action="store_true", help="do not open the browser automatically")
    args = parser.parse_args()

    try:
        import uvicorn
    except ImportError:
        sys.exit("Missing packages. Run:  pip install -r requirements.txt")

    port = _free_port(args.port)
    url = f"http://127.0.0.1:{port}"
    print(f"\n  Video Prep Studio is running at {url}\n  Press Ctrl+C to stop.\n")
    if not args.no_browser:
        threading.Timer(1.5, lambda: webbrowser.open(url)).start()
    # 127.0.0.1 only: the app and your API keys are not reachable from other machines.
    uvicorn.run("vps.server:app", host="127.0.0.1", port=port, log_level="warning")


if __name__ == "__main__":
    main()
