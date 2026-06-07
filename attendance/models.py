from dataclasses import dataclass, field
from datetime import datetime, date, time
from enum import Enum
from typing import List, Optional, Dict, Tuple
from collections import defaultdict


class LeaveType(str, Enum):
    ANNUAL = "年假"
    SICK = "病假"
    PERSONAL = "事假"
    MARRIAGE = "婚假"
    MATERNITY = "产假"
    PATERNITY = "陪产假"
    BEREAVEMENT = "丧假"
    OTHER = "其他"


class AttendanceStatus(str, Enum):
    NORMAL = "正常"
    LATE = "迟到"
    EARLY_LEAVE = "早退"
    ABSENT = "缺勤"
    MISSING_PUNCH = "漏打卡"
    ON_LEAVE = "请假"
    BUSINESS_TRIP = "出差"
    WEEKEND = "周末"
    HOLIDAY = "节假日"
    SPECIAL_SHIFT = "特殊班次"


class CheckIssueType(str, Enum):
    LATE = "迟到"
    EARLY_LEAVE = "早退"
    MISSING_PUNCH = "漏打卡"
    LEAVE_CONFLICT = "假期冲突"
    CROSS_MONTH_SHIFT = "跨月班次"
    ABNORMAL_OVERTIME = "异常加班"
    LEAVE_BALANCE_INSUFFICIENT = "假期余额不足"


class HolidayType(str, Enum):
    HOLIDAY = "法定节假日"
    WEEKEND_ADJUST = "周末调休"
    SPECIAL_WORKDAY = "特殊工作日"
    COMPANY_HOLIDAY = "公司假期"


@dataclass
class HolidayRecord:
    holiday_date: date
    holiday_type: HolidayType
    name: str = ""
    work_start_time: Optional[time] = None
    work_end_time: Optional[time] = None
    notes: str = ""


@dataclass
class ImportResult:
    file_type: str
    total: int = 0
    added: int = 0
    updated: int = 0
    skipped: int = 0
    failed: int = 0
    failed_reasons: List[str] = field(default_factory=list)
    duplicate_keys: List[str] = field(default_factory=list)
    missing_columns: List[str] = field(default_factory=list)
    new_keys: List[str] = field(default_factory=list)
    updated_keys: List[str] = field(default_factory=list)

    def merge(self, other: "ImportResult"):
        self.total += other.total
        self.added += other.added
        self.updated += other.updated
        self.skipped += other.skipped
        self.failed += other.failed
        self.failed_reasons.extend(other.failed_reasons)
        self.duplicate_keys.extend(other.duplicate_keys)
        self.missing_columns.extend(other.missing_columns)
        self.new_keys.extend(other.new_keys)
        self.updated_keys.extend(other.updated_keys)


@dataclass
class Employee:
    employee_id: str
    name: str
    department: str
    position: str = ""
    work_start_time: time = time(9, 0)
    work_end_time: time = time(18, 0)
    daily_standard_hours: float = 8.0


@dataclass
class PunchRecord:
    employee_id: str
    punch_date: date
    punch_in: Optional[datetime] = None
    punch_out: Optional[datetime] = None
    status: AttendanceStatus = AttendanceStatus.NORMAL
    notes: str = ""

    def get_key(self) -> Tuple[str, date]:
        return (self.employee_id, self.punch_date)


@dataclass
class LeaveRecord:
    employee_id: str
    leave_type: LeaveType
    start_date: date
    end_date: date
    days: float
    start_time: Optional[time] = None
    end_time: Optional[time] = None
    reason: str = ""
    approved: bool = True

    def get_key(self) -> Tuple[str, LeaveType, date, date]:
        return (self.employee_id, self.leave_type, self.start_date, self.end_date)


@dataclass
class BusinessTripRecord:
    employee_id: str
    start_date: date
    end_date: date
    days: float
    location: str = ""
    purpose: str = ""

    def get_key(self) -> Tuple[str, date, date]:
        return (self.employee_id, self.start_date, self.end_date)


