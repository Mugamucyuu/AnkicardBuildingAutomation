"""Desktop shell for the existing UI; the server is an owned child process.

No application JS bridge is exposed. Closing the window stops the worker,
including outstanding network calls. UIService recovers persisted jobs on restart.
"""
import argparse
import ctypes
from ctypes import wintypes
import json
import os
from pathlib import Path
import secrets
import subprocess
import sys
import tempfile
import threading
import time
from urllib.request import ProxyHandler, Request, build_opener

from .settings import user_data_dir

TITLE = "Ankicard Building Automation"


class SingleInstance:
    """An OS-released lock scoped to the selected user data directory."""
    def __init__(self, directory):
        self.path = Path(directory) / "desktop.lock"
        self.file = None

    def acquire(self):
        import msvcrt
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.file = self.path.open("a+b")
        if self.path.stat().st_size == 0:
            self.file.write(b"0")
            self.file.flush()
        self.file.seek(0)
        try:
            msvcrt.locking(self.file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError:
            self.file.close()
            self.file = None
            return False
        return True

    def close(self):
        if self.file:
            self.file.close()
            self.file = None


def activate_existing():
    user32 = ctypes.WinDLL("user32", use_last_error=True)
    user32.FindWindowW.argtypes = [wintypes.LPCWSTR, wintypes.LPCWSTR]
    user32.FindWindowW.restype = wintypes.HWND
    user32.ShowWindow.argtypes = [wintypes.HWND, ctypes.c_int]
    user32.SetForegroundWindow.argtypes = [wintypes.HWND]
    # Allow the first instance time to finish creating its window.
    for _ in range(50):
        handle = user32.FindWindowW(None, TITLE)
        if handle:
            user32.ShowWindow(handle, 9)  # SW_RESTORE
            user32.SetForegroundWindow(handle)
            return
        time.sleep(.1)


def watch_parent(parent_pid, stop_path):
    """Exit even if the desktop host crashes or is terminated externally."""
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
    kernel32.OpenProcess.restype = wintypes.HANDLE
    kernel32.WaitForSingleObject.argtypes = [wintypes.HANDLE, wintypes.DWORD]
    kernel32.WaitForSingleObject.restype = wintypes.DWORD
    kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
    handle = kernel32.OpenProcess(0x00100000, False, parent_pid)  # SYNCHRONIZE
    if not handle:
        os._exit(1)
    while kernel32.WaitForSingleObject(handle, 100) == 258:  # WAIT_TIMEOUT
        if stop_path.exists():
            break
    kernel32.CloseHandle(handle)
    os._exit(0)


def serve(ready_path, parent_pid):
    from http.server import ThreadingHTTPServer
    from .ui_server import make_handler
    from .ui_service import UIService
    threading.Thread(target=watch_parent, args=(parent_pid, Path(ready_path).with_suffix('.stop')), daemon=True).start()
    service = UIService()
    server = ThreadingHTTPServer(("127.0.0.1", 0), make_handler(service, secrets.token_urlsafe(32)))
    ready = Path(ready_path)
    temporary = ready.with_suffix(".tmp")
    temporary.write_text(json.dumps({"url": f"http://127.0.0.1:{server.server_port}"}), encoding="utf-8")
    temporary.replace(ready)
    try:
        server.serve_forever()
    finally:
        server.server_close()
        service.pool.shutdown(wait=False, cancel_futures=True)


class DesktopServer:
    def __init__(self, directory):
        self.directory = Path(directory)
        self.process = None
        self.temporary = None
        self.url = None

    def start(self, timeout=30):
        self.temporary = tempfile.TemporaryDirectory(prefix="desktop-", dir=self.directory)
        ready = Path(self.temporary.name) / "ready.json"
        if getattr(sys, "frozen", False):
            command = [sys.executable]
        else:
            command = [sys.executable, "-m", "vocab_app.desktop"]
        command += ["--desktop-server", str(ready), "--parent-pid", str(os.getpid())]
        env = {**os.environ, "ANKICARD_DATA_DIR": str(self.directory)}
        # A frozen app launching itself needs an independent extraction lifetime.
        env["PYINSTALLER_RESET_ENVIRONMENT"] = "1"
        self.process = subprocess.Popen(command, env=env, stdin=subprocess.DEVNULL,
                                        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                                        creationflags=subprocess.CREATE_NO_WINDOW)
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if self.process.poll() is not None:
                raise RuntimeError("The local service could not start.")
            if ready.exists():
                self.url = json.loads(ready.read_text(encoding="utf-8"))["url"]
                self.request("/api/bootstrap")
                return self.url
            time.sleep(.05)
        raise TimeoutError("The local service did not start in time.")

    def request(self, path, data=None, token=None):
        headers = {"Content-Type": "application/json", "X-Vocab-Token": token} if data is not None else {}
        request = Request(self.url + path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
        # Local IPC must not be sent through user/system HTTP proxies.
        with build_opener(ProxyHandler({})).open(request, timeout=10) as response:
            return json.load(response)

    def close(self):
        if self.process and self.process.poll() is None:
            # Signal the real worker, including when a venv redirector owns Popen.
            (Path(self.temporary.name) / 'ready.stop').touch()
            try:
                self.process.wait(timeout=3)
            except subprocess.TimeoutExpired:
                self.process.terminate()
                self.process.wait(timeout=5)
        if self.temporary:
            self.temporary.cleanup()


def smoke_check(window, server, report_path, loaded):
    """Release verification: actual renderer + bundled resources, no paid calls."""
    report = {"ok": False}
    try:
        if not loaded.wait(45):
            raise TimeoutError("Desktop page did not load")
        assert window.evaluate_js("document.title") == "Vocabulary Studio"
        assert window.evaluate_js("Boolean(document.querySelector('#import-form'))")
        bootstrap = server.request("/api/bootstrap")
        assert not any(bootstrap["credentials"].values()), "Use a clean test environment"
        assert len(bootstrap["prompts"]["stages"]) == 11
        for language, word in (("en", "apple"), ("ja", "猫"), ("ko", "나무")):
            job = server.request("/api/jobs", {"language": language, "text": word, "provider": "offline",
                                              "mode": "independent", "tag_source": "seed"}, bootstrap["token"])
            deadline = time.monotonic() + 20
            while time.monotonic() < deadline:
                saved = next(j for j in server.request("/api/jobs") if j["id"] == job["id"])
                if saved["status"] == "complete":
                    break
                time.sleep(.1)
            assert saved["items"][0]["status"] == "ready", saved["items"][0].get("error")
            preview = saved["items"][0]["preview"]
            with build_opener(ProxyHandler({})).open(server.url + preview, timeout=5) as response:
                assert word in response.read().decode("utf-8")
        report = {"ok": True, "renderer": "edgechromium", "languages": ["en", "ja", "ko"],
                  "url": server.url, "worker_pid": server.process.pid}
    except Exception as error:
        report["error"] = type(error).__name__ + ": " + str(error)
    finally:
        Path(report_path).write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding="utf-8")
        window.destroy()


def main(argv=None):
    parser = argparse.ArgumentParser(description="Ankicard desktop application")
    parser.add_argument("--desktop-server", help=argparse.SUPPRESS)
    parser.add_argument("--parent-pid", type=int, help=argparse.SUPPRESS)
    parser.add_argument("--smoke-test", type=Path, help=argparse.SUPPRESS)
    args = parser.parse_args(argv)
    if sys.platform != "win32":
        parser.error("The desktop installer currently supports Windows only; use ankicard for the browser UI.")
    if args.desktop_server:
        if not args.parent_pid:
            parser.error("Missing parent process")
        serve(args.desktop_server, args.parent_pid)
        return 0
    directory = user_data_dir()
    lock = SingleInstance(directory)
    server = DesktopServer(directory)
    try:
        if not lock.acquire():
            activate_existing()
            return 0
        import webview
        webview.settings["ALLOW_DOWNLOADS"] = True
        url = server.start()
        window = webview.create_window(TITLE, url, width=1360, height=900, min_size=(960, 640),
                                       text_select=True, hidden=bool(args.smoke_test))
        def closing():
            if args.smoke_test:
                return True
            try:
                busy = any(j["status"] in ("queued", "running") or
                           j.get("bulk_import", {}).get("status") in ("queued", "running") or
                           any(i["status"] == "importing" for i in j["items"])
                           for j in server.request("/api/jobs"))
                if busy:
                    return window.create_confirmation_dialog(TITLE,
                        "任务仍在执行，退出将停止任务。下次打开可重试。是否退出？\n"
                        "Tasks are still running. Exit and retry unfinished items next time?")
            except (OSError, ValueError):
                pass
            return True
        window.events.closing += closing
        loaded = threading.Event()
        window.events.loaded += loaded.set
        callback = (lambda: smoke_check(window, server, args.smoke_test, loaded)) if args.smoke_test else None
        webview.start(callback, gui="edgechromium", private_mode=True,
                      storage_path=str(directory / "webview"))
        if args.smoke_test:
            return 0 if json.loads(args.smoke_test.read_text(encoding="utf-8"))["ok"] else 1
        return 0
    except Exception as error:
        if args.smoke_test:
            args.smoke_test.write_text(json.dumps({"ok": False, "error": type(error).__name__}), encoding="utf-8")
        else:
            # Never include exception text: it can contain private paths or request data.
            ctypes.windll.user32.MessageBoxW(None,
                "程序无法启动。请重新运行安装包修复应用及 WebView2 组件。\n"
                "Unable to start. Run Setup again to repair the app and WebView2.\n\n" + type(error).__name__,
                TITLE, 0x10)
        return 1
    finally:
        server.close()
        lock.close()


if __name__ == "__main__":
    raise SystemExit(main())
