"""Official-release updates. Download/verify first; desktop owns installation/exit."""
import hashlib
import json
import re
import shutil
import threading
from datetime import datetime, timezone
from pathlib import Path
from urllib.error import HTTPError, URLError
from urllib.parse import urlparse
from urllib.request import HTTPRedirectHandler, Request, build_opener

from . import __version__
from .data_migrations import backup_data

REPOSITORY = "Mugamucyuu/AnkicardBuildingAutomation"
RELEASES_URL = f"https://github.com/{REPOSITORY}/releases"
LATEST_API = f"https://api.github.com/repos/{REPOSITORY}/releases/latest"
MAX_INSTALLER_BYTES = 800 * 1024 * 1024


def version_tuple(value):
    if not isinstance(value, str) or not re.fullmatch(r"(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)\.(?:0|[1-9]\d*)", value):
        raise ValueError("Invalid stable release version")
    return tuple(map(int, value.split(".")))


def file_sha256(path):
    digest = hashlib.sha256()
    with Path(path).open("rb") as source:
        for chunk in iter(lambda: source.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


class SafeRedirects(HTTPRedirectHandler):
    def redirect_request(self, req, fp, code, msg, headers, newurl):
        parsed = urlparse(newurl)
        if parsed.scheme != "https" or parsed.hostname not in {
            "github.com", "api.github.com", "release-assets.githubusercontent.com",
            "objects.githubusercontent.com", "github-releases.githubusercontent.com",
        } or parsed.username or parsed.password or parsed.port not in (None, 443):
            raise ValueError("Unexpected update redirect")
        return super().redirect_request(req, fp, code, msg, headers, newurl)


def official_release(data):
    if not isinstance(data, dict) or data.get("draft") or data.get("prerelease"):
        raise ValueError("Not a stable public release")
    tag = data.get("tag_name", "")
    version = tag.removeprefix("v")
    version_tuple(version)
    if tag != "v" + version or data.get("html_url") != RELEASES_URL + "/tag/" + tag:
        raise ValueError("Unexpected release origin")
    name = f"Ankicard-{version}-windows-x64-Setup.exe"
    assets = data.get("assets", [])
    def asset(expected):
        matches = [item for item in assets if item.get("name") == expected and item.get("state") == "uploaded"]
        if len(matches) != 1:
            raise ValueError("Release assets are incomplete")
        item = matches[0]
        url = RELEASES_URL + "/download/" + tag + "/" + expected
        if item.get("browser_download_url") != url:
            raise ValueError("Unexpected release asset origin")
        return item
    installer, checksums = asset(name), asset("SHA256SUMS.txt")
    size = installer.get("size")
    if type(size) is not int or not 0 < size <= MAX_INSTALLER_BYTES:
        raise ValueError("Invalid installer size")
    digest = installer.get("digest")
    if digest is not None and not re.fullmatch(r"sha256:[0-9a-fA-F]{64}", digest):
        raise ValueError("Invalid release digest")
    return {"version": version, "name": name, "url": installer["browser_download_url"],
            "size": size, "checksums_url": checksums["browser_download_url"],
            "digest": digest[7:].lower() if digest else None, "release_url": data["html_url"]}


class UpdateManager:
    def __init__(self, directory, *, can_install=False, current_version=__version__, opener=None):
        self.directory = Path(directory)
        self.current_version = current_version
        self.can_install = can_install
        self.opener = opener or build_opener(SafeRedirects())
        self.lock = threading.RLock()
        self.thread = None
        self.cancel_event = threading.Event()
        self.release = None
        self.installer = None
        self.expected_hash = None
        self.state = {"state": "idle", "current_version": current_version, "latest_version": None,
                      "can_install": can_install, "release_url": RELEASES_URL,
                      "downloaded": 0, "total": 0, "error": None, "checked_at": None}

    def status(self):
        with self.lock:
            result = dict(self.state)
            last = self.directory / "updates/last-result.json"
            if last.is_file():
                try:
                    value = json.loads(last.read_text(encoding="utf-8-sig"))
                    if not isinstance(value, dict):
                        raise ValueError("Invalid update result")
                    result["last_result"] = {k: value.get(k) for k in ("ok", "version", "code")}
                except (OSError, ValueError):
                    pass
            return result

    def _set(self, **values):
        with self.lock:
            self.state.update(values)

    def _request(self, url):
        return self.opener.open(Request(url, headers={"User-Agent": "Ankicard/" + self.current_version,
            "Accept": "application/vnd.github+json" if url == LATEST_API else "application/octet-stream"}), timeout=30)

    def _small(self, url, limit):
        with self._request(url) as response:
            data = response.read(limit + 1)
        if len(data) > limit:
            raise ValueError("Update metadata is too large")
        return data

    def _run(self, task):
        try:
            task()
        except InterruptedError:
            self._set(state="available", error=None)
        except HTTPError as error:
            self._set(state="error", error="rate_limit" if error.code in (403, 429) else "network")
        except (URLError, TimeoutError, ConnectionError):
            self._set(state="error", error="network")
        except ValueError:
            self._set(state="error", error="verification")
        except OSError:
            self._set(state="error", error="storage")
        except Exception:
            self._set(state="error", error="update_failed")

    def _start(self, state, task):
        with self.lock:
            if self.thread and self.thread.is_alive() or self.state["state"] in ("install_requested", "installing"):
                return self.status()
            self.cancel_event.clear()
            self._set(state=state, error=None)
            self.thread = threading.Thread(target=self._run, args=(task,), daemon=True, name="ankicard-update")
            self.thread.start()
            return self.status()

    def check(self):
        return self._start("checking", self._check)

    def _check(self):
        release = official_release(json.loads(self._small(LATEST_API, 1024 * 1024)))
        available = version_tuple(release["version"]) > version_tuple(self.current_version)
        with self.lock:
            self.release = release
            self._set(latest_version=release["version"], release_url=release["release_url"],
                      checked_at=datetime.now(timezone.utc).isoformat(), total=release["size"], downloaded=0,
                      state="available" if available else "up_to_date", error=None)

    def download(self):
        with self.lock:
            if not self.can_install:
                raise ValueError("一键更新仅适用于 Windows 安装版。")
            if not self.release or version_tuple(self.release["version"]) <= version_tuple(self.current_version):
                raise ValueError("请先检查可用的新版本。")
            return self._start("downloading", self._download)

    def _download(self):
        release = dict(self.release)
        checksum_text = self._small(release["checksums_url"], 64 * 1024).decode("utf-8-sig")
        matches = re.findall(r"(?m)^([0-9a-fA-F]{64})[ \t]+\*?" + re.escape(release["name"]) + r"\r?$", checksum_text)
        if len(matches) != 1:
            raise ValueError("Missing installer checksum")
        expected = matches[0].lower()
        if release["digest"] and release["digest"] != expected:
            raise ValueError("Conflicting release checksums")
        target = self.directory / "updates" / release["version"]
        target.mkdir(parents=True, exist_ok=True)
        installer = target / release["name"]
        if installer.is_file() and installer.stat().st_size == release["size"] and file_sha256(installer) == expected:
            self.installer, self.expected_hash = installer, expected
            self._set(state="ready", downloaded=release["size"])
            return
        if shutil.disk_usage(target).free < release["size"] * 2 + 100 * 1024 * 1024:
            raise OSError("Insufficient free space")
        temporary = installer.with_suffix(".partial")
        size, digest = 0, hashlib.sha256()
        try:
            with self._request(release["url"]) as response, temporary.open("wb") as output:
                while True:
                    if self.cancel_event.is_set():
                        raise InterruptedError()
                    chunk = response.read(1024 * 1024)
                    if not chunk:
                        break
                    size += len(chunk)
                    if size > release["size"]:
                        raise ValueError("Installer size mismatch")
                    output.write(chunk)
                    digest.update(chunk)
                    self._set(downloaded=size)
            if size != release["size"] or digest.hexdigest() != expected:
                raise ValueError("Installer checksum mismatch")
            temporary.replace(installer)
        finally:
            temporary.unlink(missing_ok=True)
        self.installer, self.expected_hash = installer, expected
        self._set(state="ready", downloaded=size)

    def cancel(self):
        with self.lock:
            if self.state["state"] == "installing":
                raise ValueError("安装准备已开始，请等待完成。")
            self.cancel_event.set()
            if self.state["state"] == "install_requested":
                self._set(state="ready")
            return self.status()

    def request_install(self):
        with self.lock:
            if not self.can_install or self.state["state"] != "ready":
                raise ValueError("请先下载并校验新版本。")
            self._set(state="install_requested")
            return self.status()

    def prepare_install(self):
        with self.lock:
            if not self.can_install or self.state["state"] != "install_requested":
                raise ValueError("没有待安装的更新。")
            self._set(state="installing")
        try:
            if file_sha256(self.installer) != self.expected_hash:
                raise ValueError("安装包校验失败，请重新下载。")
            backup = backup_data(self.directory, "before-application-update", self.current_version)
            return {"installer": str(self.installer.resolve()), "sha256": self.expected_hash,
                    "version": self.release["version"], "backup": str(backup),
                    "data_directory": str(self.directory.resolve())}
        except Exception:
            self._set(state="error", error="prepare_failed")
            raise

    def install_failed(self):
        self._set(state="error", error="install_failed")
