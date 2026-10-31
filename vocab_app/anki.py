"""Anki export with additive, non-destructive first-run provisioning."""
from .preview import render_preview
from .transport import request_json, ServiceError
from .taxonomy import TagCatalog
import base64
import copy
import hashlib
from pathlib import Path
import re
import os

MODEL_NAME = "Ankicard Vocabulary v1"
FIELDS = ("Word", "Back", "Metadata")

class AnkiClient:
    def __init__(self, url=None, transport=request_json, metadata_path=None, api_key=None):
        self.url = url or os.getenv("ANKICONNECT_URL", "http://127.0.0.1:8765")
        self.transport, self.metadata_path = transport, metadata_path
        self.api_key = api_key if api_key is not None else os.getenv("ANKICONNECT_API_KEY", "")

    def invoke(self, action, **params):
        payload = {"action": action, "version": 6, "params": params}
        if self.api_key:
            payload["key"] = self.api_key
        data = self.transport(self.url, payload, timeout=15)
        if not isinstance(data, dict) or "result" not in data or data.get("error") is not None:
            raise ServiceError("Anki 操作失败，请检查牌组、字段及 AnkiConnect 配置。")
        return data["result"]

    def ensure_model(self):
        names = self.invoke("modelNames")
        for number in range(1, 101):
            name = MODEL_NAME if number == 1 else f"{MODEL_NAME} ({number})"
            if name in names:
                if set(FIELDS).issubset(self.invoke("modelFieldNames", modelName=name)):
                    return name
                continue
            self.invoke("createModel", modelName=name, inOrderFields=list(FIELDS), isCloze=False,
                        css=".card {font-family: system-ui, sans-serif; font-size: 18px; text-align: left;} .vocab-metadata {font-size: 12px; opacity: .75;}",
                        cardTemplates=[{"Name": "Recognition", "Front": "{{Word}}", "Back": "{{FrontSide}}<hr id=answer>{{Back}}<div class=\"vocab-metadata\">{{Metadata}}</div>"}])
            return name
        raise ValueError("过多同名且字段不兼容的笔记类型，请检查 Anki 配置。")

    def add_preview(self, note, deck, model=None, media_root=None, allow_duplicate=False, approved_proposals=None):
        if note["provenance"]["provider"] == "offline":
            raise ValueError("离线样例不允许导入 Anki。")
        proposals = note.get("proposed_tags", [])
        if proposals and set(approved_proposals or []) != {p["tag"] for p in proposals}:
            raise ValueError("新标签尚待审核，暂不能导入。")
        catalog = TagCatalog.from_anki(self, self.metadata_path)
        if proposals:
            catalog.add_proposals([p for p in proposals if p["tag"] not in catalog.entries], note["language"])
        if note["language"] not in ("en", "ja", "ko"):
            raise ValueError("不支持此语言。")
        if note["taxonomy_version"] != catalog.catalog["taxonomy_version"]:
            raise ValueError("标签表版本已变化，请重新校验预览。")
        catalog.validate(note["note_tags"], note["language"])
        sense_tags = [tag for sense in note["senses"] for tag in catalog.validate_sense(sense["tags"], note["language"])]
        if catalog.validate(sense_tags, note["language"]) != sorted(note["note_tags"]):
            raise ValueError("词义标签与整条笔记的标签不一致。")
        if not isinstance(deck, str) or not deck.strip() or len(deck) > 200 or any(ord(ch) < 32 for ch in deck) or any(not p.strip() for p in deck.split("::")):
            raise ValueError("请提供有效的目标牌组名称。")
        if deck not in self.invoke("deckNames"):
            self.invoke("createDeck", deck=deck)
        model = model or self.ensure_model()
        fields = self.invoke("modelFieldNames", modelName=model)
        if set(FIELDS).issubset(fields):
            front_field, back_field, metadata_field = FIELDS
        elif {"正面", "背面", "笔记"}.issubset(fields):
            front_field, back_field, metadata_field = "正面", "背面", "笔记"
        else:
            raise ValueError("指定笔记类型需要 Word/Back/Metadata 或 正面/背面/笔记 字段。")
        back = self.render_anki_back(note, media_root)
        return self.invoke("addNote", note={
            "deckName": deck, "modelName": model,
            "fields": {front_field: note["word"], back_field: back,
                       metadata_field: "AI generated; " + note["provenance"]["run_id"]},
            "options": {"allowDuplicate": bool(allow_duplicate)}, "tags": note["note_tags"],
        })

    def render_anki_back(self, note, media_root=None):
        imported = copy.deepcopy(note)
        if imported.get("proposal_review", {}).get("decision") == "approve":
            imported["proposed_tags"] = []
        uploads = []
        for group in ("pronunciation", "images"):
            for asset in imported.get(group, {}).get("assets", []):
                relative = asset.get("local_path", "")
                if media_root is None or not re.fullmatch(r"media/[a-zA-Z0-9_.-]+", relative):
                    raise ValueError("导入媒体需要已下载文件及其预览根目录。")
                root = (Path(media_root) / "media").resolve()
                path = (Path(media_root) / relative).resolve()
                if not path.is_relative_to(root) or not path.is_file():
                    raise ValueError("媒体文件缺失或路径超出预览媒体目录。")
                if path.suffix.lower() not in (".mp3", ".ogg", ".wav", ".jpg", ".jpeg", ".png", ".webp"):
                    raise ValueError("不支持此媒体格式。")
                content = path.read_bytes()
                if not content or len(content) > 12_000_000:
                    raise ValueError("媒体为空或超过大小限制。")
                digest = hashlib.sha256(content).hexdigest()
                uploads.append((asset, "vocab-" + digest[:24] + path.suffix.lower(), content, digest))
        # Validate all files first. Only then upload, without overwriting old media.
        self.last_import_media = []
        for asset, filename, content, digest in uploads:
            stored = self.invoke("storeMediaFile", filename=filename, data=base64.b64encode(content).decode("ascii"), deleteExisting=False)
            if not isinstance(stored, str) or not re.fullmatch(r"[a-zA-Z0-9_.() -]+", stored):
                raise ValueError("Anki 返回的媒体文件名无效。")
            restored = self.invoke("retrieveMediaFile", filename=stored)
            if not isinstance(restored, str) or base64.b64decode(restored) != content:
                raise ValueError("Anki 媒体回读校验失败，本次不添加笔记。")
            asset["anki_filename"] = stored
            self.last_import_media.append({"filename": stored, "sha256": digest, "bytes": len(content), "kind": asset["kind"]})
        return render_preview(imported, standalone=False, anki=True)
