import json
from pathlib import Path
from datetime import date, datetime


class JSONStore:
    def __init__(self, base_dir: str | Path):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def save(self, filename: str, data: dict | list):
        path = self.base_dir / filename
        with open(path, "w") as f:
            json.dump(data, f, indent=2, default=self._json_serializer)

    def load(self, filename: str) -> dict | list | None:
        path = self.base_dir / filename
        if not path.exists():
            return None
        with open(path, "r") as f:
            return json.load(f)

    def load_or_default(self, filename: str, default: dict | list) -> dict | list:
        result = self.load(filename)
        return result if result is not None else default

    def list_files(self, pattern: str = "*.json") -> list[Path]:
        return sorted(self.base_dir.glob(pattern))

    def delete(self, filename: str):
        path = self.base_dir / filename
        if path.exists():
            path.unlink()

    @staticmethod
    def _json_serializer(obj):
        if isinstance(obj, (date, datetime)):
            return obj.isoformat()
        raise TypeError(f"Not JSON serializable: {type(obj)}")
