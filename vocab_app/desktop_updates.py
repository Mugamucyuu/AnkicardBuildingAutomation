"""Hand off a verified installer to a helper outside the installation directory."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import time
from uuid import uuid4

from .settings import RESOURCE_ROOT


def launch_update(plan, executable, parent_pid, worker_pid):
    executable = Path(executable).resolve()
    if os.name != "nt" or executable.name.lower() != "ankicard.exe":
        raise ValueError("Updates require the installed Windows application")
    data = Path(plan["data_directory"]).resolve()
    installer = Path(plan["installer"]).resolve()
    if not installer.is_relative_to(data / "updates"):
        raise ValueError("Invalid update staging directory")
    helper = data / "updates" / ("handoff-" + uuid4().hex)
    helper.mkdir(parents=True)
    script = helper / "install-update.ps1"
    shutil.copyfile(RESOURCE_ROOT / "update/install-update.ps1", script)
    ready = helper / "ready"
    plan = {**plan, "executable": str(executable), "install_directory": str(executable.parent),
            "parent_pid": parent_pid, "worker_pid": worker_pid,
            "ready": str(ready), "result": str(data / "updates/last-result.json"),
            "log": str(helper / "installer.log")}
    plan_path = helper / "plan.json"
    plan_path.write_text(json.dumps(plan, ensure_ascii=False), encoding="utf-8")
    powershell = Path(os.environ["SystemRoot"]) / "System32/WindowsPowerShell/v1.0/powershell.exe"
    process = subprocess.Popen([str(powershell), "-NoProfile", "-NonInteractive", "-ExecutionPolicy", "Bypass",
        "-WindowStyle", "Hidden", "-File", str(script), "-PlanPath", str(plan_path)],
        env={**os.environ, "PSModulePath": str(powershell.parent / "Modules")},
        creationflags=subprocess.CREATE_NO_WINDOW, stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    deadline = time.monotonic() + 15
    while time.monotonic() < deadline:
        if ready.exists():
            return process
        if process.poll() is not None:
            result = data / "updates/last-result.json"
            details = json.loads(result.read_text(encoding="utf-8-sig")) if result.exists() else {}
            raise RuntimeError("Update helper could not start: " + str(details.get("code")) +
                               " / " + str(details.get("error_type")) + " / " + str(details.get("error_line")))
        time.sleep(.1)
    process.terminate()
    process.wait(timeout=5)
    raise TimeoutError("Update helper did not become ready")
