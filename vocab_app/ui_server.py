"""Start the local web UI: python run_ui.py [--port 8877] [--no-browser]."""
import argparse
import json
import mimetypes
import secrets
import threading
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import urlparse, parse_qs, unquote
from vocab_app.settings import PACKAGE_ROOT
from vocab_app.ui_service import UIService, parse_words


def make_handler(service, token):
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *_):
            pass  # Never log payloads, keys, query strings, or source text.

        def respond(self, value, status=200, content_type="application/json; charset=utf-8"):
            body = json.dumps(value, ensure_ascii=False).encode() if not isinstance(value, bytes) else value
            self.send_response(status)
            self.send_header("Content-Type", content_type)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.send_header("X-Content-Type-Options", "nosniff")
            self.send_header("Referrer-Policy", "no-referrer")
            self.send_header("Content-Security-Policy", "default-src 'self'; script-src 'self'; style-src 'self' 'unsafe-inline'; img-src 'self' data:; media-src 'self'; frame-src 'self'; frame-ancestors 'self'; object-src 'none'; base-uri 'none'")
            self.end_headers()
            self.wfile.write(body)

        def trusted(self):
            expected = f"127.0.0.1:{self.server.server_port}"
            if self.headers.get("Host") != expected:
                self.respond({"error": "Invalid host"}, 403)
                return False
            origin = self.headers.get("Origin")
            if origin and origin != "http://" + expected:
                self.respond({"error": "Invalid origin"}, 403)
                return False
            return True

        def do_GET(self):
            if not self.trusted():
                return
            parsed = urlparse(self.path)
            path = unquote(parsed.path)
            query = parse_qs(parsed.query)
            try:
                if path == "/api/bootstrap":
                    return self.respond({**service.bootstrap(), "token": token})
                if path == "/api/connection":
                    return self.respond(service.connection())
                if path == "/api/tags":
                    return self.respond(service.tags(query.get("seed") == ["1"]))
                if path == "/api/jobs":
                    return self.respond(service.list_jobs())
                if path == "/api/vocabulary":
                    return self.respond(service.vocabulary(query.get("name", [""])[0]))
                if path == "/api/prompt":
                    return self.respond({"text": service.prompts.read(query.get("id", [""])[0], query.get("type", [None])[0])})
                if path.startswith("/preview/"):
                    relative = path.removeprefix("/preview/")
                    parts = relative.split("/")
                    if len(parts) not in (2, 3) or parts[0] not in service.jobs:
                        raise FileNotFoundError()
                    root = (service.directory / "jobs" / parts[0]).resolve()
                    target = (root / "/".join(parts[1:])).resolve()
                    permitted = (len(parts) == 2 and parts[1].removesuffix(".html").isdigit() and target.suffix == ".html") or (len(parts) == 3 and parts[1] == "media" and target.suffix in (".mp3", ".ogg", ".wav", ".jpg", ".jpeg", ".png", ".webp"))
                    if not permitted or not target.is_relative_to(root):
                        raise FileNotFoundError()
                else:
                    name = {"/": "index.html", "/app.js": "app.js", "/style.css": "style.css"}.get(path)
                    if not name:
                        raise FileNotFoundError()
                    target = PACKAGE_ROOT / "web" / name
                return self.respond(target.read_bytes(), content_type=mimetypes.guess_type(target.name)[0] or "application/octet-stream")
            except FileNotFoundError:
                self.respond({"error": "Not found"}, 404)
            except (ValueError, RuntimeError, OSError, KeyError):
                self.respond({"error": "读取失败；请检查 AnkiConnect 或文件配置。", "code": "read_failed"}, 400)

        def do_POST(self):
            if not self.trusted():
                return
            if self.headers.get("X-Vocab-Token") != token or self.headers.get("Content-Type", "").split(";")[0] != "application/json":
                return self.respond({"error": "Invalid request token"}, 403)
            try:
                length = int(self.headers.get("Content-Length", 0))
                if length <= 0 or length > 1_000_000:
                    raise ValueError("请求体大小无效。")
                data = json.loads(self.rfile.read(length))
                if not isinstance(data, dict):
                    raise ValueError("请求必须是 JSON 对象。")
                path = urlparse(self.path).path
                if path == "/api/settings":
                    result = service.update_settings(data)
                elif path == "/api/parse":
                    result = {"words": parse_words(data.get("text", ""))}
                elif path == "/api/prompts/upload":
                    with service.prompts.lock:
                        result = {"id": service.prompts.upload(data.get("name"), data.get("text"), data.get("type", "supplement")), "manifest": service.prompts.manifest()}
                elif path == "/api/prompts/bind":
                    with service.prompts.lock:
                        service.prompts.bind(data.get("stage"), data.get("file"))
                        result = service.prompts.manifest()
                elif path == "/api/browse":
                    result = service.browse(data.get("tags"), data.get("match", "all"))
                elif path == "/api/jobs":
                    result = service.create_job(data)
                elif path == "/api/jobs/cancel":
                    service.cancel(data["id"])
                    result = {"ok": True}
                elif path == "/api/jobs/retry":
                    service.retry(data["id"])
                    result = {"ok": True}
                elif path == "/api/jobs/import":
                    result = service.import_item(data["id"], int(data["index"]), data.get("deck"))
                elif path == "/api/jobs/reject-proposals":
                    service.reject_proposals(data["id"], int(data["index"]))
                    result = {"ok": True}
                elif path == "/api/jobs/approve-proposals":
                    result = service.approve_proposals(data["id"], int(data["index"]), data.get("deck"))
                else:
                    return self.respond({"error": "Not found"}, 404)
                self.respond(result)
            except (ValueError, KeyError, TypeError, IndexError, FileNotFoundError) as error:
                self.respond({"error": str(error)}, 400)
            except (RuntimeError, OSError):
                self.respond({"error": "操作失败；请检查 AnkiConnect、网络或文件权限。", "code": "operation_failed"}, 400)
    return Handler


def main():
    parser = argparse.ArgumentParser(description="本地词汇导入界面")
    parser.add_argument("--port", type=int, default=8877)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args()
    service = UIService()
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(service, secrets.token_urlsafe(32)))
    url = f"http://127.0.0.1:{server.server_port}"
    print("Vocabulary Studio: " + url, flush=True)
    if not args.no_browser:
        threading.Timer(.5, webbrowser.open, args=(url,)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
        service.pool.shutdown(wait=False, cancel_futures=True)


if __name__ == "__main__":
    main()
