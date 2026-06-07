import pandas as pd
from pathlib import Path
from datetime import datetime
from typing import List, Dict

from .models import AttendanceData, LeaveType, CheckIssueType
from .summary import AttendanceSummary
from .leave_manager import LeaveManager


class DataExporter:
    def __init__(self, attendance_data: AttendanceData):
        self.data = attendance_data
        self.summary = AttendanceSummary(attendance_data)
        self.leave_manager = LeaveManager(attendance_data)

    def _ensure_dir(self, file_path: str):
        Path(file_path).parent.mkdir(parents=True, exist_ok=True)

    def export_payroll_data(self, output_path: str) -> str:
        self._ensure_dir(output_path)

        emp_summaries = self.summary.generate_all_employee_summaries()
        rows = []

        standard_workdays = self.data.get_standard_workdays()

        for emp_summary in emp_summaries:
            emp = self.data.get_employee(emp_summary.employee_id)
            if not emp:
                continue

            total_leave_days = sum(emp_summary.leave_days.values())
            balances = self.leave_manager.get_leave_balance(emp_summary.employee_id)
            annual_balance = next(
                (b for b in balances if b.leave_type == LeaveType.ANNUAL), None
            )

            issue_summary_parts = []
            for issue_type, count in emp_summary.issue_summary.items():
                issue_summary_parts.append(f"{issue_type}×{count}")
            issue_summary_str = "；".join(issue_summary_parts) if issue_summary_parts else ""

            leave_usage_parts = []
            for leave_type in LeaveType:
                days = emp_summary.leave_days.get(leave_type.value, 0)
                if days > 0:
                    leave_usage_parts.append(f"{leave_type.value}×{days}")
            leave_usage_str = "；".join(leave_usage_parts) if leave_usage_parts else ""

            row = {
                "工号": emp_summary.employee_id,
                "姓名": emp_summary.name,
                "部门": emp_summary.department,
                "职位": emp.position,
                "考勤月份": self.data.month_str or f"{self.data.year}年{self.data.month}月",
                "应出勤天数": standard_workdays,
                "实际出勤天数": emp_summary.attendance_days,
                "出勤天数": emp_summary.attendance_days,
                "缺勤天数": emp_summary.absence_count,
                "请假天数": round(total_leave_days, 2),
                "年假(天)": emp_summary.leave_days.get("年假", 0),
                "病假(天)": emp_summary.leave_days.get("病假", 0),
                "事假(天)": emp_summary.leave_days.get("事假", 0),
                "其他假期(天)": round(
                    total_leave_days -
                    emp_summary.leave_days.get("年假", 0) -
                    emp_summary.leave_days.get("病假", 0) -
                    emp_summary.leave_days.get("事假", 0), 2
                ),
                "各类假期用量": leave_usage_str,
                "出差天数": emp_summary.business_trip_days,
                "加班时长(小时)": emp_summary.overtime_hours,
                "迟到次数": emp_summary.late_count,
                "早退次数": emp_summary.early_leave_count,
                "漏打卡次数": emp_summary.missing_punch_count,
                "异常明细汇总": issue_summary_str,
                "异常总数": len(emp_summary.issues),
                "需确认异常数": len([i for i in emp_summary.issues if i.needs_confirmation]),
                "需确认标记": "是" if emp_summary.needs_confirmation else "否",
                "年假余额": annual_balance.remaining_days if annual_balance else 0,
                "备注": "; ".join([i.description for i in emp_summary.issues[:3]]) if emp_summary.issues else ""
            }
            rows.append(row)

        df = pd.DataFrame(rows)
        df = df.sort_values(["部门", "工号"])

        if output_path.endswith(".csv"):
            df.to_csv(output_path, index=False, encoding="utf-8-sig")
        else:
            df.to_excel(output_path, index=False, sheet_name="工资核算清单")

        return output_path

    def export_department_summary(self, output_path: str) -> str:
        self._ensure_dir(output_path)

        dept_summaries = self.summary.generate_all_department_summaries()
        rows = []

        standard_workdays = self.data.get_standard_workdays()

        for dept_summary in dept_summaries:
            row = {
                "部门": dept_summary.department,
                "员工人数": dept_summary.employee_count,
                "标准工作日": standard_workdays,
                "总出勤天数": dept_summary.total_attendance_days,
                "人均出勤天数": round(dept_summary.total_attendance_days / dept_summary.employee_count, 2) if dept_summary.employee_count > 0 else 0,
                "总缺勤次数": dept_summary.total_absence_count,
                "总加班时长(小时)": dept_summary.total_overtime_hours,
                "人均加班时长(小时)": round(dept_summary.total_overtime_hours / dept_summary.employee_count, 2) if dept_summary.employee_count > 0 else 0,
                "平均出勤率(%)": dept_summary.average_attendance_rate,
                "需确认人数": len(dept_summary.employees_needing_confirmation),
                "需确认人员": ", ".join(dept_summary.employees_needing_confirmation) if dept_summary.employees_needing_confirmation else ""
            }
            rows.append(row)

        stats = self.summary.get_summary_stats()
        rows.append({
            "部门": "合计",
            "员工人数": stats["total_employees"],
            "标准工作日": standard_workdays,
            "总出勤天数": stats["total_attendance_days"],
            "人均出勤天数": round(stats["total_attendance_days"] / stats["total_employees"], 2) if stats["total_employees"] > 0 else 0,
            "总缺勤次数": stats["total_absence_count"],
            "总加班时长(小时)": stats["total_overtime_hours"],
            "人均加班时长(小时)": round(stats["total_overtime_hours"] / stats["total_employees"], 2) if stats["total_employees"] > 0 else 0,
            "平均出勤率(%)": stats["average_attendance_rate"],
            "需确认人数": stats["employees_needing_confirmation"],
            "需确认人员": ""
        })

        df = pd.DataFrame(rows)

        if output_path.endswith(".csv"):
            df.to_csv(output_path, index=False, encoding="utf-8-sig")
        else:
            df.to_excel(output_path, index=False, sheet_name="部门汇总")

        return output_path

    def export_check_issues(self, output_path: str) -> str:
        self._ensure_dir(output_path)

        rows = []
        for issue in self.data.get_month_issues():
            row = {
                "工号": issue.employee_id,
                "姓名": issue.employee_name,
                "部门": issue.department,
                "问题类型": issue.issue_type.value,
                "问题日期": issue.issue_date.strftime("%Y-%m-%d"),
                "严重程度": issue.severity,
                "是否需确认": "是" if issue.needs_confirmation else "否",
                "处理截止日期": issue.deadline.strftime("%Y-%m-%d") if issue.deadline else "",
                "问题描述": issue.description
            }
            rows.append(row)

        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values(["部门", "工号", "问题日期"])

        if output_path.endswith(".csv"):
            df.to_csv(output_path, index=False, encoding="utf-8-sig")
        else:
            with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
                df.to_excel(writer, index=False, sheet_name="全部问题")

                for severity in ["error", "warning", "info"]:
                    sev_df = df[df["严重程度"] == severity] if not df.empty else df
                    sev_df.to_excel(writer, index=False, sheet_name=f"{'错误' if severity == 'error' else '警告' if severity == 'warning' else '提示'}")

        return output_path

    def export_leave_balances(self, output_path: str) -> str:
        self._ensure_dir(output_path)

        all_balances = self.leave_manager.get_all_leave_balances()
        rows = []

        for emp_id, balances in all_balances.items():
            emp = self.data.get_employee(emp_id)
            if not emp:
                continue

            row = {
                "工号": emp_id,
                "姓名": emp.name,
                "部门": emp.department,
            }

            for balance in balances:
                row[f"{balance.leave_type.value}-总额"] = balance.total_days
                row[f"{balance.leave_type.value}-已用"] = balance.used_days
                row[f"{balance.leave_type.value}-剩余"] = balance.remaining_days

            rows.append(row)

        df = pd.DataFrame(rows)
        df = df.sort_values(["部门", "工号"])

        if output_path.endswith(".csv"):
            df.to_csv(output_path, index=False, encoding="utf-8-sig")
        else:
            df.to_excel(output_path, index=False, sheet_name="假期余额")

        return output_path

    def export_full_report(self, output_path: str) -> str:
        self._ensure_dir(output_path)

        if output_path.endswith(".csv"):
            output_path = output_path.replace(".csv", ".xlsx")

        standard_workdays = self.data.get_standard_workdays()

        with pd.ExcelWriter(output_path, engine="openpyxl") as writer:
            payroll_rows = []
            for emp_summary in self.summary.generate_all_employee_summaries():
                emp = self.data.get_employee(emp_summary.employee_id)
                if not emp:
                    continue
                total_leave_days = sum(emp_summary.leave_days.values())
                issue_summary_parts = []
                for issue_type, count in emp_summary.issue_summary.items():
                    issue_summary_parts.append(f"{issue_type}×{count}")
                issue_summary_str = "；".join(issue_summary_parts) if issue_summary_parts else ""
                payroll_rows.append({
                    "工号": emp_summary.employee_id,
                    "姓名": emp_summary.name,
                    "部门": emp_summary.department,
                    "应出勤天数": standard_workdays,
                    "实际出勤天数": emp_summary.attendance_days,
                    "出勤天数": emp_summary.attendance_days,
                    "缺勤次数": emp_summary.absence_count,
                    "请假天数": round(total_leave_days, 2),
                    "出差天数": emp_summary.business_trip_days,
                    "加班时长(小时)": emp_summary.overtime_hours,
                    "迟到": emp_summary.late_count,
                    "早退": emp_summary.early_leave_count,
                    "漏打卡": emp_summary.missing_punch_count,
                    "异常明细": issue_summary_str,
                    "需确认": "是" if emp_summary.needs_confirmation else "否",
                })
            pd.DataFrame(payroll_rows).to_excel(writer, index=False, sheet_name="工资核算")

            dept_rows = []
            for dept_summary in self.summary.generate_all_department_summaries():
                dept_rows.append({
                    "部门": dept_summary.department,
                    "员工数": dept_summary.employee_count,
                    "标准工作日": standard_workdays,
                    "总出勤天数": dept_summary.total_attendance_days,
                    "总缺勤": dept_summary.total_absence_count,
                    "总加班(小时)": dept_summary.total_overtime_hours,
                    "平均出勤率(%)": dept_summary.average_attendance_rate,
                    "需确认人数": len(dept_summary.employees_needing_confirmation),
                })
            pd.DataFrame(dept_rows).to_excel(writer, index=False, sheet_name="部门汇总")

            issue_rows = []
            for issue in self.data.get_month_issues():
                issue_rows.append({
                    "工号": issue.employee_id,
                    "姓名": issue.employee_name,
                    "部门": issue.department,
                    "问题类型": issue.issue_type.value,
                    "日期": issue.issue_date.strftime("%Y-%m-%d"),
                    "严重程度": issue.severity,
                    "需确认": "是" if issue.needs_confirmation else "否",
                    "截止日期": issue.deadline.strftime("%Y-%m-%d") if issue.deadline else "",
                    "描述": issue.description
                })
            pd.DataFrame(issue_rows).to_excel(writer, index=False, sheet_name="异常记录")

            leave_rows = []
            for leave in self.data.get_month_leaves():
                emp = self.data.get_employee(leave.employee_id)
                leave_rows.append({
                    "工号": leave.employee_id,
                    "姓名": emp.name if emp else "",
                    "部门": emp.department if emp else "",
                    "假别": leave.leave_type.value,
                    "开始日期": leave.start_date.strftime("%Y-%m-%d"),
                    "结束日期": leave.end_date.strftime("%Y-%m-%d"),
                    "天数": leave.days,
                    "原因": leave.reason,
                    "状态": "已批准" if leave.approved else "待审批"
                })
            pd.DataFrame(leave_rows).to_excel(writer, index=False, sheet_name="请假记录")

        return output_path
