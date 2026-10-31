"""Verify an installed wheel away from the source checkout, without Anki or API calls."""
import argparse
import json
import os
from pathlib import Path
import re
import subprocess
import sys
import tempfile
import time
from urllib.request import Request, urlopen


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("wheel", type=Path)
    args = parser.parse_args()
    wheel = args.wheel.resolve()
    output = Path("output").resolve()
    output.mkdir(exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="installed-wheel-", dir=output) as directory:
        directory = Path(directory)
        subprocess.run([sys.executable, "-m", "venv", str(directory / "venv")], check=True, capture_output=True)
        python = directory / "venv" / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
        subprocess.run([str(python), "-m", "pip", "install", "--no-index", "--no-deps", str(wheel)], check=True, capture_output=True)
        env = {**os.environ, "ANKICARD_DATA_DIR": str(directory / "state")}
        for variable in ("PYTHONPATH", "DEEPSEEK_API_KEY", "OPENAI_API_KEY", "DEEPSEEK_SEARCH_API_KEY", "ANKI_AI_PROVIDER", "DEEPSEEK_MODEL", "OPENAI_MODEL"):
            env.pop(variable, None)
        code = "from vocab_app.japanese_pitch import lookup_kanjium; from vocab_app.prompts import default_prompts; assert lookup_kanjium('猫','ねこ').pitch_accents; assert len(default_prompts()) == 10; print('Bundled resources OK')"
        subprocess.run([str(python), "-I", "-c", code], check=True, cwd=directory, env=env, capture_output=True)
        subprocess.run([str(python), "-I", "-m", "vocab_app.cli", "--language", "ja", "--word", "猫"], check=True, cwd=directory, env=env, capture_output=True)
        assert list((directory / "state/previews").glob("*.html"))
        process = subprocess.Popen([str(python), "-I", "-m", "vocab_app", "--no-browser", "--port", "0"], cwd=directory, env=env, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8")
        try:
            line = process.stdout.readline()
            url = re.search(r"http://127\.0\.0\.1:\d+", line).group()
            def request(path, data=None):
                headers = {"Content-Type": "application/json", "X-Vocab-Token": bootstrap["token"]} if data is not None else {}
                req = Request(url + path, data=json.dumps(data).encode() if data is not None else None, headers=headers)
                with urlopen(req, timeout=10) as response:
                    return json.load(response)
            bootstrap = request("/api/bootstrap")
            assert bootstrap["vocabulary"] == ["en.txt", "ja.txt", "ko.txt"]
            assert request("/api/jobs") == []
            assert not any(bootstrap["credentials"].values())
            for language, word in (("en", "apple"), ("ja", "猫"), ("ko", "나무")):
                job = request("/api/jobs", {"language": language, "text": word, "provider": "offline", "mode": "independent", "tag_source": "seed"})
                for attempt in range(100):
                    saved = next(j for j in request("/api/jobs") if j["id"] == job["id"])
                    if saved["status"] == "complete": break
                    time.sleep(.05)
                assert saved["items"][0]["status"] == "ready", saved["items"][0]["error"]
                with urlopen(url + saved["items"][0]["preview"], timeout=10) as response:
                    assert word in response.read().decode("utf-8")
            print("Installed wheel OK: bundled prompts/pitch, CLI, clean user state, HTTP UI, three offline languages.")
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__ == "__main__":
    main()
