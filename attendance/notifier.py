from typing import List, Dict, Optional
from collections import defaultdict

from .models import AttendanceData, CheckIssue, CheckIssueType


class Notifier:
    def __init__(self, attendance_data: AttendanceData):
        self.data = attendance_data

    def get_notification_records(self, only_needs_confirmation: bool = True) -> List[CheckIssue]:
        issues = self.data.get_month_issues()
        if only_needs_confirmation:
            return [i for i in issues if i.needs_confirmation]
        return list(issues)

    def get_notifications_by_employee(self, employee_id: Optional[str] = None) -> Dict[str, List[CheckIssue]]:
        result: Dict[str, List[CheckIssue]] = defaultdict(list)

        issues = self.get_notification_records()
        for issue in issues:
            if employee_id and issue.employee_id != employee_id:
                continue
            result[issue.employee_id].append(issue)

        return dict(result)

    def get_notifications_by_department(self, department: Optional[str] = None) -> Dict[str, List[CheckIssue]]:
        result: Dict[str, List[CheckIssue]] = defaultdict(list)

        issues = self.get_notification_records()
        for issue in issues:
            if department and issue.department != department:
                continue
            result[issue.department].append(issue)

        return dict(result)

    def get_notifications_by_type(self, issue_type: Optional[CheckIssueType] = None) -> Dict[str, List[CheckIssue]]:
        result: Dict[str, List[CheckIssue]] = defaultdict(list)

        issues = self.get_notification_records()
        for issue in issues:
            if issue_type and issue.issue_type != issue_type:
                continue
            result[issue.issue_type.value].append(issue)

        return dict(result)

    def get_employee_notification_summary(self, employee_id: str) -> Dict:
        issues = [i for i in self.data.get_month_issues()
                  if i.employee_id == employee_id and i.needs_confirmation]

        issue_count_by_type: Dict[str, int] = defaultdict(int)
        for issue in issues:
            issue_count_by_type[issue.issue_type.value] += 1

        emp = self.data.get_employee(employee_id)
        return {
            "employee_id": employee_id,
            "name": emp.name if emp else employee_id,
            "department": emp.department if emp else "",
            "total_notifications": len(issues),
            "notifications_by_type": dict(issue_count_by_type),
            "issues": issues
        }

    def get_department_notification_summary(self, department: str) -> Dict:
        issues = [i for i in self.data.get_month_issues()
                  if i.department == department and i.needs_confirmation]

        employees = set(i.employee_id for i in issues)
        issue_count_by_type: Dict[str, int] = defaultdict(int)
        issue_count_by_employee: Dict[str, int] = defaultdict(int)

        for issue in issues:
            issue_count_by_type[issue.issue_type.value] += 1
            issue_count_by_employee[issue.employee_name] += 1

        return {
            "department": department,
            "affected_employees": len(employees),
            "total_notifications": len(issues),
            "notifications_by_type": dict(issue_count_by_type),
            "notifications_by_employee": dict(issue_count_by_employee),
            "issues": issues
        }

    def get_overall_notification_summary(self) -> Dict:
        issues = self.get_notification_records()

        departments = set(i.department for i in issues if i.department)
        employees = set(i.employee_id for i in issues)
        issue_count_by_type: Dict[str, int] = defaultdict(int)
        issue_count_by_department: Dict[str, int] = defaultdict(int)
        issue_count_by_severity: Dict[str, int] = defaultdict(int)

        for issue in issues:
            issue_count_by_type[issue.issue_type.value] += 1
            if issue.department:
                issue_count_by_department[issue.department] += 1
            issue_count_by_severity[issue.severity] += 1

        return {
            "year": self.data.year,
            "month": self.data.month,
            "month_str": self.data.month_str,
            "affected_departments": len(departments),
            "affected_employees": len(employees),
            "total_notifications": len(issues),
            "notifications_by_type": dict(issue_count_by_type),
            "notifications_by_department": dict(issue_count_by_department),
            "notifications_by_severity": {
                "错误": issue_count_by_severity.get("error", 0),
                "警告": issue_count_by_severity.get("warning", 0),
                "提示": issue_count_by_severity.get("info", 0)
            }
        }

    def generate_notification_messages(self) -> List[Dict]:
        notifications_by_emp = self.get_notifications_by_employee()
        messages = []

        for emp_id, issues in notifications_by_emp.items():
            emp = self.data.get_employee(emp_id)
            if not emp:
                continue

            issue_descriptions = []
            for issue in issues:
                issue_descriptions.append(
                    f"[{issue.issue_type.value}] {issue.issue_date.strftime('%Y-%m-%d')}: {issue.description}"
                )

            earliest_deadline = None
            for issue in issues:
                if issue.deadline:
                    if earliest_deadline is None or issue.deadline < earliest_deadline:
                        earliest_deadline = issue.deadline

            message = {
                "employee_id": emp_id,
                "name": emp.name,
                "department": emp.department,
                "notification_count": len(issues),
                "issue_types": list(set(i.issue_type.value for i in issues)),
                "earliest_deadline": earliest_deadline,
                "message": self._format_message(emp.name, issues, earliest_deadline),
                "details": issue_descriptions,
                "issues": issues
            }
            messages.append(message)

        return sorted(messages, key=lambda x: (-x["notification_count"], x["department"], x["name"]))

    def _format_message(self, name: str, issues: List[CheckIssue], deadline) -> str:
        type_counts: Dict[str, int] = defaultdict(int)
        for issue in issues:
            type_counts[issue.issue_type.value] += 1

        type_str = "、".join([f"{k}×{v}" for k, v in type_counts.items()])
        deadline_str = f"处理截止日期为 {deadline.strftime('%Y-%m-%d')}" if deadline else "请尽快处理"

        return (
            f"{name}您好，您本月有 {len(issues)} 条考勤记录需要确认："
            f"{type_str}。{deadline_str}，请尽快登录系统补充说明或提交相关证明材料。"
        )

    def export_notification_list(self, output_path: Optional[str] = None) -> List[Dict]:
        messages = self.generate_notification_messages()
        rows = []

        for msg in messages:
            for issue in msg["issues"]:
                rows.append({
                    "部门": msg["department"],
                    "工号": msg["employee_id"],
                    "姓名": msg["name"],
                    "异常日期": issue.issue_date.strftime("%Y-%m-%d"),
                    "异常类型": issue.issue_type.value,
                    "异常原因": issue.description,
                    "严重程度": {"error": "错误", "warning": "警告", "info": "提示"}.get(issue.severity, issue.severity),
                    "处理截止日期": issue.deadline.strftime("%Y-%m-%d") if issue.deadline else "",
                    "是否需确认": "是" if issue.needs_confirmation else "否",
                })

        if output_path:
            import pandas as pd
            from pathlib import Path
            Path(output_path).parent.mkdir(parents=True, exist_ok=True)

            df = pd.DataFrame(rows)
            if not df.empty:
                df = df.sort_values(["部门", "工号", "异常日期"])

            if output_path.endswith(".csv"):
                df.to_csv(output_path, index=False, encoding="utf-8-sig")
            else:
                df.to_excel(output_path, index=False, sheet_name="待确认清单")

            return output_path

        return rows

    def get_reminder_list(self, days_until_deadline: int = 3) -> List[Dict]:
        issues = self.get_notification_records()
        from datetime import datetime, timedelta

        today = datetime.now().date()
        deadline = today + timedelta(days=days_until_deadline)

        reminder_data: Dict[str, Dict] = defaultdict(lambda: {
            "issues": [],
            "oldest_issue_date": None,
            "earliest_deadline": None
        })

        for issue in issues:
            emp_id = issue.employee_id
            reminder_data[emp_id]["issues"].append(issue)
            if (reminder_data[emp_id]["oldest_issue_date"] is None or
                    issue.issue_date < reminder_data[emp_id]["oldest_issue_date"]):
                reminder_data[emp_id]["oldest_issue_date"] = issue.issue_date
            if issue.deadline:
                if (reminder_data[emp_id]["earliest_deadline"] is None or
                        issue.deadline < reminder_data[emp_id]["earliest_deadline"]):
                    reminder_data[emp_id]["earliest_deadline"] = issue.deadline

        urgent_reminders = []
        for emp_id, data in reminder_data.items():
            oldest_date = data["oldest_issue_date"]
            earliest_deadline = data["earliest_deadline"]
            if oldest_date:
                days_pending = (today - oldest_date).days
                is_urgent = days_pending >= 7
                is_overdue = earliest_deadline and earliest_deadline < today

                emp = self.data.get_employee(emp_id)
                urgent_reminders.append({
                    "employee_id": emp_id,
                    "name": emp.name if emp else emp_id,
                    "department": emp.department if emp else "",
                    "pending_count": len(data["issues"]),
                    "oldest_issue_date": oldest_date.strftime("%Y-%m-%d"),
                    "earliest_deadline": earliest_deadline.strftime("%Y-%m-%d") if earliest_deadline else "",
                    "days_pending": days_pending,
                    "is_urgent": is_urgent,
                    "is_overdue": is_overdue,
                    "deadline": deadline.strftime("%Y-%m-%d")
                })

        return sorted(urgent_reminders, key=lambda x: (-x["days_pending"], x["department"]))