@dataclass
class OvertimeRecord:
    employee_id: str
    overtime_date: date
    start_time: time
    end_time: time
    hours: float
    reason: str = ""
    approved: bool = True

    def get_key(self) -> Tuple[str, date, time, time]:
        return (self.employee_id, self.overtime_date, self.start_time, self.end_time)


@dataclass
class TimeAdjustmentRecord:
    employee_id: str
    original_date: date
    adjust_type: str
    adjust_to_date: date
    hours: float
    reason: str = ""
    approved: bool = True

    def get_key(self) -> Tuple[str, date, str, date]:
        return (self.employee_id, self.original_date, self.adjust_type, self.adjust_to_date)


@dataclass
class LeaveBalance:
    employee_id: str
    leave_type: LeaveType
    total_days: float
    used_days: float
    remaining_days: float

    def get_key(self) -> Tuple[str, LeaveType]:
        return (self.employee_id, self.leave_type)


@dataclass
class CheckIssue:
    employee_id: str
    employee_name: str
    department: str
    issue_type: CheckIssueType
    issue_date: date
    description: str
    severity: str = "warning"
    needs_confirmation: bool = False
    deadline: Optional[date] = None

    def get_key(self) -> Tuple[str, CheckIssueType, date]:
        return (self.employee_id, self.issue_type, self.issue_date)


@dataclass
class DepartmentSummary:
    department: str
    employee_count: int
    total_attendance_days: float
    total_absence_count: int
    total_overtime_hours: float
    average_attendance_rate: float
    standard_workdays: int = 0
    employees_needing_confirmation: List[str] = field(default_factory=list)


@dataclass
class EmployeeSummary:
    employee_id: str
    name: str
    department: str
    standard_workdays: int
    attendance_days: float
    absence_count: int
    overtime_hours: float
    late_count: int
    early_leave_count: int
    missing_punch_count: int
    leave_days: Dict[str, float] = field(default_factory=dict)
    business_trip_days: float = 0.0
    issues: List[CheckIssue] = field(default_factory=list)
    issue_summary: Dict[str, int] = field(default_factory=dict)
    needs_confirmation: bool = False


