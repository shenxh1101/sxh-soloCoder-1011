import pandas as pd
from datetime import datetime, date, time
from pathlib import Path
from typing import Optional, Dict, Set
import warnings

from .models import (
    AttendanceData, Employee, PunchRecord, LeaveRecord, LeaveType,
    BusinessTripRecord, OvertimeRecord, TimeAdjustmentRecord, LeaveBalance,
    AttendanceStatus, ImportResult, HolidayRecord, HolidayType
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

    def _check_required_columns(self, df_columns, required: Dict[str, list], result: ImportResult):
        missing = []
        for col_name, keywords in required.items():
            matched = self._match_column(df_columns, keywords)
            if matched is None:
                missing.append(col_name)
        if missing:
            result.missing_columns = missing
            result.failed_reasons.append(f"缺少必要列: {', '.join(missing)}")
            return False
        return True

    def _get_existing_keys(self, records, key_getter) -> Set:
        return {key_getter(r) for r in records}

    def import_employees(self, file_path: str) -> ImportResult:
        result = ImportResult(file_type="员工信息")
        df = self._read_file(file_path)
        result.total = len(df)

        required = {
            "工号": ["工号", "员工编号", "employee_id", "id"],
            "姓名": ["姓名", "name", "员工姓名"],
        }
        if not self._check_required_columns(df.columns, required, result):
            return result

        emp_id_col = self._match_column(df.columns, required["工号"])
        name_col = self._match_column(df.columns, required["姓名"])
        dept_col = self._match_column(df.columns, ["部门", "department", "dept"])
        pos_col = self._match_column(df.columns, ["职位", "岗位", "position", "title"])
        start_col = self._match_column(df.columns, ["上班时间", "工作开始", "work_start"])
        end_col = self._match_column(df.columns, ["下班时间", "工作结束", "work_end"])

        existing_keys = set(self.data.employees.keys())

        for idx, row in df.iterrows():
            try:
                emp_id = str(row.get(emp_id_col, "")).strip()
                name = str(row.get(name_col, "")).strip()
                if not emp_id or not name:
                    result.skipped += 1
                    result.failed_reasons.append(f"第{idx+2}行: 工号或姓名为空")
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

                if emp_id in existing_keys:
                    self.data.employees[emp_id] = employee
                    result.updated += 1
                    result.updated_keys.append(emp_id)
                else:
                    self.data.employees[emp_id] = employee
                    result.added += 1
                    result.new_keys.append(emp_id)

            except Exception as e:
                result.failed += 1
                result.failed_reasons.append(f"第{idx+2}行: {str(e)}")

        self.data.last_import_time = datetime.now()
        self.data.mark_data_dirty()
        return result

    def import_punches(self, file_path: str) -> ImportResult:
        result = ImportResult(file_type="打卡记录")
        df = self._read_file(file_path)
        result.total = len(df)

        required = {
            "工号": ["工号", "员工编号", "employee_id", "id"],
            "日期": ["日期", "date", "考勤日期"],
        }
        if not self._check_required_columns(df.columns, required, result):
            return result

        emp_id_col = self._match_column(df.columns, required["工号"])
        date_col = self._match_column(df.columns, required["日期"])
        punch_in_col = self._match_column(df.columns, ["上班打卡", "签到", "punch_in", "check_in", "上班时间"])
        punch_out_col = self._match_column(df.columns, ["下班打卡", "签退", "punch_out", "check_out", "下班时间"])
        status_col = self._match_column(df.columns, ["状态", "status", "考勤状态"])
        notes_col = self._match_column(df.columns, ["备注", "说明", "notes", "remark"])

        existing_keys = self._get_existing_keys(self.data.punch_records, lambda r: r.get_key())

        for idx, row in df.iterrows():
            try:
                emp_id = str(row.get(emp_id_col, "")).strip()
                punch_date = self._parse_date(row.get(date_col))
                if not emp_id or not punch_date:
                    result.skipped += 1
                    result.failed_reasons.append(f"第{idx+2}行: 工号或日期为空")
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

                key = record.get_key()
                if key in existing_keys:
                    for i, existing in enumerate(self.data.punch_records):
                        if existing.get_key() == key:
                            self.data.punch_records[i] = record
                            break
                    result.updated += 1
                    result.updated_keys.append(str(key))
                else:
                    self.data.punch_records.append(record)
                    result.added += 1
                    result.new_keys.append(str(key))

                if punch_date.year != self.data.year or punch_date.month != self.data.month:
                    if not self.data.year or not self.data.month:
                        self.data.set_month(punch_date.year, punch_date.month)

            except Exception as e:
                result.failed += 1
                result.failed_reasons.append(f"第{idx+2}行: {str(e)}")

        self.data.last_import_time = datetime.now()
        self.data.mark_data_dirty()
        return result

    def import_leaves(self, file_path: str) -> ImportResult:
        result = ImportResult(file_type="请假记录")
        df = self._read_file(file_path)
        result.total = len(df)

        required = {
            "工号": ["工号", "员工编号", "employee_id", "id"],
            "开始日期": ["开始日期", "start_date", "请假开始"],
            "结束日期": ["结束日期", "end_date", "请假结束"],
        }
        if not self._check_required_columns(df.columns, required, result):
            return result

        emp_id_col = self._match_column(df.columns, required["工号"])
        type_col = self._match_column(df.columns, ["假别", "请假类型", "leave_type", "类型"])
        start_col = self._match_column(df.columns, required["开始日期"])
        end_col = self._match_column(df.columns, required["结束日期"])
        days_col = self._match_column(df.columns, ["天数", "请假天数", "days"])
        start_time_col = self._match_column(df.columns, ["开始时间", "start_time"])
        end_time_col = self._match_column(df.columns, ["结束时间", "end_time"])
        reason_col = self._match_column(df.columns, ["原因", "事由", "reason", "请假原因"])
        approved_col = self._match_column(df.columns, ["审批状态", "是否批准", "approved", "状态"])

        existing_keys = self._get_existing_keys(self.data.leave_records, lambda r: r.get_key())

        for idx, row in df.iterrows():
            try:
                emp_id = str(row.get(emp_id_col, "")).strip()
                start_date = self._parse_date(row.get(start_col))
                end_date = self._parse_date(row.get(end_col))
                if not emp_id or not start_date or not end_date:
                    result.skipped += 1
                    result.failed_reasons.append(f"第{idx+2}行: 工号、开始日期或结束日期为空")
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

                key = record.get_key()
                if key in existing_keys:
                    for i, existing in enumerate(self.data.leave_records):
                        if existing.get_key() == key:
                            self.data.leave_records[i] = record
                            break
                    result.updated += 1
                    result.updated_keys.append(str(key))
                else:
                    self.data.leave_records.append(record)
                    result.added += 1
                    result.new_keys.append(str(key))

            except Exception as e:
                result.failed += 1
                result.failed_reasons.append(f"第{idx+2}行: {str(e)}")

        self.data.last_import_time = datetime.now()
        self.data.mark_data_dirty()
        return result

    def import_business_trips(self, file_path: str) -> ImportResult:
        result = ImportResult(file_type="出差记录")
        df = self._read_file(file_path)
        result.total = len(df)

        required = {
            "工号": ["工号", "员工编号", "employee_id", "id"],
            "开始日期": ["开始日期", "start_date", "出差开始"],
            "结束日期": ["结束日期", "end_date", "出差结束"],
        }
        if not self._check_required_columns(df.columns, required, result):
            return result

        emp_id_col = self._match_column(df.columns, required["工号"])
        start_col = self._match_column(df.columns, required["开始日期"])
        end_col = self._match_column(df.columns, required["结束日期"])
        days_col = self._match_column(df.columns, ["天数", "出差天数", "days"])
        location_col = self._match_column(df.columns, ["地点", "出差地点", "location", "目的地"])
        purpose_col = self._match_column(df.columns, ["目的", "事由", "purpose", "出差原因"])

        existing_keys = self._get_existing_keys(self.data.business_trip_records, lambda r: r.get_key())

        for idx, row in df.iterrows():
            try:
                emp_id = str(row.get(emp_id_col, "")).strip()
                start_date = self._parse_date(row.get(start_col))
                end_date = self._parse_date(row.get(end_col))
                if not emp_id or not start_date or not end_date:
                    result.skipped += 1
                    result.failed_reasons.append(f"第{idx+2}行: 工号、开始日期或结束日期为空")
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

                key = record.get_key()
                if key in existing_keys:
                    for i, existing in enumerate(self.data.business_trip_records):
                        if existing.get_key() == key:
                            self.data.business_trip_records[i] = record
                            break
                    result.updated += 1
                    result.updated_keys.append(str(key))
                else:
                    self.data.business_trip_records.append(record)
                    result.added += 1
                    result.new_keys.append(str(key))

            except Exception as e:
                result.failed += 1
                result.failed_reasons.append(f"第{idx+2}行: {str(e)}")

        self.data.last_import_time = datetime.now()
        self.data.mark_data_dirty()
        return result

    def import_overtime(self, file_path: str) -> ImportResult:
        result = ImportResult(file_type="加班记录")
        df = self._read_file(file_path)
        result.total = len(df)

        required = {
            "工号": ["工号", "员工编号", "employee_id", "id"],
            "日期": ["日期", "date", "加班日期"],
            "开始时间": ["开始时间", "start_time", "加班开始"],
            "结束时间": ["结束时间", "end_time", "加班结束"],
        }
        if not self._check_required_columns(df.columns, required, result):
            return result

        emp_id_col = self._match_column(df.columns, required["工号"])
        date_col = self._match_column(df.columns, required["日期"])
        start_col = self._match_column(df.columns, required["开始时间"])
        end_col = self._match_column(df.columns, required["结束时间"])
        hours_col = self._match_column(df.columns, ["时长", "加班时长", "hours", "小时"])
        reason_col = self._match_column(df.columns, ["原因", "事由", "reason", "加班原因"])
        approved_col = self._match_column(df.columns, ["审批状态", "是否批准", "approved", "状态"])

        existing_keys = self._get_existing_keys(self.data.overtime_records, lambda r: r.get_key())

        for idx, row in df.iterrows():
            try:
                emp_id = str(row.get(emp_id_col, "")).strip()
                overtime_date = self._parse_date(row.get(date_col))
                start_time = self._parse_time(row.get(start_col))
                end_time = self._parse_time(row.get(end_col))
                if not emp_id or not overtime_date or not start_time or not end_time:
                    result.skipped += 1
                    result.failed_reasons.append(f"第{idx+2}行: 工号、日期、开始时间或结束时间为空")
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

                key = record.get_key()
                if key in existing_keys:
                    for i, existing in enumerate(self.data.overtime_records):
                        if existing.get_key() == key:
                            self.data.overtime_records[i] = record
                            break
                    result.updated += 1
                    result.updated_keys.append(str(key))
                else:
                    self.data.overtime_records.append(record)
                    result.added += 1
                    result.new_keys.append(str(key))

            except Exception as e:
                result.failed += 1
                result.failed_reasons.append(f"第{idx+2}行: {str(e)}")

        self.data.last_import_time = datetime.now()
        self.data.mark_data_dirty()
        return result

    def import_time_adjustments(self, file_path: str) -> ImportResult:
        result = ImportResult(file_type="调休记录")
        df = self._read_file(file_path)
        result.total = len(df)

        required = {
            "工号": ["工号", "员工编号", "employee_id", "id"],
            "原日期": ["原日期", "original_date", "调整日期"],
            "调至日期": ["调至日期", "adjust_to_date", "目标日期"],
        }
        if not self._check_required_columns(df.columns, required, result):
            return result

        emp_id_col = self._match_column(df.columns, required["工号"])
        orig_date_col = self._match_column(df.columns, required["原日期"])
        type_col = self._match_column(df.columns, ["类型", "调整类型", "adjust_type"])
        to_date_col = self._match_column(df.columns, required["调至日期"])
        hours_col = self._match_column(df.columns, ["时长", "调整时长", "hours", "小时"])
        reason_col = self._match_column(df.columns, ["原因", "事由", "reason", "调整原因"])
        approved_col = self._match_column(df.columns, ["审批状态", "是否批准", "approved", "状态"])

        existing_keys = self._get_existing_keys(self.data.time_adjustment_records, lambda r: r.get_key())

        for idx, row in df.iterrows():
            try:
                emp_id = str(row.get(emp_id_col, "")).strip()
                original_date = self._parse_date(row.get(orig_date_col))
                adjust_to_date = self._parse_date(row.get(to_date_col))
                if not emp_id or not original_date or not adjust_to_date:
                    result.skipped += 1
                    result.failed_reasons.append(f"第{idx+2}行: 工号、原日期或调至日期为空")
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

                key = record.get_key()
                if key in existing_keys:
                    for i, existing in enumerate(self.data.time_adjustment_records):
                        if existing.get_key() == key:
                            self.data.time_adjustment_records[i] = record
                            break
                    result.updated += 1
                    result.updated_keys.append(str(key))
                else:
                    self.data.time_adjustment_records.append(record)
                    result.added += 1
                    result.new_keys.append(str(key))

            except Exception as e:
                result.failed += 1
                result.failed_reasons.append(f"第{idx+2}行: {str(e)}")

        self.data.last_import_time = datetime.now()
        self.data.mark_data_dirty()
        return result

    def import_leave_balances(self, file_path: str) -> ImportResult:
        result = ImportResult(file_type="假期余额")
        df = self._read_file(file_path)
        result.total = len(df)

        required = {
            "工号": ["工号", "员工编号", "employee_id", "id"],
        }
        if not self._check_required_columns(df.columns, required, result):
            return result

        emp_id_col = self._match_column(df.columns, required["工号"])
        type_col = self._match_column(df.columns, ["假别", "假期类型", "leave_type", "类型"])
        total_col = self._match_column(df.columns, ["总额", "总天数", "total_days", "应有"])
        used_col = self._match_column(df.columns, ["已用", "已休", "used_days", "已使用"])
        remain_col = self._match_column(df.columns, ["余额", "剩余", "remaining_days", "剩余天数"])

        existing_keys = set()
        for emp_id, balances in self.data.leave_balances.items():
            for lt in balances:
                existing_keys.add((emp_id, lt))

        for idx, row in df.iterrows():
            try:
                emp_id = str(row.get(emp_id_col, "")).strip()
                if not emp_id:
                    result.skipped += 1
                    result.failed_reasons.append(f"第{idx+2}行: 工号为空")
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

                key = balance.get_key()
                if key in existing_keys:
                    if emp_id not in self.data.leave_balances:
                        self.data.leave_balances[emp_id] = {}
                    self.data.leave_balances[emp_id][leave_type] = balance
                    result.updated += 1
                    result.updated_keys.append(str(key))
                else:
                    if emp_id not in self.data.leave_balances:
                        self.data.leave_balances[emp_id] = {}
                    self.data.leave_balances[emp_id][leave_type] = balance
                    result.added += 1
                    result.new_keys.append(str(key))

            except Exception as e:
                result.failed += 1
                result.failed_reasons.append(f"第{idx+2}行: {str(e)}")

        self.data.last_import_time = datetime.now()
        self.data.mark_data_dirty()
        return result

    def import_holidays(self, file_path: str) -> ImportResult:
        result = ImportResult(file_type="节假日设置")
        df = self._read_file(file_path)
        result.total = len(df)

        required = {
            "日期": ["日期", "date", "holiday_date"],
            "类型": ["类型", "type", "holiday_type", "节假日类型"],
        }
        if not self._check_required_columns(df.columns, required, result):
            return result

        date_col = self._match_column(df.columns, required["日期"])
        type_col = self._match_column(df.columns, required["类型"])
        name_col = self._match_column(df.columns, ["名称", "name", "节假日名称", "说明"])
        start_col = self._match_column(df.columns, ["上班时间", "工作开始", "work_start"])
        end_col = self._match_column(df.columns, ["下班时间", "工作结束", "work_end"])
        notes_col = self._match_column(df.columns, ["备注", "notes", "remark"])

        existing_keys = set(self.data.holidays.keys())

        for idx, row in df.iterrows():
            try:
                holiday_date = self._parse_date(row.get(date_col))
                type_str = str(row.get(type_col, "")).strip()
                if not holiday_date or not type_str:
                    result.skipped += 1
                    result.failed_reasons.append(f"第{idx+2}行: 日期或类型为空")
                    continue

                holiday_type = None
                for ht in HolidayType:
                    if ht.value in type_str or ht.name in type_str or type_str in ht.value:
                        holiday_type = ht
                        break
                if holiday_type is None:
                    result.failed += 1
                    result.failed_reasons.append(f"第{idx+2}行: 无法识别的节假日类型 '{type_str}'")
                    continue

                name = str(row.get(name_col, "")).strip() if name_col else ""
                work_start = self._parse_time(row.get(start_col)) if start_col else None
                work_end = self._parse_time(row.get(end_col)) if end_col else None
                notes = str(row.get(notes_col, "")).strip() if notes_col else ""

                record = HolidayRecord(
                    holiday_date=holiday_date,
                    holiday_type=holiday_type,
                    name=name,
                    work_start_time=work_start,
                    work_end_time=work_end,
                    notes=notes
                )

                if holiday_date in existing_keys:
                    self.data.holidays[holiday_date] = record
                    result.updated += 1
                    result.updated_keys.append(str(holiday_date))
                else:
                    self.data.holidays[holiday_date] = record
                    result.added += 1
                    result.new_keys.append(str(holiday_date))

            except Exception as e:
                result.failed += 1
                result.failed_reasons.append(f"第{idx+2}行: {str(e)}")

        self.data.last_import_time = datetime.now()
        self.data.mark_data_dirty()
        return result

    def import_file(self, file_path: str, file_type: str) -> ImportResult:
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
        elif file_type in ["holiday", "节假日", "holidays", "calendar", "日历"]:
            return self.import_holidays(file_path)
        else:
            raise ValueError(f"不支持的文件类型: {file_type}")
