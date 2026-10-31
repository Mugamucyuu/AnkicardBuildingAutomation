"""Public settings only. Secrets are read solely at the provider boundary."""
import os
from dataclasses import dataclass
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE_ROOT = Path(__file__).resolve().parent
RESOURCE_ROOT = PACKAGE_ROOT / "resources"

def user_data_dir():
    """Writable state is independent of the installation directory and cwd."""
    override = os.getenv("ANKICARD_DATA_DIR")
    if override:
        return Path(override).expanduser().resolve()
    if os.name == "nt":
        base = Path(os.getenv("LOCALAPPDATA") or Path.home() / "AppData/Local")
    else:
        base = Path(os.getenv("XDG_DATA_HOME") or Path.home() / ".local/share")
    return base / "AnkicardBuildingAutomation"

@dataclass(frozen=True)
class Settings:
    provider: str = "deepseek"
    model: str = ""
    timeout: int = 180
    max_output_tokens: int = 4096

    @classmethod
    def from_env(cls, provider=None, model=None):
        selected = provider or os.getenv("ANKI_AI_PROVIDER", "deepseek")
        if selected not in ("deepseek", "openai"):
            raise ValueError("模型来源只能是 deepseek 或 openai。")
        return cls(selected, model or os.getenv(selected.upper() + "_MODEL", ""))

    def require_model(self):
        if not self.model.strip():
            raise ValueError("请设置 " + self.provider.upper() + "_MODEL，或传入 --model。")
