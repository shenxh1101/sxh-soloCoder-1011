import pandas as pd
from datetime import datetime, date, time
from pathlib import Path
from typing import Optional
import warnings

from .models import (
    AttendanceData, Employee, PunchRecord, LeaveRecord, LeaveType,
    BusinessTripRecord, OvertimeRecord, TimeAdjustmentRecord, LeaveBalance,
    AttendanceStatus
)

warnings.filterwarnings("ignore")


class DataImporter:
    def __init__(self, attendance_data: AttendanceData):
        self.data = attendance_data

    def _read_file(self, file_path: str) -> pd.DataFrame:
        path = Path(file_path)
        if not path.exists():
            raise FileNotFoundError(f"文件不存在: {file_path}")

        if path.suffix.lower() in [".xlsx", ".xls"]:
            return pd.read_excel(path)
        elif path.suffix.lower() == ".csv":
            return pd.read_csv(path)
        else:
            raise ValueError(f"不支持的文件格式: {path.suffix}")

    def _parse_date(self, value) -> Optional[date]:
        if pd.isna(value) or value is None:
            return None
        if isinstance(value, date):
            return value
        if isinstance(value, datetime):
            return value.date()
        try:
            return pd.to_datetime(str(value)).date()
        except:
            return None

    def _parse_datetime(self, value) -> Optional[datetime]:
        if pd.isna(value) or value is None:
            return None
        if isinstance(value, datetime):
            return value
        try:
            return pd.to_datetime(str(value))
        except:
            return None

    def _parse_time(self, value) -> Optional[time]:
        if pd.isna(value) or value is None:
            return None
        if isinstance(value, time):
            return value
        try:
            dt = pd.to_datetime(str(value))
            return dt.time()
        except:
            try:
                parts = str(value).split(":")
                if len(parts) >= 2:
                    return time(int(parts[0]), int(parts[1]))
            except:
                pass
            return None

    def _parse_float(self, value) -> float:
        if pd.isna(value) or value is None:
            return 0.0
        try:
            return float(value)
        except:
            return 0.0

    def _parse_bool(self, value) -> bool:
        if pd.isna(value) or value is None:
            return True
        if isinstance(value, bool):
            return value
        return str(value).lower() in ["true", "是", "yes", "1", "批准", "通过"]

    def _match_column(self, df_columns, keywords):
        for col in df_columns:
            col_lower = str(col).lower()
            for kw in keywords:
                if kw.lower() in col_lower:
                    return col
        return None

    def import_employees(self, file_path: str) -> int:
        df = self._read_file(file_path)
        count = 0

        emp_id_col = self._match_column(df.columns, ["工号", "员工编号", "employee_id", "id"])
        name_col = self._match_column(df.columns, ["姓名", "name", "员工姓名"])
        dept_col = self._match_column(df.columns, ["部门", "department", "dept"])
        pos_col = self._match_column(df.columns, ["职位", "岗位", "position", "title"])
        start_col = self._match_column(df.columns, ["上班时间", "工作开始", "work_start"])
        end_col = self._match_column(df.columns, ["下班时间", "工作结束", "work_end"])

        for _, row in df.iterrows():
            emp_id = str(row.get(emp_id_col, "")).strip()
            name = str(row.get(name_col, "")).strip()
            if not emp_id or not name:
                continue

            department = str(row.get(dept_col, "")).strip() if dept_col else ""
            position = str(row.get(pos_col, "")).strip() if pos_col else ""
            work_start = self._parse_time(row.get(start_col)) or time(9, 0)
            work_end = self._parse_time(row.get(end_col)) or time(18, 0)

            employee = Employee(
                employee_id=emp_id,
                name=name,
                department=department,
                position=position,
                work_start_time=work_start,
                work_end_time=work_end
            )
            self.data.employees[emp_id] = employee
            count += 1

        return count

    def import_punches(self, file_path: str) -> int:
        df = self._read_file(file_path)
        count = 0

        emp_id_col = self._match_column(df.columns, ["工号", "员工编号", "employee_id", "id"])
        date_col = self._match_column(df.columns, ["日期", "date", "考勤日期"])
        punch_in_col = self._match_column(df.columns, ["上班打卡", "签到", "punch_in", "check_in", "上班时间"])
        punch_out_col = self._match_column(df.columns, ["下班打卡", "签退", "punch_out", "check_out", "下班时间"])
        status_col = self._match_column(df.columns, ["状态", "status", "考勤状态"])
        notes_col = self._match_column(df.columns, ["备注", "说明", "notes", "remark"])

        for _, row in df.iterrows():
            emp_id = str(row.get(emp_id_col, "")).strip()
            punch_date = self._parse_date(row.get(date_col))
            if not emp_id or not punch_date:
                continue

            punch_in = self._parse_datetime(row.get(punch_in_col)) if punch_in_col else None
            punch_out = self._parse_datetime(row.get(punch_out_col)) if punch_out_col else None

            status_str = str(row.get(status_col, "")).strip() if status_col else ""
            status = AttendanceStatus.NORMAL
            if "迟到" in status_str:
                status = AttendanceStatus.LATE
            elif "早退" in status_str:
                status = AttendanceStatus.EARLY_LEAVE
            elif "缺勤" in status_str or "旷工" in status_str:
                status = AttendanceStatus.ABSENT
            elif "漏打卡" in status_str:
                status = AttendanceStatus.MISSING_PUNCH
            elif "请假" in status_str:
                status = AttendanceStatus.ON_LEAVE
            elif "出差" in status_str:
                status = AttendanceStatus.BUSINESS_TRIP

            notes = str(row.get(notes_col, "")).strip() if notes_col else ""

            record = PunchRecord(
                employee_id=emp_id,
                punch_date=punch_date,
                punch_in=punch_in,
                punch_out=punch_out,
                status=status,
                notes=notes
            )
            self.data.punch_records.append(record)
            count += 1

            if punch_date.year != self.data.year:
                self.data.year = punch_date.year
            if punch_date.month != self.data.month:
                self.data.month = punch_date.month

        return count

    def import_leaves(self, file_path: str) -> int:
        df = self._read_file(file_path)
        count = 0

        emp_id_col = self._match_column(df.columns, ["工号", "员工编号", "employee_id", "id"])
        type_col = self._match_column(df.columns, ["假别", "请假类型", "leave_type", "类型"])
        start_col = self._match_column(df.columns, ["开始日期", "start_date", "请假开始"])
        end_col = self._match_column(df.columns, ["结束日期", "end_date", "请假结束"])
        days_col = self._match_column(df.columns, ["天数", "请假天数", "days"])
        start_time_col = self._match_column(df.columns, ["开始时间", "start_time"])
        end_time_col = self._match_column(df.columns, ["结束时间", "end_time"])
        reason_col = self._match_column(df.columns, ["原因", "事由", "reason", "请假原因"])
        approved_col = self._match_column(df.columns, ["审批状态", "是否批准", "approved", "状态"])

        for _, row in df.iterrows():
            emp_id = str(row.get(emp_id_col, "")).strip()
            start_date = self._parse_date(row.get(start_col))
            end_date = self._parse_date(row.get(end_col))
            if not emp_id or not start_date or not end_date:
                continue

            leave_type_str = str(row.get(type_col, "")).strip() if type_col else "年假"
            leave_type = LeaveType.ANNUAL
            for lt in LeaveType:
                if lt.value in leave_type_str or lt.name in leave_type_str:
                    leave_type = lt
                    break

            days = self._parse_float(row.get(days_col))
            if days == 0:
                days = (end_date - start_date).days + 1

            start_time = self._parse_time(row.get(start_time_col)) if start_time_col else None
            end_time = self._parse_time(row.get(end_time_col)) if end_time_col else None
            reason = str(row.get(reason_col, "")).strip() if reason_col else ""
            approved = self._parse_bool(row.get(approved_col)) if approved_col else True

            record = LeaveRecord(
                employee_id=emp_id,
                leave_type=leave_type,
                start_date=start_date,
                end_date=end_date,
                days=days,
                start_time=start_time,
                end_time=end_time,
                reason=reason,
                approved=approved
            )
            self.data.leave_records.append(record)
            count += 1

        return count

    def import_business_trips(self, file_path: str) -> int:
        df = self._read_file(file_path)
        count = 0

        emp_id_col = self._match_column(df.columns, ["工号", "员工编号", "employee_id", "id"])
        start_col = self._match_column(df.columns, ["开始日期", "start_date", "出差开始"])
        end_col = self._match_column(df.columns, ["结束日期", "end_date", "出差结束"])
        days_col = self._match_column(df.columns, ["天数", "出差天数", "days"])
        location_col = self._match_column(df.columns, ["地点", "出差地点", "location", "目的地"])
        purpose_col = self._match_column(df.columns, ["目的", "事由", "purpose", "出差原因"])

        for _, row in df.iterrows():
            emp_id = str(row.get(emp_id_col, "")).strip()
            start_date = self._parse_date(row.get(start_col))
            end_date = self._parse_date(row.get(end_col))
            if not emp_id or not start_date or not end_date:
                continue

            days = self._parse_float(row.get(days_col))
            if days == 0:
                days = (end_date - start_date).days + 1

            location = str(row.get(location_col, "")).strip() if location_col else ""
            purpose = str(row.get(purpose_col, "")).strip() if purpose_col else ""

            record = BusinessTripRecord(
                employee_id=emp_id,
                start_date=start_date,
                end_date=end_date,
                days=days,
                location=location,
                purpose=purpose
            )
            self.data.business_trip_records.append(record)
            count += 1

        return count

    def import_overtime(self, file_path: str) -> int:
        df = self._read_file(file_path)
        count = 0

        emp_id_col = self._match_column(df.columns, ["工号", "员工编号", "employee_id", "id"])
        date_col = self._match_column(df.columns, ["日期", "date", "加班日期"])
        start_col = self._match_column(df.columns, ["开始时间", "start_time", "加班开始"])
        end_col = self._match_column(df.columns, ["结束时间", "end_time", "加班结束"])
        hours_col = self._match_column(df.columns, ["时长", "加班时长", "hours", "小时"])
        reason_col = self._match_column(df.columns, ["原因", "事由", "reason", "加班原因"])
        approved_col = self._match_column(df.columns, ["审批状态", "是否批准", "approved", "状态"])

        for _, row in df.iterrows():
            emp_id = str(row.get(emp_id_col, "")).strip()
            overtime_date = self._parse_date(row.get(date_col))
            start_time = self._parse_time(row.get(start_col))
            end_time = self._parse_time(row.get(end_col))
            if not emp_id or not overtime_date or not start_time or not end_time:
                continue

            hours = self._parse_float(row.get(hours_col))
            if hours == 0:
                start_dt = datetime.combine(overtime_date, start_time)
                end_dt = datetime.combine(overtime_date, end_time)
                hours = (end_dt - start_dt).total_seconds() / 3600

            reason = str(row.get(reason_col, "")).strip() if reason_col else ""
            approved = self._parse_bool(row.get(approved_col)) if approved_col else True

            record = OvertimeRecord(
                employee_id=emp_id,
                overtime_date=overtime_date,
                start_time=start_time,
                end_time=end_time,
                hours=hours,
                reason=reason,
                approved=approved
            )
            self.data.overtime_records.append(record)
            count += 1

        return count

    def import_time_adjustments(self, file_path: str) -> int:
        df = self._read_file(file_path)
        count = 0

        emp_id_col = self._match_column(df.columns, ["工号", "员工编号", "employee_id", "id"])
        orig_date_col = self._match_column(df.columns, ["原日期", "original_date", "调整日期"])
        type_col = self._match_column(df.columns, ["类型", "调整类型", "adjust_type"])
        to_date_col = self._match_column(df.columns, ["调至日期", "adjust_to_date", "目标日期"])
        hours_col = self._match_column(df.columns, ["时长", "调整时长", "hours", "小时"])
        reason_col = self._match_column(df.columns, ["原因", "事由", "reason", "调整原因"])
        approved_col = self._match_column(df.columns, ["审批状态", "是否批准", "approved", "状态"])

        for _, row in df.iterrows():
            emp_id = str(row.get(emp_id_col, "")).strip()
            original_date = self._parse_date(row.get(orig_date_col))
            adjust_to_date = self._parse_date(row.get(to_date_col))
            if not emp_id or not original_date or not adjust_to_date:
                continue

            adjust_type = str(row.get(type_col, "调休")).strip() if type_col else "调休"
            hours = self._parse_float(row.get(hours_col))
            reason = str(row.get(reason_col, "")).strip() if reason_col else ""
            approved = self._parse_bool(row.get(approved_col)) if approved_col else True

            record = TimeAdjustmentRecord(
                employee_id=emp_id,
                original_date=original_date,
                adjust_type=adjust_type,
                adjust_to_date=adjust_to_date,
                hours=hours,
                reason=str(row.get(reason_col, "")).strip() if reason_col else "",
                approved=self._parse_bool(row.get(approved_col)) if approved_col else True
            )
            self.data.time_adjustment_records.append(record)
            count += 1

        return count

    def import_leave_balances(self, file_path: str) -> int:
        df = self._read_file(file_path)
        count = 0

        emp_id_col = self._match_column(df.columns, ["工号", "员工编号", "employee_id", "id"])
        type_col = self._match_column(df.columns, ["假别", "假期类型", "leave_type", "类型"])
        total_col = self._match_column(df.columns, ["总额", "总天数", "total_days", "应有"])
        used_col = self._match_column(df.columns, ["已用", "已休", "used_days", "已使用"])
        remain_col = self._match_column(df.columns, ["余额", "剩余", "remaining_days", "剩余天数"])

        for _, row in df.iterrows():
            emp_id = str(row.get(emp_id_col, "")).strip()
            if not emp_id:
                continue

            leave_type_str = str(row.get(type_col, "年假")).strip() if type_col else "年假"
            leave_type = LeaveType.ANNUAL
            for lt in LeaveType:
                if lt.value in leave_type_str or lt.name in leave_type_str:
                    leave_type = lt
                    break

            total_days = self._parse_float(row.get(total_col))
            used_days = self._parse_float(row.get(used_col))
            remaining_days = self._parse_float(row.get(remain_col))
            if remaining_days == 0 and total_days > 0:
                remaining_days = total_days - used_days

            balance = LeaveBalance(
                employee_id=emp_id,
                leave_type=leave_type,
                total_days=total_days,
                used_days=used_days,
                remaining_days=remaining_days
            )
            self.data.leave_balances[emp_id][leave_type] = balance
            count += 1

        return count

    def import_file(self, file_path: str, file_type: str) -> int:
        file_type = file_type.lower()
        if file_type in ["employee", "员工", "employees"]:
            return self.import_employees(file_path)
        elif file_type in ["punch", "打卡", "punches", "attendance"]:
            return self.import_punches(file_path)
        elif file_type in ["leave", "请假", "leaves"]:
            return self.import_leaves(file_path)
        elif file_type in ["trip", "出差", "business", "business_trip"]:
            return self.import_business_trips(file_path)
        elif file_type in ["overtime", "加班"]:
            return self.import_overtime(file_path)
        elif file_type in ["adjust", "调休", "adjustment", "time_adjustment"]:
            return self.import_time_adjustments(file_path)
        elif file_type in ["balance", "余额", "leave_balance"]:
            return self.import_leave_balances(file_path)
        else:
            raise ValueError(f"不支持的文件类型: {file_type}")
