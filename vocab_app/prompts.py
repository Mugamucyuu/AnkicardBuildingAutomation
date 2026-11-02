"""Versioned, file-backed prompts. A batch keeps an immutable prompt snapshot."""
import hashlib
import json
import re
import threading
from functools import wraps
from pathlib import Path
from .settings import RESOURCE_ROOT, user_data_dir

DEFAULTS = {
    "generation": "structured_vocabulary.txt", "tag_policy": "tagging_policy.txt",
    "style_en": "style_en.txt", "style_ja": "style_ja.txt", "style_ko": "style_ko.txt",
    "search_planner": "search_planner.txt", "tag_review": "tag_review.txt",
    "content_repair": "content_repair.txt", "tag_repair": "tag_repair.txt",
    "image_plan": "image_plan.txt",
    "validation": "validation.txt",
    "formatting": "formatting.txt",
}
FILE_TYPES = (*DEFAULTS, "supplement", "legacy", "unclassified")


def locked(method):
    @wraps(method)
    def call(self, *args, **kwargs):
        with self.lock:
            return method(self, *args, **kwargs)
    return call


def display_name(file_id, prompt_type):
    name = file_id.split("/", 1)[1]
    return re.sub(r"^[0-9a-f]{16}-" + re.escape(prompt_type) + "-", "", name)

