#!/usr/bin/env python3
"""
Punto de entrada de LineFlow.

Uso:
    python run.py                 # abre http://127.0.0.1:8000 en el navegador
    python run.py --port 9000     # otro puerto
    python run.py --no-browser    # no abrir el navegador automáticamente
"""
from __future__ import annotations

import argparse
import sys
import threading
import webbrowser

if sys.version_info < (3, 9):
    sys.exit("LineFlow requires Python 3.9 or newer")

from lineflow import __version__  # noqa: E402
from lineflow.web import create_server  # noqa: E402


def main() -> None:
    parser = argparse.ArgumentParser(description="LineFlow · Assembly line sequencing & timing module")
    parser.add_argument("--host", default="127.0.0.1", help="Interface to bind (default 127.0.0.1)")
    parser.add_argument("--port", type=int, default=8000, help="Port (default 8000)")
    parser.add_argument("--no-browser", action="store_true", help="Do not open the browser")
    parser.add_argument("--verbose", action="store_true", help="Log every HTTP request")
    args = parser.parse_args()

    try:
        server = create_server(args.host, args.port, verbose=args.verbose)
    except OSError as exc:
        sys.exit(f"Could not start the server on {args.host}:{args.port} ({exc}). Try --port 8080")

    url = f"http://{'127.0.0.1' if args.host in ('0.0.0.0', '') else args.host}:{server.server_address[1]}"
    print(f"LineFlow {__version__} running at {url}  (Ctrl+C to stop)")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopping LineFlow…")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
