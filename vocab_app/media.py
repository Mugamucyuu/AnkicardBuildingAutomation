"""Selectable media-source contracts. Network adapters remain explicit pending work."""
from dataclasses import asdict, dataclass, field

SOURCES = {
    "none": {"languages": ["en", "ja", "ko"], "status": "available"},
    "wiktionary": {"languages": ["en", "ja", "ko"], "status": "planned"},
    "ojad": {"languages": ["ja"], "status": "available"},
    "kanjium": {"languages": ["ja"], "status": "available"},
    "ubiq": {"languages": ["ja"], "status": "available"},
    "krdict": {"languages": ["ko"], "status": "available"},
    "daum": {"languages": ["ko"], "status": "available"},
    "cambridge": {"languages": ["en"], "status": "available"},
    "oxford": {"languages": ["en"], "status": "available"},
    "longman": {"languages": ["en"], "status": "available"},
    "free_dictionary": {"languages": ["en"], "status": "available"},
    "commons": {"languages": ["en", "ja", "ko"], "status": "available"},
}

@dataclass
class MediaAsset:
    kind: str
    url: str
    source_page: str
    attribution: str
    license: str
    variety: str = ""

@dataclass
class MediaResult:
    pronunciation_text: str = ""
    pronunciation_system: str = ""
    assets: list = field(default_factory=list)
    warnings: list = field(default_factory=list)
    pitch_accents: list = field(default_factory=list)
    lookup_attempts: list = field(default_factory=list)
    selection: dict = field(default_factory=dict)
    phonetic_hangul: list = field(default_factory=list)

    def to_dict(self):
        return asdict(self)

class MediaRegistry:
    def select_image(self, word, language, senses, plan):
        return MediaResult(warnings=["当前媒体接口未启用按词义配图。"])

    def lookup(self, source, language, word):
        if source not in SOURCES or language not in SOURCES[source]["languages"]:
            raise ValueError("媒体来源不存在或不支持当前语言。")
        if source == "none":
            return MediaResult(warnings=["未启用外部媒体；AI 生成的读音不作为已核验发音。"])
        return MediaResult(warnings=[source + " 接口尚未接入，本次不获取音频或图片。"])
