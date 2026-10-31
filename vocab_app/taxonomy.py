"""Validate note tags against the agreed vocabulary, allowing broad new subjects."""
import copy
import re
import hashlib
import json
from datetime import datetime, timezone
from .settings import RESOURCE_ROOT, user_data_dir

class TagCatalog:
    def __init__(self, catalog):
        self.catalog = copy.deepcopy(catalog)
        self.entries = {e["tag"]: e for e in self.catalog["entries"]}
        self.snapshot = {"mode": "seed", "anki_tags": [], "excluded": [], "taxonomy_version": self.catalog["taxonomy_version"]}

    @classmethod
    def load(cls):
        import json
        return cls(json.loads((RESOURCE_ROOT / "data/tags/taxonomy.json").read_text(encoding="utf-8-sig")))

    @classmethod
    def from_anki(cls, client, metadata_path=None):
        catalog = cls.load()
        tags = client.invoke("getTags")
        if not isinstance(tags, list) or any(not isinstance(t, str) for t in tags):
            raise ValueError("Anki 标签列表格式无效。")
        path = metadata_path or user_data_dir() / "tag_metadata.json"
        metadata = json.loads(path.read_text(encoding="utf-8-sig")) if path.exists() else {"tags": {}}
        descriptions = metadata.get("tags", {})
        if not isinstance(descriptions, dict):
            raise ValueError("用户标签说明必须是 tags 对象。")
        excluded = []
        controlled = set(catalog.catalog["rules"]["extension"]["controlled"])
        for tag in sorted(set(tags)):
            root = tag.split("::")[0]
            if tag in catalog.entries:
                catalog.entries[tag]["in_anki"] = True
                info = descriptions.get(tag, {})
                if not isinstance(info, dict):
                    raise ValueError("标签说明项必须为对象。")
                if info.get("definition_zh"):
                    catalog.entries[tag]["definition_zh"] = info["definition_zh"]
                    catalog.entries[tag]["description_source"] = "user_metadata"
                continue
            reason = None
            if not re.fullmatch(catalog.catalog["naming"]["pattern"], tag) or len(tag) > catalog.catalog["naming"]["max_tag_length"]:
                reason = "不是英文小写层级名称；仅展示，不自动改名或写入"
            elif root in controlled or root in ("region", "medium"):
                reason = "与固定词性／语源／地域或已移除维度冲突"
            if reason:
                excluded.append({"tag": tag, "reason": reason})
                continue
            info = descriptions.get(tag, {})
            if not isinstance(info, dict):
                raise ValueError("标签说明项必须为对象。")
            languages = info.get("languages", ["*"])
            if not isinstance(languages, list) or not languages or any(x not in ("*", "en", "ja", "ko") for x in languages):
                raise ValueError("用户标签语言范围无效。")
            parts = tag.split("::")
            for index in range(1, len(parts)):
                parent = "::".join(parts[:index])
                if parent not in catalog.entries:
                    catalog.entries[parent] = {"tag": parent, "parent": "::".join(parts[:index-1]) or None,
                        "definition_zh": "由 Anki 子标签重建的层级分组", "kind": "group", "languages": ["*"], "source": "anki_parent", "aliases": []}
            catalog.entries[tag] = {"tag": tag, "parent": tag.rsplit("::", 1)[0] if "::" in tag else None,
                "label_zh": info.get("label_zh", tag), "definition_zh": info.get("definition_zh", "用户在 Anki 中建立的标签；只有名称和父级，含义不明确时不要猜测使用。"),
                "kind": "assignable", "languages": languages, "status": "user_defined", "source": "anki",
                "description_source": "user_metadata" if info.get("definition_zh") else "name_only", "in_anki": True, "aliases": []}
            # Resolve only an exact, unique leaf-name match, not semantic guesses.
            equivalents = [e["tag"] for e in catalog.catalog["entries"] if e["kind"] != "group"
                and e["tag"].split("::")[0] in catalog.catalog["rules"]["extension"]["extensible"]
                and (tag == e["tag"].split("::")[-1] or tag in e.get("aliases", []))]
            equivalent = info.get("equivalent_to") if "equivalent_to" in info else (equivalents[0] if len(equivalents) == 1 and not info.get("definition_zh") else None)
            if equivalent:
                if equivalent not in catalog.entries or catalog.entries[equivalent]["kind"] == "group" or equivalent.split("::")[0] in controlled:
                    raise ValueError("用户标签同义映射目标无效。")
                catalog.entries[tag]["equivalent_to"] = equivalent
                catalog.entries[tag]["definition_zh"] = info.get("definition_zh") or catalog.entries[equivalent]["definition_zh"]
        catalog.snapshot = {"mode": "anki", "anki_tags": sorted(set(tags)), "excluded": excluded,
            "taxonomy_version": catalog.catalog["taxonomy_version"], "fetched_at": datetime.now(timezone.utc).isoformat()}
        catalog.catalog["entries"] = list(catalog.entries.values())
        catalog.snapshot_info()
        return catalog

    def clone(self):
        result = TagCatalog(self.catalog)
        result.entries = copy.deepcopy(self.entries)
        result.snapshot = copy.deepcopy(self.snapshot)
        return result

    def snapshot_info(self):
        payload = {"entries": list(self.entries.values()), "snapshot": {k:v for k,v in self.snapshot.items() if k not in ("id", "fetched_at")}}
        digest = hashlib.sha256(json.dumps(payload, ensure_ascii=False, sort_keys=True).encode()).hexdigest()
        self.snapshot.setdefault("id", digest)
        return {**copy.deepcopy(self.snapshot), "entry_count": len(self.entries)}

    def prompt_context(self, language):
        tree = [{"tag": e["tag"], "parent": e.get("parent"), "assignable": e["kind"] != "group",
                 "definition": e["definition_zh"], "source": e.get("source", "seed"), "in_anki": e.get("in_anki", False),
                 "description_source": e.get("description_source", "seed")}
                for e in self.entries.values() if "*" in e["languages"] or language in e["languages"]]
        equivalents = [{"preferred": e["tag"], "equivalent": e["equivalent_to"]} for e in self.entries.values() if e.get("equivalent_to")]
        return {"allowed_tags": [e for e in tree if e["assignable"]], "tag_tree": tree, "equivalent_tags": equivalents, "tag_snapshot": self.snapshot_info()}

    def add_proposals(self, proposals, language):
        added = []
        controlled = self.catalog["rules"]["extension"]["controlled"]
        for proposal in proposals:
            if not isinstance(proposal, dict):
                raise ValueError("新增标签必须为对象。")
            required = ("tag", "parent", "label_zh", "definition_zh", "rationale_zh")
            if any(not isinstance(proposal.get(k), str) or not proposal[k].strip() for k in required):
                raise ValueError("新增标签缺少名称、父级、定义或新增理由。")
            tag, parent = proposal["tag"], proposal["parent"]
            if tag in self.entries:
                raise ValueError("新增标签已存在，应直接复用。")
            if not re.fullmatch(self.catalog["naming"]["pattern"], tag):
                raise ValueError("新增标签必须使用英文小写层级名称。")
            dimension = tag.split("::")[0]
            if dimension in controlled or dimension not in self.catalog["rules"]["extension"]["extensible"]:
                raise ValueError("此分类不允许 AI 自行扩展。")
            if tag.rsplit("::", 1)[0] != parent:
                raise ValueError("新增标签父级不匹配。")
            if parent not in self.entries and parent not in [d["id"] for d in self.catalog["dimensions"]]:
                raise ValueError("新增标签父级不存在。")
            if len(tag.split("::")) > self.catalog["naming"]["max_segments"] or len(tag) > self.catalog["naming"]["max_tag_length"]:
                raise ValueError("新增标签过长。")
            if dimension == "domain" and len(tag.split("::")) > 3:
                raise ValueError("领域标签仅允许宽泛分类，不允许新增细分学科。")
            aliases = proposal.get("aliases", [])
            if not isinstance(aliases, list) or any(not isinstance(p, str) or not p.isascii() for p in aliases):
                raise ValueError("标签别名必须为英文字符串列表。")
            equivalents = {p.casefold() for p in aliases}
            equivalents.add(tag.casefold())
            existing = {name.casefold() for e in self.entries.values() for name in [e["tag"], *e.get("aliases", [])]}
            if equivalents & existing:
                raise ValueError("新增标签与已有名称或别名冲突。")
            entry = {**proposal, "languages": [language], "kind": "assignable",
                     "status": "needs_review", "aliases": proposal.get("aliases", [])}
            # Semantic duplicate detection needs a separate review step, so proposals are
            # preview-only until approved. No global catalog/Anki mutations occur here.
            self.entries[tag] = entry
            added.append(entry)
        return added

    def validate(self, tags, language):
        if not isinstance(tags, list) or any(not isinstance(t, str) for t in tags):
            raise ValueError("标签必须为字符串列表。")
        unique = set(tags)
        for entry in self.entries.values():
            if entry["tag"] in unique and entry.get("equivalent_to") in unique:
                unique.discard(entry["equivalent_to"])
        for tag in unique:
            entry = self.entries.get(tag)
            if entry is None or entry["kind"] == "group":
                raise ValueError("使用了未知标签或仅分组标签。")
            if "*" not in entry["languages"] and language not in entry["languages"]:
                raise ValueError("标签不适用于当前语言。")
            if tag.startswith("origin::") and language == "en":
                raise ValueError("英语不使用语源标签。")
        return sorted(t for t in unique if not any(other.startswith(t + "::") for other in unique))

    def validate_sense(self, tags, language):
        tags = self.validate(tags, language)
        if not any(tag.startswith("pos::") for tag in tags):
            raise ValueError("每个词义必须有词性标签。")
        if language in ("ja", "ko") and not any(tag.startswith("origin::") for tag in tags):
            raise ValueError("日语、韩语每个词义必须有语源标签；混合来源允许多选。")
        return tags
