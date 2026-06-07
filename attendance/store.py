import pickle
from pathlib import Path
from datetime import date, datetime
from typing import Optional, Dict, List
import json

from .models import AttendanceData


class DataStore:
    def __init__(self, base_dir: str = "./.attendance_data"):
        self.base_dir = Path(base_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        self.current_month_file = self.base_dir / "current_month.json"
        self.metadata_file = self.base_dir / "metadata.json"

    def _get_month_path(self, month_str: str) -> Path:
        return self.base_dir / f"{month_str}.pkl"

    def list_available_months(self) -> List[str]:
        months = []
        for f in self.base_dir.glob("*.pkl"):
            month_str = f.stem
            if len(month_str) == 7 and month_str[4] == '-':
                months.append(month_str)
        return sorted(months, reverse=True)

    def get_current_month(self) -> Optional[str]:
        if self.current_month_file.exists():
            try:
                with open(self.current_month_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                    return data.get("current_month")
            except:
                return None
        return None

    def set_current_month(self, month_str: str) -> None:
        with open(self.current_month_file, "w", encoding="utf-8") as f:
            json.dump({"current_month": month_str, "updated_at": datetime.now().isoformat()}, f, ensure_ascii=False)

    def get_month_data_path(self, month_str: str) -> Path:
        return self._get_month_path(month_str)

    def save(self, data: AttendanceData) -> None:
        if data.month_str:
            month_str = data.month_str
        else:
            current = self.get_current_month()
            month_str = current or f"{datetime.now().year}-{datetime.now().month:02d}"
            data.set_month(*map(int, month_str.split('-')))

        path = self._get_month_path(month_str)
        self.base_dir.mkdir(parents=True, exist_ok=True)
        with open(path, "wb") as f:
            pickle.dump(data, f)

        self.set_current_month(data.month_str)
        self._update_metadata(data.month_str)

    def load(self, month_str: Optional[str] = None) -> Optional[AttendanceData]:
        if not month_str:
            month_str = self.get_current_month()

        if not month_str:
            return None

        path = self._get_month_path(month_str)
        if not path.exists():
            return None

        with open(path, "rb") as f:
            data = pickle.load(f)

        return data

    def load_or_create(self, month_str: str) -> AttendanceData:
        data = self.load(month_str)
        if data is None:
            data = AttendanceData()
            data.set_month(*map(int, month_str.split('-')))
            self.save(data)
        return data

    def clear_month(self, month_str: Optional[str] = None) -> bool:
        if not month_str:
            month_str = self.get_current_month()

        if not month_str:
            return False

        path = self._get_month_path(month_str)
        if path.exists():
            path.unlink()

            available = self.list_available_months()
            if available:
                self.set_current_month(available[0])
            else:
                if self.current_month_file.exists():
                    self.current_month_file.unlink()

            return True
        return False

    def clear_all(self) -> int:
        count = 0
        for f in self.base_dir.glob("*.pkl"):
            f.unlink()
            count += 1

        if self.current_month_file.exists():
            self.current_month_file.unlink()
        if self.metadata_file.exists():
            self.metadata_file.unlink()

        return count

    def delete_month(self, month_str: str) -> bool:
        path = self._get_month_path(month_str)
        if path.exists():
            path.unlink()

            current = self.get_current_month()
            if current == month_str:
                available = self.list_available_months()
                if available:
                    self.set_current_month(available[0])
                else:
                    if self.current_month_file.exists():
                        self.current_month_file.unlink()

            return True
        return False

    def exists(self, month_str: Optional[str] = None) -> bool:
        if not month_str:
            month_str = self.get_current_month()
        if not month_str:
            return False
        return self._get_month_path(month_str).exists()

    def copy_month(self, source_month: str, target_month: str, overwrite: bool = False) -> bool:
        source_path = self._get_month_path(source_month)
        target_path = self._get_month_path(target_month)

        if not source_path.exists():
            return False

        if target_path.exists() and not overwrite:
            return False

        data = self.load(source_month)
        if data:
            data.set_month(*map(int, target_month.split('-')))
            self.save(data)
            return True
        return False

    def _update_metadata(self, month_str: str) -> None:
        metadata = {}
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, "r", encoding="utf-8") as f:
                    metadata = json.load(f)
            except:
                metadata = {}

        months_data = metadata.get("months", {})
        months_data[month_str] = {
            "last_updated": datetime.now().isoformat(),
            "last_check": datetime.now().isoformat()
        }
        metadata["months"] = months_data
        metadata["last_updated"] = datetime.now().isoformat()

        with open(self.metadata_file, "w", encoding="utf-8") as f:
            json.dump(metadata, f, ensure_ascii=False, indent=2)

    def get_metadata(self) -> Dict:
        if self.metadata_file.exists():
            try:
                with open(self.metadata_file, "r", encoding="utf-8") as f:
                    return json.load(f)
            except:
                return {}
        return {}

    def get_month_info(self, month_str: str) -> Dict:
        metadata = self.get_metadata()
        months_data = metadata.get("months", {})
        info = months_data.get(month_str, {})

        data = self.load(month_str)
        if data:
            info.update({
                "year": data.year,
                "month": data.month,
                "employees": len(data.employees),
                "punch_records": len(data.punch_records),
                "leave_records": len(data.leave_records),
                "business_trips": len(data.business_trip_records),
                "overtime_records": len(data.overtime_records),
                "adjustment_records": len(data.time_adjustment_records),
                "leave_balances": sum(len(v) for v in data.leave_balances.values()),
                "check_issues": len(data.check_issues),
                "last_import": data.last_import_time.isoformat() if data.last_import_time else None,
                "last_check": data.last_check_time.isoformat() if data.last_check_time else None,
                "check_dirty": data.check_dirty,
            })

        return info

    def switch_month(self, month_str: str) -> AttendanceData:
        data = self.load_or_create(month_str)
        self.set_current_month(month_str)
        return data

    def get_all_months_info(self) -> List[Dict]:
        months = self.list_available_months()
        result = []
        for month in months:
            info = self.get_month_info(month)
            info["month"] = month
            info["is_current"] = (month == self.get_current_month())
            result.append(info)
        return result