class PromptStore:
    def __init__(self, directory=None):
        self.directory = Path(directory or user_data_dir() / "prompts")
        self.lock = threading.RLock()

    @locked
    def bindings(self):
        path = self.directory / "bindings.json"
        return json.loads(path.read_text(encoding="utf-8")) if path.exists() else {}

    @locked
    def files(self, prompt_type=None):
        if prompt_type is not None and prompt_type not in FILE_TYPES:
            raise ValueError("未知 prompt 类型。")
        index_path = self.directory / "types.json"
        index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
        bindings = self.bindings()
        files = []
        for kind, directory in (("builtin", RESOURCE_ROOT / "prompts"), ("custom", self.directory)):
            for p in sorted(directory.glob("*")):
                if p.suffix.lower() not in (".txt", ".md"):
                    continue
                file_id = kind + "/" + p.name
                if kind == "builtin":
                    types = [s for s, name in DEFAULTS.items() if p.name == name] or ["legacy"]
                else:
                    # Preserve older bindings without guessing an unbound file's purpose.
                    types = [index[file_id]] if file_id in index else [s for s, fid in bindings.items() if fid == file_id] or ["unclassified"]
                for category in types:
                    if prompt_type is None or category == prompt_type:
                        files.append({"id": file_id, "name": p.name, "display_name": display_name(file_id, category),
                                      "builtin": kind == "builtin", "type": category})
        return files

    @locked
    def read(self, file_id, prompt_type=None):
        if not isinstance(file_id, str) or not re.fullmatch(r"(?:builtin|custom)/[^/\\]+\.(?i:txt|md)", file_id):
            raise ValueError("无效的 prompt 文件。")
        if prompt_type is not None and not any(f["id"] == file_id for f in self.files(prompt_type)):
            raise ValueError("该文件不属于所选 prompt 类型。")
        kind, name = file_id.split("/")
        if re.search(r'[<>:"|?*\x00-\x1f]', name):
            raise ValueError("无效的 prompt 文件名。")
        root = (RESOURCE_ROOT / "prompts") if kind == "builtin" else self.directory
        path = root / name
        if not path.resolve().is_relative_to(root.resolve()):
            raise ValueError("无效的 prompt 文件路径。")
        return path.read_text(encoding="utf-8-sig")

    @locked
    def upload(self, name, text, prompt_type="supplement"):
        if prompt_type not in (*DEFAULTS, "supplement"):
            raise ValueError("请先选择可上传的 prompt 类型。")
        if not isinstance(name, str) or len(name) > 120 or re.search(r'[<>:"|?*\x00-\x1f]', name) or Path(name).name != name or "/" in name or "\\" in name or Path(name).suffix.lower() not in (".txt", ".md"):
            raise ValueError("请上传 txt/md 文件，文件名不可包含路径。")
        if not isinstance(text, str) or not text.strip() or len(text.encode("utf-8")) > 256_000:
            raise ValueError("Prompt 必须是非空文本，且小于 256 KB。")
        self.directory.mkdir(parents=True, exist_ok=True)
        # Content-addressed uploads retain previous versions without overwriting defaults.
        filename = hashlib.sha256(text.encode()).hexdigest()[:16] + "-" + prompt_type + "-" + name
        with self.lock:
            temporary = self.directory / (filename + ".tmp")
            temporary.write_text(text, encoding="utf-8")
            temporary.replace(self.directory / filename)
            file_id = "custom/" + filename
            index_path = self.directory / "types.json"
            index = json.loads(index_path.read_text(encoding="utf-8")) if index_path.exists() else {}
            index[file_id] = prompt_type
            temporary = self.directory / "types.tmp"
            temporary.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(index_path)
        return file_id

    @locked
    def bind(self, stage, file_id):
        if stage not in DEFAULTS:
            raise ValueError("未知 prompt 阶段。")
        if file_id:
            self.read(file_id, stage)
            if stage == 'validation':
                from .validation import parse_validation
                parse_validation(self.read(file_id, stage))
        bindings = self.bindings()
        if file_id:
            bindings[stage] = file_id
        else:
            bindings.pop(stage, None)
        self.directory.mkdir(parents=True, exist_ok=True)
        temporary = self.directory / "bindings.tmp"
        temporary.write_text(json.dumps(bindings, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.directory / "bindings.json")

    @locked
    def snapshot(self, overrides=None, supplement=None):
        bindings = {**self.bindings(), **(overrides or {})}
        if set(bindings) - set(DEFAULTS):
            raise ValueError("未知 prompt 阶段。")
        result = {stage: self.read(bindings.get(stage) or "builtin/" + name, stage) for stage, name in DEFAULTS.items()}
        if supplement:
            result["generation"] += "\n\n" + self.read(supplement, "supplement")
        from .validation import parse_validation
        parse_validation(result['validation'])
        return result

    @locked
    def manifest(self):
        return {"files": self.files(), "stages": DEFAULTS, "types": FILE_TYPES, "bindings": self.bindings()}

    @locked
    def document(self, file_id, prompt_type=None):
        text = self.read(file_id, prompt_type)
        return {"text": text, "sha256": hashlib.sha256(text.encode("utf-8")).hexdigest()}

    @locked
    def save_version(self, name, text, prompt_type, source=None, expected_sha256=None, activate=False):
        """Create an immutable version; only explicitly requested activation changes defaults."""
        if type(activate) is not bool:
            raise ValueError("启用选项必须为布尔值。")
        if source:
            current = self.document(source, prompt_type)
            if expected_sha256 != current["sha256"]:
                raise ValueError("文件内容已变化，请重新载入后再保存。")
        if activate and prompt_type not in DEFAULTS:
            raise ValueError("附加说明请在生成任务中选择。")
        if prompt_type == "validation":
            from .validation import parse_validation
            parse_validation(text)
        file_id = self.upload(name, text, prompt_type)
        if activate:
            self.bind(prompt_type, file_id)
        return {"id": file_id, "manifest": self.manifest(), **self.document(file_id, prompt_type)}

    @locked
    def delete(self, file_id, expected_sha256):
        """Delete a custom version, resetting its bindings; job snapshots are independent."""
        current = self.document(file_id)
        if not file_id.startswith("custom/"):
            raise ValueError("内置提示词不可删除；可以编辑并保存为自定义版本。")
        if expected_sha256 != current["sha256"]:
            raise ValueError("文件内容已变化，请重新载入后再删除。")
        bindings = self.bindings()
        reset = [stage for stage, selected in bindings.items() if selected == file_id]
        # Reset references first: interruption can leave an unused file, never a broken binding.
        for stage in reset:
            self.bind(stage, None)
        (self.directory / file_id.split("/", 1)[1]).unlink()
        index_path = self.directory / "types.json"
        if index_path.exists():
            index = json.loads(index_path.read_text(encoding="utf-8"))
            index.pop(file_id, None)
            temporary = self.directory / "types.tmp"
            temporary.write_text(json.dumps(index, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(index_path)
        return {"manifest": self.manifest(), "reset_stages": reset}

def default_prompts():
    # CLI always uses shipped files; UI bindings are explicit and do not affect it.
    return {stage: (RESOURCE_ROOT / "prompts" / name).read_text(encoding="utf-8") for stage, name in DEFAULTS.items()}

def assemble_generation(prompts, language, images=False):
    text=prompts['generation']+'\n\n'+prompts['tag_policy']+'\n\n'+prompts['style_'+language]
    return text+'\n\n'+prompts['image_plan'] if images else text
