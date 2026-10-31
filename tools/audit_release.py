"""Report likely secrets/private paths by filename and line; never print values."""
import argparse
from pathlib import Path
import re
import subprocess

PATTERNS = {
    "API credential": re.compile(r"\bsk-(?:proj-)?[A-Za-z0-9_-]{20,}"),
    "GitHub credential": re.compile(r"\b(?:gh[pousr]_[A-Za-z0-9]{25,}|github_pat_[A-Za-z0-9_]{30,})"),
    "private home path": re.compile(r"(?:[A-Z]:[/\\]Users[/\\][^\s/\\]+|/(?:Users|home)/[^\s/]+)", re.I),
    "private key": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
}
SKIP = {".git", "output", "build", "dist", ".venv", "venv", "__pycache__", "node_modules", ".pytest_cache"}

def inspect(name, content):
    text = content.decode("utf-8", errors="ignore")
    return [(name, number, label) for number, line in enumerate(text.splitlines(), 1)
            for label, pattern in PATTERNS.items() if pattern.search(line)]

def audit(root, history=False):
    findings = []
    for path in root.rglob("*"):
        relative = path.relative_to(root)
        if any(part in SKIP or part.endswith(".egg-info") for part in relative.parts) or not path.is_file():
            continue
        if path.suffix.lower() in (".pyc", ".pyo", ".png", ".jpg", ".zip", ".whl", ".mp3", ".ogg"):
            continue
        if path.name == ".env" or path.name.startswith(".env.") and path.name != ".env.example":
            findings.append((str(relative), 1, "local environment file"))
        findings.extend(inspect(str(relative), path.read_bytes()))
    if history:
        commits = subprocess.check_output(["git", "-C", str(root), "rev-list", "--all"], text=True).splitlines()
        for commit in commits:
            names = subprocess.check_output(["git", "-C", str(root), "ls-tree", "-rz", "--name-only", commit]).decode("utf-8").strip("\0").split("\0")
            for name in names:
                content = subprocess.check_output(["git", "-C", str(root), "show", commit + ":" + name])
                findings.extend(inspect(commit[:8] + ":" + name, content))
    return findings

def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, default=Path.cwd())
    parser.add_argument("--history", action="store_true")
    args = parser.parse_args()
    findings = audit(args.root.resolve(), args.history)
    for name, line, reason in findings:
        print(f"{name}:{line}: {reason} [value redacted]")
    print(f"Release audit: {len(findings)} finding(s).")
    return bool(findings)

if __name__ == "__main__":
    raise SystemExit(main())
