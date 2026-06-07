from dataclasses import dataclass, field
from datetime import datetime, date, time
from enum import Enum
from typing import List, Optional, Dict
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


class CheckIssueType(str, Enum):
    LATE = "迟到"
    EARLY_LEAVE = "早退"
    MISSING_PUNCH = "漏打卡"
    LEAVE_CONFLICT = "假期冲突"
    CROSS_MONTH_SHIFT = "跨月班次"
    ABNORMAL_OVERTIME = "异常加班"
    LEAVE_BALANCE_INSUFFICIENT = "假期余额不足"


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


@dataclass
class BusinessTripRecord:
    employee_id: str
    start_date: date
    end_date: date
    days: float
    location: str = ""
    purpose: str = ""


@dataclass
class OvertimeRecord:
    employee_id: str
    overtime_date: date
    start_time: time
    end_time: time
    hours: float
    reason: str = ""
    approved: bool = True


@dataclass
class TimeAdjustmentRecord:
    employee_id: str
    original_date: date
    adjust_type: str
    adjust_to_date: date
    hours: float
    reason: str = ""
    approved: bool = True


@dataclass
class LeaveBalance:
    employee_id: str
    leave_type: LeaveType
    total_days: float
    used_days: float
    remaining_days: float


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


@dataclass
class DepartmentSummary:
    department: str
    employee_count: int
    total_attendance_days: float
    total_absence_count: int
    total_overtime_hours: float
    average_attendance_rate: float
    employees_needing_confirmation: List[str] = field(default_factory=list)


@dataclass
class EmployeeSummary:
    employee_id: str
    name: str
    department: str
    attendance_days: float
    absence_count: int
    overtime_hours: float
    late_count: int
    early_leave_count: int
    missing_punch_count: int
    leave_days: Dict[str, float] = field(default_factory=dict)
    business_trip_days: float = 0.0
    issues: List[CheckIssue] = field(default_factory=list)


@dataclass
class AttendanceData:
    employees: Dict[str, Employee] = field(default_factory=dict)
    punch_records: List[PunchRecord] = field(default_factory=list)
    leave_records: List[LeaveRecord] = field(default_factory=list)
    business_trip_records: List[BusinessTripRecord] = field(default_factory=list)
    overtime_records: List[OvertimeRecord] = field(default_factory=list)
    time_adjustment_records: List[TimeAdjustmentRecord] = field(default_factory=list)
    leave_balances: Dict[str, Dict[LeaveType, LeaveBalance]] = field(default_factory=lambda: defaultdict(dict))
    check_issues: List[CheckIssue] = field(default_factory=list)
    month: int = 0
    year: int = 0

    def get_employee(self, employee_id: str) -> Optional[Employee]:
        return self.employees.get(employee_id)

    def get_employee_punches(self, employee_id: str) -> List[PunchRecord]:
        return [p for p in self.punch_records if p.employee_id == employee_id]

    def get_employee_leaves(self, employee_id: str) -> List[LeaveRecord]:
        return [l for l in self.leave_records if l.employee_id == employee_id]

    def get_employee_business_trips(self, employee_id: str) -> List[BusinessTripRecord]:
        return [b for b in self.business_trip_records if b.employee_id == employee_id]

    def get_employee_overtimes(self, employee_id: str) -> List[OvertimeRecord]:
        return [o for o in self.overtime_records if o.employee_id == employee_id]

    def get_employee_leave_balance(self, employee_id: str) -> Dict[LeaveType, LeaveBalance]:
        return self.leave_balances.get(employee_id, {})
