"""Small shipped demo; never falls back to a paid model or writes to Anki."""
import json
from types import SimpleNamespace
from .settings import RESOURCE_ROOT

class OfflineClient:
    settings = SimpleNamespace(provider="offline", model="fixture-v1")

    def generate(self, system, user, **kwargs):
        request = json.loads(user)
        fixture = json.loads((RESOURCE_ROOT / "examples/notes.json").read_text(encoding="utf-8"))
        key = request["language"] + ":" + request["word"]
        if key not in fixture:
            raise ValueError("离线样例仅支持 en:apple、ja:猫、ko:나무；不会自动调用模型。")
        return json.dumps(fixture[key], ensure_ascii=False)
