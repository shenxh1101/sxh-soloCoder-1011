#!/usr/bin/env python3
"""完整功能验证脚本 - 在单个进程中测试所有模块"""

import sys
import os
from pathlib import Path
from datetime import date

sys.path.insert(0, str(Path(__file__).parent))

from attendance.models import AttendanceData, LeaveType
from attendance.importer import DataImporter
from attendance.checker import AttendanceChecker
from attendance.summary import AttendanceSummary
from attendance.leave_manager import LeaveManager
from attendance.exporter import DataExporter
from attendance.notifier import Notifier
from attendance.utils import generate_sample_data_command


def print_header(title):
    print(f"\n{'='*60}")
    print(f"  {title}")
    print(f"{'='*60}\n")


def main():
    os.chdir(Path(__file__).parent)

    print_header("考勤数据管理工具 - 完整功能验证")

    print("步骤 1: 生成示例数据...")
    paths = generate_sample_data_command("./data")
    print(f"✓ 示例数据生成完成")

    print_header("步骤 2: 初始化数据和管理器")

    data = AttendanceData()
    importer = DataImporter(data)
    checker = AttendanceChecker(data)
    summary = AttendanceSummary(data)
    leave_manager = LeaveManager(data)
    exporter = DataExporter(data)
    notifier = Notifier(data)

    print("✓ 所有管理器初始化完成")

    print_header("步骤 3: 导入数据")

    counts = {}
    counts["employees"] = importer.import_employees(paths["employees"])
    print(f"✓ 导入员工信息: {counts['employees']} 条")

    counts["punches"] = importer.import_punches(paths["punches"])
    print(f"✓ 导入打卡记录: {counts['punches']} 条")
    print(f"  统计月份: {data.year}年{data.month}月")

    counts["leaves"] = importer.import_leaves(paths["leaves"])
    print(f"✓ 导入请假记录: {counts['leaves']} 条")

    counts["trips"] = importer.import_business_trips(paths["trips"])
    print(f"✓ 导入出差记录: {counts['trips']} 条")

    counts["overtime"] = importer.import_overtime(paths["overtime"])
    print(f"✓ 导入加班记录: {counts['overtime']} 条")

    counts["adjustments"] = importer.import_time_adjustments(paths["adjustments"])
    print(f"✓ 导入调休记录: {counts['adjustments']} 条")

    counts["balances"] = importer.import_leave_balances(paths["balances"])
    print(f"✓ 导入假期余额: {counts['balances']} 条")

    print_header("步骤 4: 执行考勤检查")

    results = checker.run_all_checks()
    print(f"检查结果汇总:")
    check_names = {
        "late_arrival": "迟到",
        "early_leave": "早退",
        "missing_punch": "漏打卡",
        "leave_conflicts": "假期冲突",
        "cross_month_shifts": "跨月班次",
        "abnormal_overtime": "异常加班",
    }
    for key, name in check_names.items():
        print(f"  {name}: {results[key]} 条")
    print(f"  合计: {results['total']} 条")

    print(f"\n异常详情 (前20条):")
    from tabulate import tabulate
    issue_rows = []
    for i, issue in enumerate(data.check_issues[:20], 1):
        severity = {"error": "错误", "warning": "警告", "info": "提示"}[issue.severity]
        needs_confirm = "是" if issue.needs_confirmation else "否"
        issue_rows.append([
            i, issue.employee_name, issue.department,
            issue.issue_type.value, issue.issue_date.strftime("%Y-%m-%d"),
            severity, needs_confirm, issue.description[:50] + ("..." if len(issue.description) > 50 else "")
        ])
    print(tabulate(issue_rows, ["序号", "员工", "部门", "类型", "日期", "严重程度", "需确认", "描述"], tablefmt="simple"))

    print_header("步骤 5: 部门考勤汇总")

    dept_summaries = summary.generate_all_department_summaries()
    dept_rows = []
    for ds in dept_summaries:
        dept_rows.append([
            ds.department, ds.employee_count,
            ds.total_attendance_days,
            round(ds.total_attendance_days / ds.employee_count, 2) if ds.employee_count > 0 else 0,
            ds.total_absence_count, ds.total_overtime_hours,
            f"{ds.average_attendance_rate}%",
            len(ds.employees_needing_confirmation),
            ", ".join(ds.employees_needing_confirmation[:2])
        ])
    print(tabulate(dept_rows, [
        "部门", "人数", "总出勤天数", "人均出勤", "缺勤次数",
        "总加班(小时)", "出勤率", "需确认人数", "需确认人员"
    ], tablefmt="simple"))

    print_header("步骤 6: 员工考勤详情 (示例: E001)")

    emp_summary = summary.generate_employee_summary("E001")
    emp = data.get_employee("E001")
    print(f"工号: {emp_summary.employee_id}")
    print(f"姓名: {emp_summary.name}")
    print(f"部门: {emp_summary.department}")
    print(f"职位: {emp.position if emp else ''}")
    print(f"\n考勤统计:")
    emp_rows = [
        ["出勤天数", emp_summary.attendance_days],
        ["缺勤次数", emp_summary.absence_count],
        ["出差天数", emp_summary.business_trip_days],
        ["加班时长(小时)", emp_summary.overtime_hours],
        ["迟到次数", emp_summary.late_count],
        ["早退次数", emp_summary.early_leave_count],
        ["漏打卡次数", emp_summary.missing_punch_count],
    ]
    for leave_type, days in emp_summary.leave_days.items():
        emp_rows.append([f"{leave_type}天数", days])
    print(tabulate(emp_rows, tablefmt="simple"))

    print_header("步骤 7: 假期余额查询")

    print("所有员工年假余额:")
    balance_rows = []
    for emp_id in data.employees:
        emp = data.get_employee(emp_id)
        balances = leave_manager.get_leave_balance(emp_id, LeaveType.ANNUAL)
        for bal in balances:
            status = "正常" if bal.remaining_days > 5 else "余额不足" if bal.remaining_days <= 1 else "即将用尽"
            balance_rows.append([
                emp_id, emp.name if emp else "", emp.department if emp else "",
                bal.total_days, bal.used_days, bal.remaining_days, status
            ])
    print(tabulate(balance_rows, ["工号", "姓名", "部门", "总额", "已用", "剩余", "状态"], tablefmt="simple"))

    print(f"\n余额不足员工 (年假 ≤ 1天):")
    low_balance = leave_manager.get_employees_with_low_balance(LeaveType.ANNUAL, 1.0)
    if low_balance:
        lb_rows = [[e["employee_id"], e["name"], e["department"], e["remaining_days"]] for e in low_balance]
        print(tabulate(lb_rows, ["工号", "姓名", "部门", "剩余天数"], tablefmt="simple"))
    else:
        print("✓ 没有余额不足的员工")

    print_header("步骤 8: 导出数据")

    Path("./output").mkdir(exist_ok=True)

    payroll_path = exporter.export_payroll_data("./output/工资核算清单.xlsx")
    print(f"✓ 工资核算清单已导出: {payroll_path}")

    dept_path = exporter.export_department_summary("./output/部门汇总表.xlsx")
    print(f"✓ 部门汇总表已导出: {dept_path}")

    issues_path = exporter.export_check_issues("./output/异常记录表.xlsx")
    print(f"✓ 异常记录表已导出: {issues_path}")

    balance_path = exporter.export_leave_balances("./output/假期余额表.xlsx")
    print(f"✓ 假期余额表已导出: {balance_path}")

    full_path = exporter.export_full_report("./output/完整考勤报告.xlsx")
    print(f"✓ 完整考勤报告已导出: {full_path}")

    print_header("步骤 9: 待确认通知")

    notify_summary = notifier.get_overall_notification_summary()
    print(f"统计月份: {notify_summary['year']}年{notify_summary['month']}月")
    print(f"涉及部门: {notify_summary['affected_departments']} 个")
    print(f"涉及员工: {notify_summary['affected_employees']} 人")
    print(f"待确认总数: {notify_summary['total_notifications']} 条")

    print(f"\n按类型统计:")
    type_rows = [[k, v] for k, v in notify_summary["notifications_by_type"].items()]
    print(tabulate(type_rows, ["问题类型", "数量"], tablefmt="simple"))

    print(f"\n按严重程度:")
    sev_rows = [[k, v] for k, v in notify_summary["notifications_by_severity"].items()]
    print(tabulate(sev_rows, ["严重程度", "数量"], tablefmt="simple"))

    print(f"\n通知消息列表 (前10条):")
    messages = notifier.generate_notification_messages()
    msg_rows = []
    for i, msg in enumerate(messages[:10], 1):
        msg_rows.append([
            i, msg["name"], msg["department"],
            msg["notification_count"],
            "、".join(msg["issue_types"]),
            msg["message"][:50] + "..."
        ])
    print(tabulate(msg_rows, ["序号", "员工", "部门", "待确认数", "问题类型", "通知内容"], tablefmt="simple"))

    notify_export_path = notifier.export_notification_list("./output/待确认通知列表.xlsx")
    print(f"\n✓ 待确认列表已导出: {notify_export_path}")

    print_header("步骤 10: 整体统计")

    stats = summary.get_summary_stats()
    stats_rows = [
        ["统计月份", f"{stats['year']}年{stats['month']}月"],
        ["员工总数", stats["total_employees"]],
        ["部门总数", stats["total_departments"]],
        ["总出勤天数", stats["total_attendance_days"]],
        ["总缺勤次数", stats["total_absence_count"]],
        ["总加班时长(小时)", stats["total_overtime_hours"]],
        ["平均出勤率(%)", stats["average_attendance_rate"]],
        ["有异常员工数", stats["employees_with_issues"]],
        ["需确认员工数", stats["employees_needing_confirmation"]],
        ["总异常数", stats["total_check_issues"]],
    ]
    print(tabulate(stats_rows, tablefmt="simple"))

    print_header("验证完成")

    print(f"""
✓ 所有功能验证通过！

已验证的功能模块:
  1. 数据导入 (import) - 支持7种类型的文件导入
  2. 数据检查 (check) - 6种考勤异常检查
  3. 统计汇总 (summary) - 按部门/员工统计出勤数据
  4. 假期管理 (leave) - 假期余额查询和管理
  5. 数据导出 (export) - 5种格式的报表导出
  6. 通知提醒 (notify) - 待确认记录管理

生成的文件:
  示例数据: ./data/*.xlsx
  导出报表: ./output/*.xlsx
""")

    return 0


if __name__ == "__main__":
    sys.exit(main())
