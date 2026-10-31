from pathlib import Path

STUDIO = Path(__file__).resolve().parent
REPO = STUDIO.parent
TEXTS = REPO / "texts"
SESSIONS = REPO / "sessions"
READER = REPO / "reader"

MODELS_JSON = STUDIO / "models.json"
LOCAL_JSON = STUDIO / "local.json"  # git-ignored: your own checkpoints
SETTINGS_JSON = STUDIO / "settings.json"  # git-ignored: default live/final model
