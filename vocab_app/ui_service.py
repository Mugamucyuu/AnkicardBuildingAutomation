"""Local UI application services; generation and Anki writes stay server-side."""
import copy
import json
import os
import re
import threading
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime, timezone
from pathlib import Path
from uuid import uuid4

from .anki import AnkiClient
from .media import SOURCES as MEDIA_SOURCES, MediaResult
from .pipeline import ImportPipeline
from .preview import render_preview
from .prompts import PromptStore
from .providers import ModelClient, KEY_VARIABLES
from .research import SOURCES
from .settings import RESOURCE_ROOT, Settings, user_data_dir
from .taxonomy import TagCatalog

DEFAULT_CONCURRENCY = 4
MAX_CONCURRENCY = 32


def validate_concurrency(value):
    if type(value) is not int or not 1 <= value <= MAX_CONCURRENCY:
        raise ValueError(f"并发数必须为 1–{MAX_CONCURRENCY} 的整数。")
    return value


def write_json(path, value):
    path.parent.mkdir(parents=True, exist_ok=True)
    temporary = path.with_suffix(".tmp")
    temporary.write_text(json.dumps(value, ensure_ascii=False, indent=2), encoding="utf-8")
    temporary.replace(path)


def parse_words(text):
    if not isinstance(text, str) or len(text) > 200_000:
        raise ValueError("词汇文本过长或格式无效。")
    words = []
    for line in re.split(r"[\n\r,，、]+", text):
        word = re.sub(r"^\s*(?:[-*+]\s+|\d+[.)、]\s*)", "", line).strip()
        if not word or word.startswith("#"):
            continue
        if len(word) > 200:
            raise ValueError("单个词条不能超过 200 字符；短语中的空格会保留。")
        if word not in words:
            words.append(word)
    if len(words) > 1000:
        raise ValueError("每批最多 1000 个词汇。")
    return words


