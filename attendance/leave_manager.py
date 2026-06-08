from typing import List, Dict, Optional
from collections import defaultdict

from .models import AttendanceData, LeaveBalance, LeaveType, LeaveRecord


class LeaveManager:
    def __init__(self, attendance_data: AttendanceData):
        self.data = attendance_data

    def _get_employee_name(self, employee_id: str) -> str:
        emp = self.data.get_employee(employee_id)
        return emp.name if emp else employee_id

    def _get_employee_department(self, employee_id: str) -> str:
        emp = self.data.get_employee(employee_id)
        return emp.department if emp else ""

    def get_leave_balance(self, employee_id: str, leave_type: Optional[LeaveType] = None) -> List[LeaveBalance]:
        balances = self.data.get_employee_leave_balance(employee_id)

        if leave_type:
            if leave_type in balances:
                return [balances[leave_type]]
            return []

        result = []
        for lt in LeaveType:
            if lt in balances:
                result.append(balances[lt])
            else:
                result.append(LeaveBalance(
                    employee_id=employee_id,
                    leave_type=lt,
                    total_days=0.0,
                    used_days=0.0,
                    remaining_days=0.0
                ))
        return result

    def get_all_leave_balances(self) -> Dict[str, List[LeaveBalance]]:
        result = {}
        for emp_id in self.data.employees:
            result[emp_id] = self.get_leave_balance(emp_id)
        return result

    def calculate_used_days(self, employee_id: str, leave_type: LeaveType) -> float:
        leaves = self.data.get_employee_leaves(employee_id)
        total = 0.0
        for leave in leaves:
            if leave.leave_type == leave_type and leave.approved:
                if (self.data.year == 0 or self.data.month == 0 or
                    (leave.start_date.year == self.data.year and
                     leave.start_date.month == self.data.month)):
                    total += leave.days
        return total

    def update_balance_from_records(self, employee_id: str, leave_type: LeaveType) -> Optional[LeaveBalance]:
        balances = self.data.get_employee_leave_balance(employee_id)
        balance = balances.get(leave_type)

        if not balance:
            return None

        used_days = self.calculate_used_days(employee_id, leave_type)
        balance.used_days = used_days
        balance.remaining_days = max(0.0, balance.total_days - used_days)

        return balance

    def update_all_balances(self) -> int:
        count = 0
        for emp_id in self.data.employees:
            for lt in LeaveType:
                if self.update_balance_from_records(emp_id, lt):
                    count += 1
        return count

    def get_leave_records(self, employee_id: str, leave_type: Optional[LeaveType] = None) -> List[LeaveRecord]:
        records = self.data.get_employee_leaves(employee_id)
        if leave_type:
            records = [r for r in records if r.leave_type == leave_type]
        return sorted(records, key=lambda x: x.start_date, reverse=True)

    def get_department_leave_summary(self, department: str) -> Dict:
        emp_ids = [eid for eid, e in self.data.employees.items() if e.department == department]

        total_balance_by_type: Dict[LeaveType, Dict[str, float]] = defaultdict(
            lambda: {"total": 0.0, "used": 0.0, "remaining": 0.0}
        )

        for emp_id in emp_ids:
            balances = self.get_leave_balance(emp_id)
            for bal in balances:
                total_balance_by_type[bal.leave_type]["total"] += bal.total_days
                total_balance_by_type[bal.leave_type]["used"] += bal.used_days
                total_balance_by_type[bal.leave_type]["remaining"] += bal.remaining_days

        return {
            "department": department,
            "employee_count": len(emp_ids),
            "leave_summary": {
                lt.value: {
                    "total_days": round(data["total"], 2),
                    "used_days": round(data["used"], 2),
                    "remaining_days": round(data["remaining"], 2)
                }
                for lt, data in total_balance_by_type.items()
            }
        }

    def get_employees_with_low_balance(self, leave_type: LeaveType, threshold_days: float = 1.0) -> List[Dict]:
        result = []
        for emp_id in self.data.employees:
            balances = self.get_leave_balance(emp_id, leave_type)
            for bal in balances:
                if bal.remaining_days <= threshold_days:
                    result.append({
                        "employee_id": emp_id,
                        "name": self._get_employee_name(emp_id),
                        "department": self._get_employee_department(emp_id),
                        "leave_type": leave_type.value,
                        "remaining_days": bal.remaining_days,
                        "total_days": bal.total_days
                    })
        return sorted(result, key=lambda x: x["remaining_days"])

    def get_leave_statistics(self) -> Dict:
        total_approved_leaves = 0
        total_pending_leaves = 0
        total_leave_days = 0.0
        total_records = 0
        leave_type_count: Dict[str, int] = defaultdict(int)
        leave_type_days: Dict[str, float] = defaultdict(float)

        for leave in self.data.leave_records:
            days_in_month = self.data.get_days_in_month(leave.start_date, leave.end_date)
            if days_in_month <= 0:
                continue

            total_records += 1
            if leave.approved:
                total_approved_leaves += 1
                total_leave_days += days_in_month
                leave_type_count[leave.leave_type.value] += 1
                leave_type_days[leave.leave_type.value] += days_in_month
            else:
                total_pending_leaves += 1

        return {
            "year": self.data.year,
            "month": self.data.month,
            "total_leave_records": total_records,
            "approved_leaves": total_approved_leaves,
            "pending_leaves": total_pending_leaves,
            "total_leave_days": round(total_leave_days, 2),
            "leave_type_count": dict(leave_type_count),
            "leave_type_days": {k: round(v, 2) for k, v in leave_type_days.items()}
        }
