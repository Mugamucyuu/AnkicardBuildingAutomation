"""Generate a structured preview. No Anki writes or media downloads here."""
import json
import re
import hashlib
from datetime import datetime, timezone, timedelta
from uuid import uuid4
from .taxonomy import TagCatalog
from .media import MediaRegistry
from .quality import generate_content
from .research import ResearchCollector
from .tag_review import audit_tags
from .prompts import default_prompts, assemble_generation

def require_text(value, name):
    if not isinstance(value, str) or not value.strip():
        raise ValueError(name + " 必须为非空文本。")
    return value.strip()

class ImportPipeline:
    def __init__(self, model_client, media=None, tag_catalog=None, prompts=None):
        self.model = model_client
        self.media = media or MediaRegistry()
        if tag_catalog is None and getattr(model_client, "enforce_readability", False):
            from .anki import AnkiClient
            try:
                tag_catalog = TagCatalog.from_anki(AnkiClient())
            except (RuntimeError, OSError) as error:
                raise RuntimeError("无法同步 Anki 标签；请打开 AnkiConnect，或显式选择初始标签表模式。") from error
        self.tag_catalog = tag_catalog or TagCatalog.load()
        self.tag_catalog.snapshot_info()
        self.prompts = {**default_prompts(), **(prompts or {})}
        self.tag_policy = self.prompts["tag_policy"]

    def generate(self, word, language, pronunciation_source="none", image_source="none", generation_mode="independent", sources=()):
        word = require_text(word, "词汇")
        if language not in ("en", "ja", "ko"):
            raise ValueError("目前支持 en、ja、ko。")
        if pronunciation_source == "commons" or image_source not in ("none", "auto", "commons"):
            raise ValueError("请选择发音来源和图片来源各自支持的选项。")
        # Validate sources before spending tokens.
        pronunciation = self.media.lookup(pronunciation_source, language, word).to_dict()
        catalog = self.tag_catalog.clone()
        def plan_query(term, lang):
            planner = type(self.model)(self.model.settings, self.model.transport)
            return planner.generate(self.prompts["search_planner"], json.dumps({"word":term,"language":lang},ensure_ascii=False))
        research = ResearchCollector().collect(word, language, generation_mode, sources, plan_query)
        instruction = assemble_generation(self.prompts, language, image_source != 'none')
        user = json.dumps({"word": word, "language": language, **catalog.prompt_context(language), "research":research}, ensure_ascii=False)
        content, quality_check = generate_content(
            self.model, instruction, user, language,
            enforce=getattr(self.model, "enforce_readability", False),
            repair_prompt=self.prompts["content_repair"],
            _validation=self.prompts['validation'],
        )
        if not isinstance(content, dict):
            raise ValueError("AI 输出必须为 JSON 对象。")
        if research["sources"]:
            known_ids={source["id"] for source in research["sources"]}
            cited=set(re.findall(r"\[(S\d+)\]",json.dumps(content,ensure_ascii=False)))
            if not cited or not cited.issubset(known_ids):
                raise ValueError("联网回答缺少有效来源标记，或引用了不存在的来源。")
        tag_audit = audit_tags(self.model, content, language, research, word=word, catalog=catalog, policy=self.tag_policy, prompts=self.prompts, _validation=self.prompts['validation']) if getattr(self.model, "enforce_readability", False) else None
        senses = content.get("senses")
        if not isinstance(senses, list) or not senses:
            raise ValueError("至少需要一个词义。")
        proposals = content.get("proposed_tags", [])
        if not isinstance(proposals, list):
            raise ValueError("proposed_tags 必须为列表。")
        proposed = catalog.add_proposals(proposals, language)
        sense_ids, note_tags, assignments = set(), [], []
        run_id = "ai-run:" + str(uuid4())
        for sense in senses:
            if not isinstance(sense, dict):
                raise ValueError("词义必须为对象。")
            sid = require_text(sense.get("id"), "词义 ID")
            if sid in sense_ids:
                raise ValueError("词义 ID 重复。")
            sense_ids.add(sid)
            require_text(sense.get("definition"), "释义")
            examples = sense.get("examples")
            if not isinstance(examples, list) or not examples:
                raise ValueError("每个词义至少需要一个例句。")
            for example in examples:
                require_text(example, "例句")
            tags = catalog.validate_sense(sense.get("tags"), language)
            if not any(t.startswith("pos::") for t in tags):
                raise ValueError("每个词义至少需要一个词性标签。")
            reasons = sense.get("tag_reasons")
            if not isinstance(reasons, dict):
                raise ValueError("每个标签都必须保留判断理由。")
            for tag in tags:
                reason = require_text(reasons.get(tag), "标签理由")
                assignments.append({
                    "tag": tag, "sense_ids": [sid],
                    "evidence": {"source_type": "ai_inference", "source_ref": run_id,
                                 "source_label": None, "reason_zh": reason},
                    "confidence": "medium", "as_of": datetime.now(timezone(timedelta(hours=8))).date().isoformat(),
                })
            sense["tags"] = tags
            note_tags.extend(tags)
        analysis = content.get("analysis")
        if not isinstance(analysis, dict):
            raise ValueError("缺少分析对象。")
        for key in ("etymology", "nuance", "synonyms"):
            require_text(analysis.get(key), key)
        # A sense must exist before searching; reuse the same model response
        # for a tiny visual query plan. No vision call or extra model round trip.
        images = self.media.select_image(word, language, senses, content.get('image_plan')).to_dict() if image_source != 'none' else self.media.lookup('none', language, word).to_dict()
        forms = content.get("alternative_forms", "")
        if isinstance(forms, list) and all(isinstance(form, str) for form in forms):
            forms = " / ".join(forms)
        if not isinstance(forms, str):
            raise ValueError("其他表记必须为文本或文本列表。")
        # Re-resolve with the generated reading: a kanji headword can have
        # several readings. Keep exact dictionary evidence and source order.
        if language == "ja" and pronunciation_source in ("auto", "kanjium", "ojad", "ubiq") and hasattr(self.media, "japanese_accent"):
            reading = content.get("reading", "")
            if isinstance(reading, str) and reading.strip():
                options = {} if pronunciation_source == "auto" else {"source": pronunciation_source}
                accent = self.media.japanese_accent(word, reading.strip(), **options).to_dict()
                pronunciation["lookup_attempts"].extend(accent["lookup_attempts"])
                pronunciation["pitch_accents"] = accent["pitch_accents"]
                pronunciation["warnings"] = [w for w in pronunciation["warnings"] if "声调" not in w]
                pronunciation["warnings"].extend(accent["warnings"])
                if accent["pitch_accents"]:
                    if not pronunciation["assets"]:
                        pronunciation["assets"] = accent["assets"]
                    pronunciation["warnings"] = [w for w in pronunciation["warnings"] if "声调" not in w and not (accent["assets"] and "真人录音" in w)]
        return {
            "format_version": 1, "taxonomy_version": catalog.catalog["taxonomy_version"],
            "tag_snapshot": self.tag_catalog.snapshot_info(),
            "tag_policy_sha256": hashlib.sha256(self.tag_policy.encode()).hexdigest(),
            "prompt_sha256": {k: hashlib.sha256(v.encode()).hexdigest() for k, v in self.prompts.items()},
            "image_plan_prompt_sha256": hashlib.sha256(self.prompts["image_plan"].encode()).hexdigest() if image_source != 'none' else None,
            "word": word, "language": language, "senses": senses, "analysis": analysis,
            "reading": content.get("reading", ""), "alternative_forms": forms,
            "note_tags": catalog.validate(note_tags, language), "assignments": assignments,
            "proposed_tags": proposed, "pronunciation": pronunciation, "images": images,
            "provenance": {"content": "ai_generated", "run_id": run_id,
                           "provider": self.model.settings.provider, "model": self.model.settings.model},
            "review_required": True,
            "quality_check": quality_check,
            "research":research, "tag_audit":tag_audit,
        }