class UIService:
    def __init__(self, directory=None, anki=None):
        self.directory = Path(directory or user_data_dir())
        self.directory.mkdir(parents=True, exist_ok=True)
        self.prompts = PromptStore(self.directory / "prompts")
        self.metadata_path = self.directory / "tag_metadata.json"
        self.anki = anki or AnkiClient(metadata_path=self.metadata_path)
        self.vocabulary_directory = self.directory / "vocabulary"
        self.vocabulary_directory.mkdir(exist_ok=True)
        self.lock = threading.RLock()
        self.pool = ThreadPoolExecutor(max_workers=1, thread_name_prefix="vocab-ui")
        self.jobs = {}
        self.settings_path = self.directory / "settings.json"
        environment = Settings.from_env()
        self.preferences = {"locale": "zh", "theme": "system", "provider": environment.provider, "model": environment.model or ("deepseek-flash" if environment.provider == "deepseek" else ""), "concurrency": DEFAULT_CONCURRENCY}
        if self.settings_path.exists():
            self.preferences.update(json.loads(self.settings_path.read_text(encoding="utf-8")))
        for path in (self.directory / "jobs").glob("*/job.json"):
            job = json.loads(path.read_text(encoding="utf-8"))
            for item in job["items"]:
                if item["status"] in ("queued", "generating"):
                    item.update(status="failed", error="进程已停止；可以重试未完成的词汇。")
                elif item["status"] == "importing":
                    item.update(status="uncertain", error="导入结果待核对；再次导入时先按 run_id 检查 Anki。")
            job["status"] = "complete"
            if job.get("bulk_import", {}).get("status") in ("queued", "running"):
                job["bulk_import"]["status"] = "interrupted"
            self.jobs[job["id"]] = job
            self.save(job)

    def save(self, job):
        write_json(self.directory / "jobs" / job["id"] / "job.json", job)

    def bootstrap(self):
        return {"settings": self.preferences, "prompts": self.prompts.manifest(),
                "sources": SOURCES, "media_sources": MEDIA_SOURCES,
                "vocabulary": sorted(self.vocabulary_files()),
                "credentials": {p: bool(os.getenv(v)) for p, v in KEY_VARIABLES.items()},
                "search_configured": bool(os.getenv("DEEPSEEK_SEARCH_API_KEY") or os.getenv("DEEPSEEK_API_KEY"))}

    def update_settings(self, data):
        with self.lock:
            if data.get("locale", "zh") not in ("zh", "ja", "en") or data.get("theme", "system") not in ("system", "light", "dark"):
                raise ValueError("界面语言或主题无效。")
            if data.get("provider", "deepseek") not in KEY_VARIABLES:
                raise ValueError("请选择 DeepSeek 或 OpenAI。")
            if any(j["status"] in ("queued", "running") for j in self.jobs.values()) and data.get("keys"):
                raise ValueError("请等当前任务结束，再更新密钥。")
            keys = data.get("keys", {})
            if not isinstance(keys, dict) or set(keys) - {"deepseek", "openai", "search"}:
                raise ValueError("无效的密钥选项。")
            preferences = {k: data.get(k, self.preferences[k]) for k in self.preferences}
            validate_concurrency(preferences["concurrency"])
            if not isinstance(preferences["model"], str) or len(preferences["model"]) > 120:
                raise ValueError("模型 ID 无效。")
            for provider, key in keys.items():
                if not isinstance(key, str) or len(key) > 1024:
                    raise ValueError("密钥格式无效。")
            for provider, key in keys.items():
                if key.strip():
                    os.environ[{**KEY_VARIABLES, "search": "DEEPSEEK_SEARCH_API_KEY"}[provider]] = key.strip()
            self.preferences = preferences
            write_json(self.settings_path, self.preferences)
            return self.bootstrap()

    def connection(self):
        return {"version": self.anki.invoke("version"), "decks": self.anki.invoke("deckNames")}

    def vocabulary(self, name):
        if name not in self.bootstrap()["vocabulary"]:
            raise ValueError("词库文件不存在。")
        raw = self.vocabulary_files()[name].read_bytes()
        for encoding in ("utf-8-sig", "gb18030"):
            try:
                return {"text": raw.decode(encoding)}
            except UnicodeError:
                continue
        raise ValueError("请把词库保存为 UTF-8 txt/md 文本。")

    def vocabulary_files(self):
        paths = {}
        for directory in (RESOURCE_ROOT / "examples/vocabulary", self.vocabulary_directory):
            paths.update({p.name: p for p in directory.glob("*") if p.is_file() and p.suffix.lower() in (".txt", ".md")})
        return paths

    def prompt_preview(self, language='en', word='example', images=False):
        from .prompts import assemble_generation
        if language not in ('en','ja','ko'):raise ValueError('语言无效。')
        prompts=self.prompts.snapshot()
        return {'generation':assemble_generation(prompts,language,images),
                'search_planner':prompts['search_planner'],
                'tag_review':prompts['tag_review']+'\n\n'+prompts['tag_policy'],
                'content_repair':prompts['content_repair'],'tag_repair':prompts['tag_repair'],
                'validation':json.loads(prompts['validation']),
                'example_input':{'word':word,'language':language,**TagCatalog.load().prompt_context(language),'research':{'mode':'independent','sources':[],'queries':[]}},
                'notice':'当前配置预览使用初始标签和空资料；真实标签、资料、附加说明和重试反馈以任务实际请求为准。'}

    def prompt_requests(self, job_id, index):
        with self.lock:
            job=self.jobs[job_id]
            if not 0 <= index < len(job['items']):raise ValueError('词卡不存在。')
            root=self.directory/'jobs'/job_id
            snapshot=json.loads((root/'prompts.json').read_text(encoding='utf-8'))
            records=[json.loads(p.read_text(encoding='utf-8')) for p in sorted((root/'requests'/str(index)).glob('*.json'))]
            return {'word':job['items'][index]['word'],'snapshot':snapshot,'requests':records,
                    'notice':'旧任务可能只有模板快照，没有实际请求记录。记录不含密钥或 HTTP 认证头。'}

    def tags(self, seed=False):
        catalog = TagCatalog.load() if seed else TagCatalog.from_anki(self.anki, self.metadata_path)
        # Include every real Anki tag, even if excluded from AI assignment.
        entries = {name: {"tag": name, "description": e.get("definition_zh", ""), "in_anki": e.get("in_anki", False), "assignable": e["kind"] != "group", "excluded": False}
                   for name, e in catalog.entries.items()}
        for item in catalog.snapshot.get("excluded", []):
            entries[item["tag"]] = {"tag": item["tag"], "description": item["reason"], "in_anki": True, "excluded": True, "assignable": False}
        return {"entries": list(entries.values()), "snapshot": catalog.snapshot_info()}

    def browse(self, tags, match="all"):
        actual = self.anki.invoke("getTags")
        if not isinstance(tags, list) or not tags or len(tags) > 30 or any(t not in actual for t in tags) or match not in ("all", "any"):
            raise ValueError("请选择现有 Anki 标签。")
        terms = ['tag:"' + t.replace("\\", "\\\\").replace('"', '\\"') + '"' for t in tags]
        query = (" " if match == "all" else " OR ").join(terms)
        return {"query": query, "notes": self.anki.invoke("guiBrowse", query=query)}

    def list_jobs(self):
        with self.lock:
            return copy.deepcopy(sorted(self.jobs.values(), key=lambda j: j["created"], reverse=True))

    def create_job(self, data):
        language = data.get("language")
        if language not in ("en", "ja", "ko"):
            raise ValueError("请选择词汇语言。")
        words = parse_words(data.get("text", ""))
        if not words:
            raise ValueError("请先输入词汇。")
        concurrency = validate_concurrency(data.get("concurrency", self.preferences["concurrency"]))
        provider, mode = data.get("provider"), data.get("mode")
        if provider not in (*KEY_VARIABLES, "offline") or mode not in ("independent", "web", "sources"):
            raise ValueError("模型来源或生成模式无效。")
        if not isinstance(data.get("model", ""), str) or len(data.get("model", "")) > 120:
            raise ValueError("模型 ID 无效。")
        sources = data.get("sources", [])
        if not isinstance(sources, list) or any(s not in SOURCES or language not in SOURCES[s]["languages"] for s in sources):
            raise ValueError("词典不支持当前语言。")
        if mode == "sources" and not sources:
            raise ValueError("请至少选择一个词典。")
        if data.get("tag_source", "anki") not in ("anki", "seed"):
            raise ValueError("标签来源无效。")
        audio, image = data.get("audio", "auto"), data.get("image", "auto")
        if audio != "auto" and (audio not in MEDIA_SOURCES or audio == "commons" or language not in MEDIA_SOURCES[audio]["languages"]):
            raise ValueError("发音来源不支持当前语言。")
        if image not in ("none", "auto", "commons"):
            raise ValueError("无效图片来源。")
        if provider == "offline":
            if mode != "independent" or data.get("auto_import"):
                raise ValueError("离线演示仅使用独立模式，不支持导入。")
            permitted = {"en": "apple", "ja": "猫", "ko": "나무"}
            if words != [permitted[language]]:
                raise ValueError("离线演示支持 en:apple、ja:猫、ko:나무。")
            audio, image = "none", "none"
        else:
            Settings(provider, data.get("model", "")).require_model()
            if not os.getenv(KEY_VARIABLES[provider]):
                raise ValueError("请在设置中填写对应 API key。")
            if mode == "web" and not self.bootstrap()["search_configured"]:
                raise ValueError("自动联网检索还需要 DeepSeek 检索密钥。")
        deck = data.get("deck", "")
        if not isinstance(deck, str) or len(deck) > 200:
            raise ValueError("目标牌组无效。")
        if data.get("auto_import") and not deck:
            raise ValueError("自动导入需要选择目标牌组。")
        prompts = self.prompts.snapshot(data.get("bindings"), data.get("supplement"))
        # Snapshot Anki once, before enqueueing or spending model tokens.
        catalog = TagCatalog.load() if provider == "offline" or data.get("tag_source") == "seed" else TagCatalog.from_anki(self.anki, self.metadata_path)
        config = {"language": language, "provider": provider, "model": data.get("model", ""), "mode": mode, "sources": sources,
                  "audio": audio, "image": image, "deck": deck, "auto_import": bool(data.get("auto_import")), "tag_source": data.get("tag_source", "anki"), "concurrency": concurrency}
        job = {"id": uuid4().hex, "created": datetime.now(timezone.utc).isoformat(), "status": "queued", "cancel": False, "config": config,
               "items": [{"word": word, "status": "queued", "error": "", "note_id": None} for word in words]}
        root = self.directory / "jobs" / job["id"]
        write_json(root / "prompts.json", prompts)
        write_json(root / "catalog.json", {"catalog": catalog.catalog, "snapshot": catalog.snapshot})
        with self.lock:
            self.jobs[job["id"]] = job
            self.save(job)
        self.pool.submit(self.run, job["id"], prompts, catalog)
        return copy.deepcopy(job)

    def _status(self, job, item, **values):
        with self.lock:
            item.update(values)
            self.save(job)

    def _generate_item(self, job_id, index, prompts, catalog):
        from .examples import OfflineClient
        from .public_media import PublicMediaRegistry, download_assets
        job = self.jobs[job_id]
        config, item = job["config"], job["items"][index]
        root = self.directory / "jobs" / job_id
        with self.lock:
            if job["cancel"]:
                self._status(job, item, status="cancelled")
                return
            self._status(job, item, status="generating", error="")
        try:
            from .request_trace import recording_transport
            model = OfflineClient() if config["provider"] == "offline" else ModelClient(Settings(config["provider"], config["model"]), recording_transport(root / 'requests' / str(index)))
            pipeline = ImportPipeline(model, PublicMediaRegistry(), copy.deepcopy(catalog), prompts=prompts)
            note = pipeline.generate(item["word"], config["language"], config["audio"], config["image"], config["mode"], config["sources"])
            prefix = f"media/{index}"
            for group in ("pronunciation", "images"):
                note[group] = download_assets(MediaResult(**note[group]), root / prefix, relative_prefix=prefix).to_dict()
            if config["language"] == "en" and config["audio"] == "auto" and not note["pronunciation"]["assets"]:
                note["pronunciation"] = PublicMediaRegistry().english_audio(item["word"], root / prefix).to_dict()
            # Publish flat media paths compatible with existing previews/imports.
            for group in ("pronunciation", "images"):
                for asset in note[group]["assets"]:
                    filename = Path(asset["local_path"]).name
                    target = root / "media" / f"{index}-{filename}"
                    source = root / prefix / filename
                    if source.exists():
                        source.replace(target)
                    asset["local_path"] = "media/" + target.name
            write_json(root / f"{index}.json", note)
            (root / f"{index}.html").write_text(render_preview(note), encoding="utf-8")
            self._status(job, item, status="ready", tags=note["note_tags"], proposals=note.get("proposed_tags", []),
                         warnings=note["pronunciation"]["warnings"] + note["images"]["warnings"],
                         preview=f"/preview/{job_id}/{index}.html")
            if config["auto_import"] and not job["cancel"] and not note.get("proposed_tags"):
                self.import_item(job_id, index)
        except Exception as error:
            if item["status"] != "import_failed":
                safe = re.sub(r"sk-[A-Za-z0-9_-]+", "[redacted]", str(error))[:1200] if isinstance(error, (ValueError, RuntimeError)) else ""
                self._status(job, item, status="failed", error="生成失败。请检查网络、额度、prompt 格式或来源可用性，再重试。 " + safe)

    def run(self, job_id, prompts, catalog):
        job = self.jobs[job_id]
        with self.lock:
            job["status"] = "running"
            self.save(job)
        try:
            # Batches queue globally; each word owns clients, catalog and media.
            concurrency = validate_concurrency(job["config"].get("concurrency", DEFAULT_CONCURRENCY))
            with ThreadPoolExecutor(max_workers=concurrency, thread_name_prefix="vocab-word") as workers:
                futures = [workers.submit(self._generate_item, job_id, index, prompts, catalog)
                           for index, item in enumerate(job["items"]) if item["status"] == "queued"]
                for future in futures:
                    future.result()
        except Exception:
            for item in job["items"]:
                if item["status"] in ("queued", "generating"):
                    self._status(job, item, status="failed", error="任务初始化失败，请检查 prompt 配置后重试。")
        finally:
            with self.lock:
                job["status"] = "cancelled" if job["cancel"] else "complete"
                self.save(job)

    def retry(self, job_id):
        with self.lock:
            job = self.jobs[job_id]
            if job["status"] in ("running", "queued") or job.get("bulk_import", {}).get("status") in ("queued", "running"):
                raise ValueError("任务仍在运行。")
            root = self.directory / "jobs" / job_id
            saved = json.loads((root / "catalog.json").read_text(encoding="utf-8"))
            catalog = TagCatalog(saved["catalog"])
            catalog.snapshot = saved["snapshot"]
            for item in job["items"]:
                if item["status"] in ("failed", "cancelled"):
                    item.update(status="queued", error="")
            if not any(i["status"] == "queued" for i in job["items"]):
                raise ValueError("没有需要重新生成的词汇。")
            job.update(status="queued", cancel=False)
            self.save(job)
            self.pool.submit(self.run, job_id, json.loads((root / "prompts.json").read_text(encoding="utf-8")), catalog)

    def cancel(self, job_id):
        with self.lock:
            self.jobs[job_id]["cancel"] = True
            self.save(self.jobs[job_id])

    def import_all(self, job_id, deck=None, approve_new_tags=False):
        with self.lock:
            job = self.jobs[job_id]
            if job["status"] in ("queued", "running"):
                raise ValueError("请等本批生成结束后再全部导入。")
            if job["config"]["provider"] == "offline":
                raise ValueError("离线演示不能导入 Anki。")
            if type(approve_new_tags) is not bool:
                raise ValueError("新标签批准选项无效。")
            selected = deck or job["config"].get("deck", "")
            if not isinstance(selected, str) or not selected.strip() or len(selected) > 200:
                raise ValueError("请选择目标牌组。")
            if job.get("bulk_import", {}).get("status") in ("queued", "running"):
                return copy.deepcopy(job["bulk_import"])
            indices = [i for i, item in enumerate(job["items"])
                       if not item.get("note_id") and item["status"] in ("ready", "import_failed", "uncertain")]
            if not indices:
                raise ValueError("没有待导入的词卡。")
            if not approve_new_tags and any(job["items"][i].get("proposals") for i in indices):
                raise ValueError("本批含新标签，请选择一并批准新标签后全部导入。")
            job["bulk_import"] = {"status": "queued", "total": len(indices), "imported": 0, "failed": 0,
                                  "skipped": len(job["items"]) - len(indices), "deck": selected}
            self.save(job)
            self.pool.submit(self._import_all, job_id, indices, selected, approve_new_tags)
            return copy.deepcopy(job["bulk_import"])

    def _import_all(self, job_id, indices, deck, approve_new_tags):
        job = self.jobs[job_id]
        with self.lock:
            job["bulk_import"]["status"] = "running"
            self.save(job)
        try:
            for index in indices:
                try:
                    with self.lock:
                        item = job["items"][index]
                        if item.get("note_id"):
                            job["bulk_import"]["skipped"] += 1
                        else:
                            if item.get("proposals") and approve_new_tags:
                                self.approve_proposals(job_id, index, deck)
                            else:
                                self.import_item(job_id, index, deck)
                            job["bulk_import"]["imported"] += 1
                        self.save(job)
                except Exception:
                    with self.lock:
                        job["bulk_import"]["failed"] += 1
                        if item["status"] != "import_failed":
                            self._status(job, item, status="import_failed", error="批量导入失败，请检查标签、Anki 连接和目标牌组后重试。")
                        self.save(job)
        finally:
            with self.lock:
                job["bulk_import"]["status"] = "complete"
                self.save(job)

    def import_item(self, job_id, index, deck=None):
        # Serial import and run-id recovery prevent double-click/restart duplicates.
        with self.lock:
            job = self.jobs[job_id]
            if index < 0 or index >= len(job["items"]):
                raise ValueError("词卡不存在。")
            item = job["items"][index]
            if item.get("note_id"):
                return {"note_id": item["note_id"]}
            if item["status"] not in ("ready", "import_failed", "uncertain"):
                raise ValueError("请先完成词卡生成。")
            root = self.directory / "jobs" / job_id
            note = json.loads((root / f"{index}.json").read_text(encoding="utf-8"))
            if note["provenance"]["provider"] == "offline":
                raise ValueError("离线演示不能导入 Anki。")
            if note.get("proposed_tags") and note.get("proposal_review", {}).get("decision") != "approve":
                raise ValueError("新标签仍需审核；请选择批准新标签，或移除提案后导入。")
            selected = deck or job["config"]["deck"]
            if not selected:
                raise ValueError("请选择目标牌组。")
            run_id = note["provenance"]["run_id"]
            try:
                self._status(job, item, status="importing", error="")
                # Global text search works with both new Metadata and legacy 笔记 fields.
                existing = self.anki.invoke("findNotes", query='"' + run_id + '"')
                if len(existing) > 1:
                    raise ValueError("同一运行记录发现多个笔记，请在 Anki 中检查。")
                options = {}
                if note.get("proposed_tags"):
                    options["approved_proposals"] = [p["tag"] for p in note["proposed_tags"]]
                note_id = existing[0] if existing else self.anki.add_preview(note, selected, media_root=root, **options)
                self._status(job, item, status="imported", note_id=note_id, imported_deck=selected)
                return {"note_id": note_id}
            except Exception:
                self._status(job, item, status="import_failed", error="导入失败或结果待确认；重试会先核对 run_id，重复词条默认不新增。")
                raise ValueError(item["error"]) from None

    def reject_proposals(self, job_id, index):
        with self.lock:
            job = self.jobs[job_id]
            if index < 0 or index >= len(job["items"]):
                raise ValueError("词卡不存在。")
            item = job["items"][index]
            if item["status"] != "ready":
                raise ValueError("只能审核待导入的词卡。")
            root = self.directory / "jobs" / job_id
            path = root / f"{index}.json"
            note = json.loads(path.read_text(encoding="utf-8"))
            proposed = {p["tag"] for p in note.get("proposed_tags", [])}
            catalog = TagCatalog.from_anki(self.anki, self.metadata_path) if job["config"]["tag_source"] == "anki" else TagCatalog.load()
            for sense in note["senses"]:
                sense["tags"] = [t for t in sense["tags"] if t not in proposed]
                sense["tag_reasons"] = {t: r for t, r in sense["tag_reasons"].items() if t not in proposed}
                catalog.validate_sense(sense["tags"], note["language"])
            note["note_tags"] = sorted(set(t for s in note["senses"] for t in s["tags"]))
            note["assignments"] = [a for a in note["assignments"] if a["tag"] not in proposed]
            note["proposal_review"] = {"decision": "reject", "proposals": note.get("proposed_tags", [])}
            note["proposed_tags"] = []
            write_json(path, note)
            (root / f"{index}.html").write_text(render_preview(note), encoding="utf-8")
            self._status(job, item, tags=note["note_tags"], proposals=[])

    def approve_proposals(self, job_id, index, deck=None):
        with self.lock:
            job = self.jobs[job_id]
            if index < 0 or index >= len(job["items"]):
                raise ValueError("词卡不存在。")
            item = job["items"][index]
            if item["status"] not in ("ready", "import_failed", "uncertain"):
                raise ValueError("只能审核待导入的词卡。")
            root = self.directory / "jobs" / job_id
            path = root / f"{index}.json"
            note = json.loads(path.read_text(encoding="utf-8"))
            catalog = TagCatalog.from_anki(self.anki, self.metadata_path)
            proposals = note.get("proposed_tags", [])
            catalog.add_proposals([p for p in proposals if p["tag"] not in catalog.entries], note["language"])
            catalog.validate(note["note_tags"], note["language"])
            note["proposal_review"] = {"decision": "approve", "tags": [p["tag"] for p in proposals]}
            write_json(path, note)
            result = self.import_item(job_id, index, deck)
            # Once real tags exist, retain their reviewed descriptions for future batches.
            metadata_path = self.metadata_path
            metadata = json.loads(metadata_path.read_text(encoding="utf-8")) if metadata_path.exists() else {"tags": {}}
            for p in proposals:
                metadata["tags"][p["tag"]] = {"label_zh": p.get("label_zh", p["tag"]), "definition_zh": p["definition_zh"], "languages": [note["language"]]}
            write_json(metadata_path, metadata)
            self._status(job, item, proposals=[])
            return result
