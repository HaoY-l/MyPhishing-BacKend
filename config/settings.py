import json
from pathlib import Path

# 项目根目录（无论从哪里启动都不会错）
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_FILE = BASE_DIR / "config" / "config.json"

_CONFIG = None


def _load_config():
    global _CONFIG
    if _CONFIG is None:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            _CONFIG = json.load(f)
    return _CONFIG


def get_bool(key: str, default: bool = False) -> bool:
    cfg = _load_config()
    return bool(cfg.get(key, default))
