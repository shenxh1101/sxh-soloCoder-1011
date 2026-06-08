from datetime import datetime, date, time, timedelta
from typing import List, Dict, Tuple
from collections import defaultdict

from .models import (
    AttendanceData, CheckIssue, CheckIssueType, AttendanceStatus,
    LeaveType, PunchRecord, LeaveRecord, BusinessTripRecord
)


class AttendanceChecker:
    def __init__(self, attendance_data: AttendanceData):
        self.data = attendance_data
        self.late_tolerance_minutes = 5
        self.early_leave_tolerance_minutes = 5
        self.max_overtime_hours = 4.0
        self.max_daily_overtime_hours = 8.0

    def _get_employee_name(self, employee_id: str) -> str:
        emp = self.data.get_employee(employee_id)
        return emp.name if emp else employee_id

    def _get_employee_department(self, employee_id: str) -> str:
        emp = self.data.get_employee(employee_id)
        return emp.department if emp else ""

    def _add_issue(self, employee_id: str, issue_type: CheckIssueType,
                   issue_date: date, description: str,
                   severity: str = "warning", needs_confirmation: bool = False):
        issue = CheckIssue(
            employee_id=employee_id,
            employee_name=self._get_employee_name(employee_id),
            department=self._get_employee_department(employee_id),
            issue_type=issue_type,
            issue_date=issue_date,
            description=description,
            severity=severity,
            needs_confirmation=needs_confirmation,
            deadline=issue_date + timedelta(days=3)
        )
        self.data.check_issues.append(issue)

    def check_late_arrival(self) -> int:
        count = 0
        punches = self.data.get_month_punches()
        for punch in punches:
            if punch.status in [AttendanceStatus.ON_LEAVE, AttendanceStatus.BUSINESS_TRIP]:
                continue
            if punch.status == AttendanceStatus.LATE:
                emp = self.data.get_employee(punch.employee_id)
                if not emp or not punch.punch_in:
                    continue

                work_start = datetime.combine(punch.punch_date, emp.work_start_time)
                late_minutes = (punch.punch_in - work_start).total_seconds() / 60

                if late_minutes > self.late_tolerance_minutes:
                    self._add_issue(
                        employee_id=punch.employee_id,
                        issue_type=CheckIssueType.LATE,
                        issue_date=punch.punch_date,
                        description=f"迟到 {int(late_minutes)} 分钟，上班时间 {emp.work_start_time.strftime('%H:%M')}，实际打卡 {punch.punch_in.strftime('%H:%M')}",
                        severity="warning" if late_minutes <= 30 else "error",
                        needs_confirmation=late_minutes > 60
                    )
                    count += 1
        return count

    def check_early_leave(self) -> int:
        count = 0
        punches = self.data.get_month_punches()
        for punch in punches:
            if punch.status in [AttendanceStatus.ON_LEAVE, AttendanceStatus.BUSINESS_TRIP]:
                continue
            if punch.status == AttendanceStatus.EARLY_LEAVE:
                emp = self.data.get_employee(punch.employee_id)
                if not emp or not punch.punch_out:
                    continue

                work_end = datetime.combine(punch.punch_date, emp.work_end_time)
                early_minutes = (work_end - punch.punch_out).total_seconds() / 60

                if early_minutes > self.early_leave_tolerance_minutes:
                    self._add_issue(
                        employee_id=punch.employee_id,
                        issue_type=CheckIssueType.EARLY_LEAVE,
                        issue_date=punch.punch_date,
                        description=f"早退 {int(early_minutes)} 分钟，下班时间 {emp.work_end_time.strftime('%H:%M')}，实际打卡 {punch.punch_out.strftime('%H:%M')}",
                        severity="warning" if early_minutes <= 30 else "error",
                        needs_confirmation=early_minutes > 60
                    )
                    count += 1
        return count

    def check_missing_punch(self) -> int:
        count = 0
        punches = self.data.get_month_punches()
        for punch in punches:
            if punch.status in [AttendanceStatus.ON_LEAVE, AttendanceStatus.BUSINESS_TRIP]:
                continue

            emp = self.data.get_employee(punch.employee_id)
            if not emp:
                continue

            if self.data.is_holiday(punch.punch_date):
                if not punch.punch_in and not punch.punch_out:
                    continue

            is_non_workday = not self.data.is_workday(punch.punch_date)
            if is_non_workday and not punch.punch_in and not punch.punch_out:
                continue

            missing_in = punch.punch_in is None and self.data.is_workday(punch.punch_date)
            missing_out = punch.punch_out is None and self.data.is_workday(punch.punch_date)

            if missing_in or missing_out:
                missing_type = "上班" if missing_in else "下班"
                if missing_in and missing_out:
                    missing_type = "上下班"

                self._add_issue(
                    employee_id=punch.employee_id,
                    issue_type=CheckIssueType.MISSING_PUNCH,
                    issue_date=punch.punch_date,
                    description=f"漏打{missing_type}卡，{missing_type}无打卡记录",
                    severity="warning",
                    needs_confirmation=True
                )
                count += 1
        return count

    def _date_ranges_overlap(self, start1: date, end1: date, start2: date, end2: date) -> bool:
        return start1 <= end2 and start2 <= end1

    def check_leave_conflicts(self) -> int:
        count = 0
        employee_leaves: Dict[str, List[LeaveRecord]] = defaultdict(list)

        leaves = self.data.get_month_leaves()
        for leave in leaves:
            if not leave.approved:
                continue
            employee_leaves[leave.employee_id].append(leave)

        for emp_id, leaves in employee_leaves.items():
            leaves_sorted = sorted(leaves, key=lambda x: x.start_date)
            for i in range(len(leaves_sorted)):
                for j in range(i + 1, len(leaves_sorted)):
                    l1, l2 = leaves_sorted[i], leaves_sorted[j]
                    if self._date_ranges_overlap(l1.start_date, l1.end_date, l2.start_date, l2.end_date):
                        overlap_start = max(l1.start_date, l2.start_date)
                        overlap_end = min(l1.end_date, l2.end_date)
                        overlap_days = (overlap_end - overlap_start).days + 1

                        if not self.data.is_in_month(overlap_start) and not self.data.is_in_month(overlap_end):
                            continue

                        self._add_issue(
                            employee_id=emp_id,
                            issue_type=CheckIssueType.LEAVE_CONFLICT,
                            issue_date=overlap_start,
                            description=f"假期冲突：{l1.leave_type.value}({l1.start_date}~{l1.end_date}) 与 {l2.leave_type.value}({l2.start_date}~{l2.end_date}) 重叠 {overlap_days} 天",
                            severity="error",
                            needs_confirmation=True
                        )
                        count += 1

        for leave in leaves:
            if not leave.approved:
                continue
            emp_id = leave.employee_id
            balances = self.data.get_employee_leave_balance(emp_id)
            balance = balances.get(leave.leave_type)

            if balance and balance.remaining_days < leave.days:
                if not self.data.is_in_month(leave.start_date):
                    continue

                self._add_issue(
                    employee_id=emp_id,
                    issue_type=CheckIssueType.LEAVE_BALANCE_INSUFFICIENT,
                    issue_date=leave.start_date,
                    description=f"{leave.leave_type.value}余额不足：剩余 {balance.remaining_days} 天，申请 {leave.days} 天",
                    severity="warning",
                    needs_confirmation=True
                )
                count += 1

            trips = self.data.get_employee_business_trips(emp_id)
            for trip in trips:
                if self._date_ranges_overlap(leave.start_date, leave.end_date, trip.start_date, trip.end_date):
                    overlap_start = max(leave.start_date, trip.start_date)
                    if not self.data.is_in_month(overlap_start):
                        continue

                    self._add_issue(
                        employee_id=emp_id,
                        issue_type=CheckIssueType.LEAVE_CONFLICT,
                        issue_date=overlap_start,
                        description=f"假期与出差冲突：{leave.leave_type.value}({leave.start_date}~{leave.end_date}) 与出差({trip.start_date}~{trip.end_date}) 重叠",
                        severity="error",
                        needs_confirmation=True
                    )
                    count += 1

        return count

    def check_cross_month_shifts(self) -> int:
        count = 0
        target_year = self.data.year
        target_month = self.data.month

        if target_year == 0 or target_month == 0:
            return count

        leaves = self.data.get_month_leaves()
        for leave in leaves:
            if not leave.approved:
                continue

            leave_starts_this_month = self.data.is_in_month(leave.start_date)
            leave_ends_this_month = self.data.is_in_month(leave.end_date)

            if leave_starts_this_month and not leave_ends_this_month:
                self._add_issue(
                    employee_id=leave.employee_id,
                    issue_type=CheckIssueType.CROSS_MONTH_SHIFT,
                    issue_date=leave.start_date,
                    description=f"跨月{leave.leave_type.value}：开始于本月 {leave.start_date}，结束于 {leave.end_date}",
                    severity="info",
                    needs_confirmation=False
                )
                count += 1
            elif not leave_starts_this_month and leave_ends_this_month:
                self._add_issue(
                    employee_id=leave.employee_id,
                    issue_type=CheckIssueType.CROSS_MONTH_SHIFT,
                    issue_date=date(target_year, target_month, 1),
                    description=f"跨月{leave.leave_type.value}：开始于 {leave.start_date}，结束于本月 {leave.end_date}",
                    severity="info",
                    needs_confirmation=False
                )
                count += 1

        trips = self.data.get_month_business_trips()
        for trip in trips:
            trip_starts_this_month = self.data.is_in_month(trip.start_date)
            trip_ends_this_month = self.data.is_in_month(trip.end_date)

            if trip_starts_this_month and not trip_ends_this_month:
                self._add_issue(
                    employee_id=trip.employee_id,
                    issue_type=CheckIssueType.CROSS_MONTH_SHIFT,
                    issue_date=trip.start_date,
                    description=f"跨月出差：开始于本月 {trip.start_date}，结束于 {trip.end_date}",
                    severity="info",
                    needs_confirmation=False
                )
                count += 1
            elif not trip_starts_this_month and trip_ends_this_month:
                self._add_issue(
                    employee_id=trip.employee_id,
                    issue_type=CheckIssueType.CROSS_MONTH_SHIFT,
                    issue_date=date(target_year, target_month, 1),
                    description=f"跨月出差：开始于 {trip.start_date}，结束于本月 {trip.end_date}",
                    severity="info",
                    needs_confirmation=False
                )
                count += 1

        punches = self.data.get_month_punches()
        for punch in punches:
            if punch.punch_in and punch.punch_out:
                if punch.punch_in.date() != punch.punch_out.date():
                    self._add_issue(
                        employee_id=punch.employee_id,
                        issue_type=CheckIssueType.CROSS_MONTH_SHIFT,
                        issue_date=punch.punch_date,
                        description=f"跨天班次：上班打卡 {punch.punch_in}，下班打卡 {punch.punch_out}",
                        severity="info",
                        needs_confirmation=False
                    )
                    count += 1

        return count

    def check_abnormal_overtime(self) -> int:
        count = 0
        employee_daily_overtime: Dict[Tuple[str, date], float] = defaultdict(float)

        overtimes = self.data.get_month_overtimes()
        for ot in overtimes:
            if not ot.approved:
                continue

            key = (ot.employee_id, ot.overtime_date)
            employee_daily_overtime[key] += ot.hours

        for (emp_id, ot_date), total_hours in employee_daily_overtime.items():
            if total_hours > self.max_daily_overtime_hours:
                self._add_issue(
                    employee_id=emp_id,
                    issue_type=CheckIssueType.ABNORMAL_OVERTIME,
                    issue_date=ot_date,
                    description=f"单日加班时长异常：{total_hours:.1f} 小时，超过每日上限 {self.max_daily_overtime_hours} 小时",
                    severity="warning",
                    needs_confirmation=True
                )
                count += 1

        employee_monthly_overtime: Dict[str, float] = defaultdict(float)
        for ot in overtimes:
            if not ot.approved:
                continue
            employee_monthly_overtime[ot.employee_id] += ot.hours

        for emp_id, total_hours in employee_monthly_overtime.items():
            monthly_max = self.max_overtime_hours * self.data.get_standard_workdays()
            if total_hours > monthly_max:
                self._add_issue(
                    employee_id=emp_id,
                    issue_type=CheckIssueType.ABNORMAL_OVERTIME,
                    issue_date=date(self.data.year, self.data.month, 1),
                    description=f"月度加班时长异常：{total_hours:.1f} 小时，超过月度上限 {monthly_max:.0f} 小时",
                    severity="error",
                    needs_confirmation=True
                )
                count += 1

        for ot in overtimes:
            if not ot.approved:
                continue

            punches = self.data.get_employee_punches(ot.employee_id)
            same_day_punch = next((p for p in punches if p.punch_date == ot.overtime_date), None)

            if same_day_punch and same_day_punch.punch_out:
                ot_start = datetime.combine(ot.overtime_date, ot.start_time)
                if ot_start < same_day_punch.punch_out:
                    self._add_issue(
                        employee_id=ot.employee_id,
                        issue_type=CheckIssueType.ABNORMAL_OVERTIME,
                        issue_date=ot.overtime_date,
                        description=f"加班时间与下班时间冲突：下班打卡 {same_day_punch.punch_out.strftime('%H:%M')}，加班开始 {ot.start_time.strftime('%H:%M')}",
                        severity="warning",
                        needs_confirmation=True
                    )
                    count += 1

            if ot.hours > self.max_daily_overtime_hours:
                self._add_issue(
                    employee_id=ot.employee_id,
                    issue_type=CheckIssueType.ABNORMAL_OVERTIME,
                    issue_date=ot.overtime_date,
                    description=f"单次加班时长异常：{ot.hours:.1f} 小时，超过单次上限 {self.max_daily_overtime_hours} 小时",
                    severity="warning",
                    needs_confirmation=True
                )
                count += 1

        return count

    def check_absent_on_special_workdays(self) -> int:
        count = 0
        if self.data.year == 0 or self.data.month == 0:
            return count

        month_workdays = self.data.get_month_workdays()
        special_workdays = [d for d in month_workdays if self.data.is_special_workday(d)]

        if not special_workdays:
            return count

        for emp_id in self.data.employees:
            punches = self.data.get_employee_punches(emp_id, month_only=True)
            leaves = self.data.get_employee_leaves(emp_id, month_only=True)
            trips = self.data.get_employee_business_trips(emp_id, month_only=True)

            punch_dates = {p.punch_date for p in punches}
            leave_dates = set()
            for leave in leaves:
                days_in_month = self.data.get_days_in_month(leave.start_date, leave.end_date)
                if days_in_month > 0:
                    from datetime import timedelta
                    current = max(leave.start_date, date(self.data.year, self.data.month, 1))
                    end = min(leave.end_date, date(self.data.year, self.data.month + 1, 1) - timedelta(days=1)) if self.data.month < 12 else min(leave.end_date, date(self.data.year + 1, 1, 1) - timedelta(days=1))
                    while current <= end:
                        leave_dates.add(current)
                        current += timedelta(days=1)

            trip_dates = set()
            for trip in trips:
                days_in_month = self.data.get_days_in_month(trip.start_date, trip.end_date)
                if days_in_month > 0:
                    from datetime import timedelta
                    current = max(trip.start_date, date(self.data.year, self.data.month, 1))
                    end = min(trip.end_date, date(self.data.year, self.data.month + 1, 1) - timedelta(days=1)) if self.data.month < 12 else min(trip.end_date, date(self.data.year + 1, 1, 1) - timedelta(days=1))
                    while current <= end:
                        trip_dates.add(current)
                        current += timedelta(days=1)

            for d in special_workdays:
                if d not in punch_dates and d not in leave_dates and d not in trip_dates:
                    self._add_issue(
                        employee_id=emp_id,
                        issue_type=CheckIssueType.ABSENT,
                        issue_date=d,
                        description=f"特殊工作日缺勤：{d.strftime('%Y-%m-%d')} 为调休工作日，无打卡、请假或出差记录",
                        severity="error",
                        needs_confirmation=True
                    )
                    count += 1

        return count

    def run_all_checks(self) -> Dict[str, int]:
        self.data.check_issues.clear()

        results = {
            "late_arrival": self.check_late_arrival(),
            "early_leave": self.check_early_leave(),
            "missing_punch": self.check_missing_punch(),
            "absent": self.check_absent_on_special_workdays(),
            "leave_conflicts": self.check_leave_conflicts(),
            "cross_month_shifts": self.check_cross_month_shifts(),
            "abnormal_overtime": self.check_abnormal_overtime(),
        }
        results["total"] = sum(results.values())

        self.data.mark_check_done()

        return results

    def get_issues_by_employee(self, employee_id: str) -> List[CheckIssue]:
        return [i for i in self.data.check_issues if i.employee_id == employee_id]

    def get_issues_by_type(self, issue_type: CheckIssueType) -> List[CheckIssue]:
        return [i for i in self.data.check_issues if i.issue_type == issue_type]

    def get_issues_by_severity(self, severity: str) -> List[CheckIssue]:
        return [i for i in self.data.check_issues if i.severity == severity]

    def get_issues_needing_confirmation(self) -> List[CheckIssue]:
        return [i for i in self.data.check_issues if i.needs_confirmation]