@dataclass
class AttendanceData:
    month: int = 0
    year: int = 0
    month_str: str = ""

    employees: Dict[str, Employee] = field(default_factory=dict)
    punch_records: List[PunchRecord] = field(default_factory=list)
    leave_records: List[LeaveRecord] = field(default_factory=list)
    business_trip_records: List[BusinessTripRecord] = field(default_factory=list)
    overtime_records: List[OvertimeRecord] = field(default_factory=list)
    time_adjustment_records: List[TimeAdjustmentRecord] = field(default_factory=list)
    leave_balances: Dict[str, Dict[LeaveType, LeaveBalance]] = field(default_factory=lambda: defaultdict(dict))
    check_issues: List[CheckIssue] = field(default_factory=list)
    holidays: Dict[date, HolidayRecord] = field(default_factory=dict)

    last_import_time: Optional[datetime] = None
    last_check_time: Optional[datetime] = None
    check_dirty: bool = True
    data_dirty: bool = False

    def set_month(self, year: int, month: int):
        self.year = year
        self.month = month
        self.month_str = f"{year}-{month:02d}"

    def is_in_month(self, d: date) -> bool:
        return d.year == self.year and d.month == self.month

    def get_standard_workdays(self) -> int:
        if self.year == 0 or self.month == 0:
            return 0

        import calendar
        cal = calendar.Calendar()
        count = 0
        for day in cal.itermonthdays(self.year, self.month):
            if day == 0:
                continue
            d = date(self.year, self.month, day)

            if d in self.holidays:
                holiday = self.holidays[d]
                if holiday.holiday_type in [HolidayType.HOLIDAY, HolidayType.WEEKEND_ADJUST, HolidayType.COMPANY_HOLIDAY]:
                    continue
                elif holiday.holiday_type == HolidayType.SPECIAL_WORKDAY:
                    count += 1
                    continue

            if d.weekday() < 5:
                count += 1

        return count

    def is_workday(self, d: date) -> bool:
        if d in self.holidays:
            holiday = self.holidays[d]
            if holiday.holiday_type in [HolidayType.HOLIDAY, HolidayType.WEEKEND_ADJUST, HolidayType.COMPANY_HOLIDAY]:
                return False
            elif holiday.holiday_type == HolidayType.SPECIAL_WORKDAY:
                return True

        return d.weekday() < 5

    def is_holiday(self, d: date) -> bool:
        if d in self.holidays:
            holiday = self.holidays[d]
            return holiday.holiday_type in [HolidayType.HOLIDAY, HolidayType.WEEKEND_ADJUST, HolidayType.COMPANY_HOLIDAY]
        return False

    def get_employee(self, employee_id: str) -> Optional[Employee]:
        return self.employees.get(employee_id)

    def get_employee_punches(self, employee_id: str, month_only: bool = True) -> List[PunchRecord]:
        punches = [p for p in self.punch_records if p.employee_id == employee_id]
        if month_only and self.year and self.month:
            punches = [p for p in punches if self.is_in_month(p.punch_date)]
        return punches

    def get_employee_leaves(self, employee_id: str, month_only: bool = True) -> List[LeaveRecord]:
        leaves = [l for l in self.leave_records if l.employee_id == employee_id]
        if month_only and self.year and self.month:
            leaves = [l for l in leaves if self.is_in_month(l.start_date) or self.is_in_month(l.end_date)]
        return leaves

    def get_employee_business_trips(self, employee_id: str, month_only: bool = True) -> List[BusinessTripRecord]:
        trips = [b for b in self.business_trip_records if b.employee_id == employee_id]
        if month_only and self.year and self.month:
            trips = [b for b in trips if self.is_in_month(b.start_date) or self.is_in_month(b.end_date)]
        return trips

    def get_employee_overtimes(self, employee_id: str, month_only: bool = True) -> List[OvertimeRecord]:
        overtimes = [o for o in self.overtime_records if o.employee_id == employee_id]
        if month_only and self.year and self.month:
            overtimes = [o for o in overtimes if self.is_in_month(o.overtime_date)]
        return overtimes

    def get_employee_leave_balance(self, employee_id: str) -> Dict[LeaveType, LeaveBalance]:
        return self.leave_balances.get(employee_id, {})

    def get_month_punches(self) -> List[PunchRecord]:
        if not self.year or not self.month:
            return self.punch_records
        return [p for p in self.punch_records if self.is_in_month(p.punch_date)]

    def get_month_leaves(self) -> List[LeaveRecord]:
        if not self.year or not self.month:
            return self.leave_records
        return [l for l in self.leave_records if self.is_in_month(l.start_date) or self.is_in_month(l.end_date)]

    def get_month_business_trips(self) -> List[BusinessTripRecord]:
        if not self.year or not self.month:
            return self.business_trip_records
        return [b for b in self.business_trip_records if self.is_in_month(b.start_date) or self.is_in_month(b.end_date)]

    def get_month_overtimes(self) -> List[OvertimeRecord]:
        if not self.year or not self.month:
            return self.overtime_records
        return [o for o in self.overtime_records if self.is_in_month(o.overtime_date)]

    def get_month_issues(self) -> List[CheckIssue]:
        if not self.year or not self.month:
            return self.check_issues
        return [i for i in self.check_issues if self.is_in_month(i.issue_date)]

    def mark_data_dirty(self):
        self.data_dirty = True
        self.check_dirty = True

    def mark_check_done(self):
        self.last_check_time = datetime.now()
        self.check_dirty = False
        self.data_dirty = False

    def clear_check_results(self):
        self.check_issues.clear()
        self.check_dirty = True

    def has_data(self) -> bool:
        return len(self.employees) > 0

    def has_any_records(self) -> bool:
        return (len(self.punch_records) > 0 or
                len(self.leave_records) > 0 or
                len(self.business_trip_records) > 0 or
                len(self.overtime_records) > 0 or
                len(self.time_adjustment_records) > 0 or
                len(self.leave_balances) > 0)
