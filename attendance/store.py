import pickle
import json
from pathlib import Path
from datetime import date, datetime
from typing import Optional

from .models import AttendanceData


class DataStore:
    def __init__(self, store_path: str = "./.attendance_store.pkl"):
        self.store_path = Path(store_path)

    def save(self, data: AttendanceData) -> None:
        self.store_path.parent.mkdir(parents=True, exist_ok=True)
        with open(self.store_path, "wb") as f:
            pickle.dump(data, f)

    def load(self) -> Optional[AttendanceData]:
        if not self.store_path.exists():
            return None
        with open(self.store_path, "rb") as f:
            return pickle.load(f)

    def clear(self) -> None:
        if self.store_path.exists():
            self.store_path.unlink()

    def exists(self) -> bool:
        return self.store_path.exists()
