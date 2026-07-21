"""Tiny local viewer server for reduced OpenCUA actions.

Serves the action-overlay viewer (viewer.html) next to the project's
final_video.mp4 and final_actions_opencua.json. Byte-range requests are
supported so the <video> element can seek. Standard library only.

Usage:  python -m cursor view-actions data/<id> [--port 8899]
"""

from __future__ import annotations

import json
import re
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

_RANGE_RE = re.compile(r"bytes=(\d*)-(\d*)")


def _make_handler(project_dir: Path):
    viewer_html = (Path(__file__).parent / "viewer.html").read_bytes()
    video_path = project_dir / "final_video.mp4"
    actions_path = project_dir / "actions" / "final_actions_opencua.json"

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):  # keep the console quiet
            pass

        def do_GET(self):  # noqa: N802
            route = self.path.split("?")[0].rstrip("/") or "/"
            if route in ("/", "/index.html"):
                self._send_bytes(viewer_html, "text/html; charset=utf-8")
            elif route == "/actions":
                if not actions_path.exists():
                    self.send_error(404, f"missing {actions_path.name} — run reduce-actions first")
                    return
                self._send_bytes(actions_path.read_bytes(), "application/json")
            elif route == "/video":
                self._send_video()
            else:
                self.send_error(404)

        def _send_bytes(self, data: bytes, ctype: str):
            self.send_response(200)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(data)))
            self.end_headers()
            self.wfile.write(data)

        def _send_video(self):
            if not video_path.exists():
                self.send_error(404, "final_video.mp4 not found in project dir")
                return
            size = video_path.stat().st_size
            start, end = 0, size - 1
            status = 200
            m = _RANGE_RE.match(self.headers.get("Range", ""))
            if m and (m.group(1) or m.group(2)):
                status = 206
                if m.group(1):
                    start = int(m.group(1))
                    if m.group(2):
                        end = min(int(m.group(2)), size - 1)
                else:  # suffix range: last N bytes
                    start = max(0, size - int(m.group(2)))
                if start > end or start >= size:
                    self.send_response(416)
                    self.send_header("Content-Range", f"bytes */{size}")
                    self.end_headers()
                    return
            length = end - start + 1
            self.send_response(status)
            self.send_header("Content-Type", "video/mp4")
            self.send_header("Accept-Ranges", "bytes")
            self.send_header("Content-Length", str(length))
            if status == 206:
                self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
            self.end_headers()
            with video_path.open("rb") as f:
                f.seek(start)
                remaining = length
                while remaining > 0:
                    chunk = f.read(min(1 << 20, remaining))
                    if not chunk:
                        break
                    try:
                        self.wfile.write(chunk)
                    except (BrokenPipeError, ConnectionResetError):
                        return
                    remaining -= len(chunk)

    return Handler


def serve(project_dir: str | Path, port: int = 8899, open_browser: bool = True) -> None:
    project_dir = Path(project_dir).resolve()
    actions_path = project_dir / "actions" / "final_actions_opencua.json"
    if not actions_path.exists():
        raise FileNotFoundError(
            f"{actions_path} not found — run `python -m cursor reduce-actions {project_dir}` first")
    doc = json.loads(actions_path.read_text())
    url = f"http://127.0.0.1:{port}/"
    print(f"Viewing {doc.get('id', project_dir.name)} — "
          f"{doc['stats']['n_actions']} actions @ {url}  (Ctrl+C to stop)")
    server = ThreadingHTTPServer(("127.0.0.1", port), _make_handler(project_dir))
    if open_browser:
        import webbrowser
        webbrowser.open(url)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
