"""Verify real update download/backup/helper/installer/relaunch using a local release fixture."""
import argparse
import io
import json
import os
from pathlib import Path
import subprocess
import sys
import time
from zipfile import ZipFile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
from vocab_app import __version__
from vocab_app.desktop_updates import launch_update
from vocab_app.updates import UpdateManager, file_sha256, LATEST_API, RELEASES_URL


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("installer", type=Path)
    parser.add_argument("executable", type=Path)
    parser.add_argument("--state-directory", type=Path, required=True)
    args = parser.parse_args()
    installer, executable, state = args.installer.resolve(), args.executable.resolve(), args.state_directory.resolve()
    for variable in ("DEEPSEEK_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_SEARCH_API_KEY", "PYTHONPATH", "PYTHONHOME"):
        os.environ.pop(variable, None)
    os.environ["ANKICARD_DISABLE_UPDATE_CHECK"] = "1"
    name, digest = installer.name, file_sha256(installer)
    base = RELEASES_URL + "/download/v" + __version__ + "/"
    release = {"tag_name": "v" + __version__, "html_url": RELEASES_URL + "/tag/v" + __version__,
               "draft": False, "prerelease": False, "assets": [
        {"name": name, "state": "uploaded", "size": installer.stat().st_size,
         "digest": "sha256:" + digest, "browser_download_url": base + name},
        {"name": "SHA256SUMS.txt", "state": "uploaded", "browser_download_url": base + "SHA256SUMS.txt"}]}
    class LocalRelease:
        def open(self, request, **kwargs):
            if request.full_url == LATEST_API:
                return io.BytesIO(json.dumps(release).encode())
            if request.full_url == base + "SHA256SUMS.txt":
                return io.BytesIO((digest + "  " + name + "\n").encode())
            assert request.full_url == base + name
            return installer.open("rb")
    manager = UpdateManager(state, can_install=True, current_version="0.3.0", opener=LocalRelease())
    manager.check();manager.thread.join(10)
    assert manager.status()["state"] == "available", manager.status()
    manager.download();manager.thread.join(120)
    assert manager.status()["state"] == "ready", manager.status()
    manager.request_install()
    plan = manager.prepare_install()
    with ZipFile(plan["backup"]) as archive:
        assert "settings.json" in archive.namelist()
        assert any(name.startswith("jobs/") for name in archive.namelist())
        assert any(name.startswith("prompts/") for name in archive.namelist())
    report = state / "updates/restart-smoke.json"
    report.unlink(missing_ok=True)
    plan["smoke_report"] = str(report)
    # Hold a real parent open until the helper has acquired its process handle.
    parent = subprocess.Popen([sys.executable, "-c", "import sys;sys.stdin.readline()"],
                              stdin=subprocess.PIPE, creationflags=subprocess.CREATE_NO_WINDOW)
    try:
        helper = launch_update(plan, executable, parent.pid, parent.pid)
    finally:
        parent.communicate(input=b"\n", timeout=10)
    assert helper.wait(timeout=240) == 0, (state / "updates/last-result.json").read_text()
    deadline = time.monotonic() + 120
    while time.monotonic() < deadline and not report.exists():
        time.sleep(.2)
    assert report.exists(), "Updated app did not relaunch"
    result = json.loads(report.read_text(encoding="utf-8"))
    assert result["ok"], result
    # The report is written just before the renderer exits; allow its worker cleanup.
    time.sleep(2)
    assert json.loads((state / "updates/last-result.json").read_text())["ok"]
    print("Update OK: official-release fixture, checksum, backup, app exit, silent installer, native relaunch and retained state.")


if __name__ == "__main__":
    main()
