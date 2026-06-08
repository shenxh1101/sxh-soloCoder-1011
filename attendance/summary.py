from datetime import date
from typing import List, Dict
from collections import defaultdict

from .models import (
    AttendanceData, AttendanceStatus, DepartmentSummary,
    EmployeeSummary, LeaveType, CheckIssueType
)


class AttendanceSummary:
    def __init__(self, attendance_data: AttendanceData):
        self.data = attendance_data

    def generate_employee_summary(self, employee_id: str) -> EmployeeSummary:
        emp = self.data.get_employee(employee_id)
        if not emp:
            raise ValueError(f"员工不存在: {employee_id}")

        punches = self.data.get_employee_punches(employee_id, month_only=True)
        leaves = self.data.get_employee_leaves(employee_id, month_only=True)
        trips = self.data.get_employee_business_trips(employee_id, month_only=True)
        overtimes = self.data.get_employee_overtimes(employee_id, month_only=True)
        issues = [i for i in self.data.get_month_issues() if i.employee_id == employee_id]

        standard_workdays = self.data.get_standard_workdays()

        attendance_days = 0.0
        absence_count = 0
        overtime_hours = 0.0
        late_count = 0
        early_leave_count = 0
        missing_punch_count = 0
        leave_days: Dict[str, float] = defaultdict(float)
        business_trip_days = 0.0
        issue_summary: Dict[str, int] = defaultdict(int)

        for punch in punches:
            if punch.status == AttendanceStatus.NORMAL:
                attendance_days += 1.0
            elif punch.status == AttendanceStatus.LATE:
                attendance_days += 1.0
                late_count += 1
            elif punch.status == AttendanceStatus.EARLY_LEAVE:
                attendance_days += 1.0
                early_leave_count += 1
            elif punch.status == AttendanceStatus.MISSING_PUNCH:
                attendance_days += 0.5
                missing_punch_count += 1
            elif punch.status == AttendanceStatus.ABSENT:
                absence_count += 1
            elif punch.status == AttendanceStatus.ON_LEAVE:
                pass
            elif punch.status == AttendanceStatus.BUSINESS_TRIP:
                attendance_days += 1.0

        for leave in leaves:
            if leave.approved:
                days_in_month = self.data.get_days_in_month(leave.start_date, leave.end_date)
                if days_in_month > 0:
                    leave_days[leave.leave_type.value] += days_in_month

        for trip in trips:
            days_in_month = self.data.get_days_in_month(trip.start_date, trip.end_date)
            if days_in_month > 0:
                business_trip_days += days_in_month
                attendance_days += days_in_month

        for ot in overtimes:
            if ot.approved:
                overtime_hours += ot.hours

        for issue in issues:
            issue_summary[issue.issue_type.value] += 1
            if issue.issue_type == CheckIssueType.ABSENT:
                absence_count += 1

        needs_confirm = any(i.needs_confirmation for i in issues)

        summary = EmployeeSummary(
            employee_id=employee_id,
            name=emp.name,
            department=emp.department,
            standard_workdays=standard_workdays,
            attendance_days=round(attendance_days, 2),
            absence_count=absence_count,
            overtime_hours=round(overtime_hours, 2),
            late_count=late_count,
            early_leave_count=early_leave_count,
            missing_punch_count=missing_punch_count,
            leave_days=dict(leave_days),
            business_trip_days=round(business_trip_days, 2),
            issues=issues,
            issue_summary=dict(issue_summary),
            needs_confirmation=needs_confirm
        )

        return summary

    def generate_all_employee_summaries(self) -> List[EmployeeSummary]:
        summaries = []
        for emp_id in self.data.employees:
            summaries.append(self.generate_employee_summary(emp_id))
        return summaries

    def generate_department_summary(self, department: str) -> DepartmentSummary:
        emp_ids = [eid for eid, e in self.data.employees.items() if e.department == department]
        if not emp_ids:
            raise ValueError(f"部门不存在: {department}")

        total_attendance_days = 0.0
        total_absence_count = 0
        total_overtime_hours = 0.0
        employees_needing_confirmation = []
        standard_workdays = self.data.get_standard_workdays()

        attendance_rates = []

        for emp_id in emp_ids:
            emp_summary = self.generate_employee_summary(emp_id)
            total_attendance_days += emp_summary.attendance_days
            total_absence_count += emp_summary.absence_count
            total_overtime_hours += emp_summary.overtime_hours

            if emp_summary.needs_confirmation:
                employees_needing_confirmation.append(emp_summary.name)

            if standard_workdays > 0:
                rate = emp_summary.attendance_days / standard_workdays * 100
                attendance_rates.append(min(rate, 100))

        avg_attendance_rate = sum(attendance_rates) / len(attendance_rates) if attendance_rates else 0.0

        return DepartmentSummary(
            department=department,
            employee_count=len(emp_ids),
            total_attendance_days=round(total_attendance_days, 2),
            total_absence_count=total_absence_count,
            total_overtime_hours=round(total_overtime_hours, 2),
            average_attendance_rate=round(avg_attendance_rate, 2),
            standard_workdays=standard_workdays,
            employees_needing_confirmation=employees_needing_confirmation
        )

    def generate_all_department_summaries(self) -> List[DepartmentSummary]:
        departments = set(e.department for e in self.data.employees.values() if e.department)
        summaries = []
        for dept in sorted(departments):
            summaries.append(self.generate_department_summary(dept))
        return summaries

    def get_summary_stats(self) -> Dict:
        dept_summaries = self.generate_all_department_summaries()
        emp_summaries = self.generate_all_employee_summaries()

        total_employees = len(self.data.employees)
        total_departments = len(dept_summaries)
        total_attendance = sum(s.total_attendance_days for s in dept_summaries)
        total_absences = sum(s.total_absence_count for s in dept_summaries)
        total_overtime = sum(s.total_overtime_hours for s in dept_summaries)

        avg_attendance_rate = (
            sum(s.average_attendance_rate for s in dept_summaries) / total_departments
            if total_departments > 0 else 0.0
        )

        employees_with_issues = sum(
            1 for s in emp_summaries if s.late_count > 0 or s.early_leave_count > 0
            or s.missing_punch_count > 0 or s.absence_count > 0
        )

        employees_needing_confirm = sum(
            1 for s in emp_summaries if s.needs_confirmation
        )

        standard_workdays = self.data.get_standard_workdays()

        return {
            "year": self.data.year,
            "month": self.data.month,
            "month_str": self.data.month_str,
            "standard_workdays": standard_workdays,
            "total_employees": total_employees,
            "total_departments": total_departments,
            "total_attendance_days": round(total_attendance, 2),
            "total_absence_count": total_absences,
            "total_overtime_hours": round(total_overtime, 2),
            "average_attendance_rate": round(avg_attendance_rate, 2),
            "employees_with_issues": employees_with_issues,
            "employees_needing_confirmation": employees_needing_confirm,
            "total_check_issues": len(self.data.get_month_issues()),
            "check_dirty": self.data.check_dirty,
            "data_dirty": self.data.data_dirty,
        }
