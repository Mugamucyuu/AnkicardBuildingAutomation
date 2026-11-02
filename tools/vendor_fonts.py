"""Fetch pinned, unmodified OFL fonts for offline UI use (maintainer only)."""
import hashlib
import json
from pathlib import Path
from urllib.parse import quote
from urllib.request import urlopen

REVISION = "6c1dbe27dcf7d817d4b62cec033ba77fa8e2a5ec"
FONTS = {
    "inter": ("Inter[opsz,wght].ttf", "Inter.ttf"),
    "manrope": ("Manrope[wght].ttf", "Manrope.ttf"),
    "sourceserif4": ("SourceSerif4[opsz,wght].ttf", "SourceSerif4.ttf"),
    "notosanssc": ("NotoSansSC[wght].ttf", "NotoSansSC.ttf"),
    "notoserifsc": ("NotoSerifSC[wght].ttf", "NotoSerifSC.ttf"),
}


def main():
    root = Path(__file__).resolve().parents[1] / "vocab_app/web/fonts"
    root.mkdir(parents=True, exist_ok=True)
    sources = []
    for family, (upstream, name) in FONTS.items():
        for source, destination in ((upstream, name), ("OFL.txt", family + "-OFL.txt")):
            url = f"https://raw.githubusercontent.com/google/fonts/{REVISION}/ofl/{family}/{quote(source)}"
            with urlopen(url, timeout=120) as response:
                content = response.read()
            (root / destination).write_bytes(content)
            sources.append({"file": destination, "url": url, "sha256": hashlib.sha256(content).hexdigest()})
            print(destination, len(content))
    (root / "sources.json").write_text(json.dumps(sources, indent=2) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
