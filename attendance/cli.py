import click
import sys
from datetime import datetime
from tabulate import tabulate
from typing import Optional

from .models import AttendanceData, CheckIssueType, LeaveType
from .importer import DataImporter
from .checker import AttendanceChecker
from .summary import AttendanceSummary
from .leave_manager import LeaveManager
from .exporter import DataExporter
from .notifier import Notifier


class Context:
    def __init__(self):
        self.data = AttendanceData()
        self.importer: Optional[DataImporter] = None
        self.checker: Optional[AttendanceChecker] = None
        self.summary: Optional[AttendanceSummary] = None
        self.leave_manager: Optional[LeaveManager] = None
        self.exporter: Optional[DataExporter] = None
        self.notifier: Optional[Notifier] = None
        self.data_dir: str = "./data"
        self.output_dir: str = "./output"

    def init_managers(self):
        self.importer = DataImporter(self.data)
        self.checker = AttendanceChecker(self.data)
        self.summary = AttendanceSummary(self.data)
        self.leave_manager = LeaveManager(self.data)
        self.exporter = DataExporter(self.data)
        self.notifier = Notifier(self.data)


pass_ctx = click.make_pass_decorator(Context)


@click.group()
@click.version_option(version="1.0.0", prog_name="attendance")
@click.option("--data-dir", default="./data", help="数据文件目录")
@click.option("--output-dir", default="./output", help="输出文件目录")
@click.pass_context
def cli(ctx, data_dir: str, output_dir: str):
    """人力资源考勤数据管理命令行工具"""
    ctx_obj = Context()
    ctx_obj.data_dir = data_dir
    ctx_obj.output_dir = output_dir
    ctx_obj.init_managers()
    ctx.obj = ctx_obj


@cli.command()
@click.option("--file", "-f", required=True, help="文件路径")
@click.option("--type", "-t", "file_type", required=True,
              type=click.Choice(["employee", "punch", "leave", "trip", "overtime", "adjust", "balance"]),
              help="文件类型: employee(员工), punch(打卡), leave(请假), trip(出差), overtime(加班), adjust(调休), balance(余额)")
@pass_ctx
def import_cmd(ctx: Context, file: str, file_type: str):
    """导入考勤相关文件"""
    type_names = {
        "employee": "员工信息",
        "punch": "打卡记录",
        "leave": "请假记录",
        "trip": "出差记录",
        "overtime": "加班记录",
        "adjust": "调休记录",
        "balance": "假期余额"
    }

    try:
        count = ctx.importer.import_file(file, file_type)
        click.echo(f"\n✓ 成功导入 {type_names[file_type]} 数据，共 {count} 条记录")

        if file_type == "punch" and ctx.data.year and ctx.data.month:
            click.echo(f"  统计月份: {ctx.data.year}年{ctx.data.month}月")

        _show_data_overview(ctx)

    except FileNotFoundError as e:
        click.echo(f"✗ 错误: {e}", err=True)
        sys.exit(1)
    except ValueError as e:
        click.echo(f"✗ 错误: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"✗ 导入失败: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--check-type", "-c", multiple=True,
              type=click.Choice(["late", "early", "missing", "conflict", "cross_month", "overtime"]),
              help="指定检查类型，可多选。不指定则执行全部检查")
@pass_ctx
def check(ctx: Context, check_type):
    """检查考勤异常（迟到、早退、漏打卡、假期冲突、跨月班次、异常加班）"""
    if not ctx.data.punch_records and not check_type:
        click.echo("⚠ 未找到打卡数据，请先执行 import 命令导入数据")
        return

    check_map = {
        "late": ("迟到检查", ctx.checker.check_late_arrival),
        "early": ("早退检查", ctx.checker.check_early_leave),
        "missing": ("漏打卡检查", ctx.checker.check_missing_punch),
        "conflict": ("假期冲突检查", ctx.checker.check_leave_conflicts),
        "cross_month": ("跨月班次检查", ctx.checker.check_cross_month_shifts),
        "overtime": ("异常加班检查", ctx.checker.check_abnormal_overtime),
    }

    click.echo("\n" + "=" * 60)
    click.echo("考勤异常检查")
    click.echo("=" * 60)

    if check_type:
        ctx.data.check_issues.clear()
        results = {}
        for ct in check_type:
            name, func = check_map[ct]
            click.echo(f"\n正在执行 {name}...")
            count = func()
            results[ct] = count
            click.echo(f"  发现 {count} 条异常")
        results["total"] = sum(results.values())
    else:
        click.echo("\n正在执行全部检查...")
        results = ctx.checker.run_all_checks()

    click.echo("\n" + "-" * 60)
    click.echo("检查结果汇总")
    click.echo("-" * 60)

    result_headers = ["检查项目", "异常数量"]
    result_rows = []

    check_names = {
        "late_arrival": "迟到",
        "early_leave": "早退",
        "missing_punch": "漏打卡",
        "leave_conflicts": "假期冲突",
        "cross_month_shifts": "跨月班次",
        "abnormal_overtime": "异常加班",
    }

    for key, name in check_names.items():
        if key in results:
            count = results[key]
            result_rows.append([name, click.style(str(count), fg="red" if count > 0 else "green")])

    result_rows.append(["-" * 10, "-" * 10])
    result_rows.append(["合计", click.style(str(results.get("total", 0)), bold=True)])

    click.echo(tabulate(result_rows, result_headers, tablefmt="simple"))

    if ctx.data.check_issues:
        click.echo("\n" + "-" * 60)
        click.echo("异常详情")
        click.echo("-" * 60)

        detail_headers = ["序号", "员工", "部门", "类型", "日期", "严重程度", "需确认", "描述"]
        detail_rows = []

        for i, issue in enumerate(ctx.data.check_issues[:50], 1):
            severity_style = {"error": "red", "warning": "yellow", "info": "blue"}
            severity = click.style(
                {"error": "错误", "warning": "警告", "info": "提示"}[issue.severity],
                fg=severity_style.get(issue.severity, "white")
            )
            needs_confirm = click.style("是", fg="red") if issue.needs_confirmation else "否"

            detail_rows.append([
                i, issue.employee_name, issue.department,
                issue.issue_type.value, issue.issue_date.strftime("%Y-%m-%d"),
                severity, needs_confirm, issue.description
            ])

        click.echo(tabulate(detail_rows, detail_headers, tablefmt="simple"))

        if len(ctx.data.check_issues) > 50:
            click.echo(f"\n... 还有 {len(ctx.data.check_issues) - 50} 条异常未显示，使用 export 命令导出完整报告")

    needs_confirm = [i for i in ctx.data.check_issues if i.needs_confirmation]
    if needs_confirm:
        click.echo(f"\n⚠ 共有 {len(needs_confirm)} 条记录需要员工确认，可使用 notify 命令查看详情")


@cli.command()
@click.option("--department", "-d", help="指定部门，不指定则显示所有部门")
@click.option("--employee", "-e", help="指定员工工号，显示该员工详情")
@pass_ctx
def summary(ctx: Context, department: Optional[str], employee: Optional[str]):
    """按部门输出出勤统计（出勤天数、缺勤次数、加班时长、需确认人员）"""
    if not ctx.data.employees:
        click.echo("⚠ 未找到员工数据，请先执行 import 命令导入员工信息")
        return

    click.echo("\n" + "=" * 60)

    if employee:
        click.echo(f"员工考勤详情 - {employee}")
        click.echo("=" * 60)

        try:
            emp_summary = ctx.summary.generate_employee_summary(employee)
            emp = ctx.data.get_employee(employee)

            info_rows = [
                ["工号", emp_summary.employee_id],
                ["姓名", emp_summary.name],
                ["部门", emp_summary.department],
                ["职位", emp.position if emp else ""],
                ["统计月份", f"{ctx.data.year}年{ctx.data.month}月" if ctx.data.year else "全部"],
            ]
            click.echo(tabulate(info_rows, tablefmt="plain"))

            click.echo("\n" + "-" * 60)
            click.echo("考勤统计")
            click.echo("-" * 60)

            stat_rows = [
                ["出勤天数", emp_summary.attendance_days],
                ["缺勤次数", click.style(str(emp_summary.absence_count), fg="red" if emp_summary.absence_count > 0 else "green")],
                ["出差天数", emp_summary.business_trip_days],
                ["加班时长(小时)", emp_summary.overtime_hours],
                ["迟到次数", click.style(str(emp_summary.late_count), fg="yellow" if emp_summary.late_count > 0 else "green")],
                ["早退次数", click.style(str(emp_summary.early_leave_count), fg="yellow" if emp_summary.early_leave_count > 0 else "green")],
                ["漏打卡次数", click.style(str(emp_summary.missing_punch_count), fg="yellow" if emp_summary.missing_punch_count > 0 else "green")],
            ]

            if emp_summary.leave_days:
                for leave_type, days in emp_summary.leave_days.items():
                    stat_rows.append([f"{leave_type}天数", days])

            click.echo(tabulate(stat_rows, tablefmt="simple"))

            if emp_summary.issues:
                click.echo("\n" + "-" * 60)
                click.echo("异常记录")
                click.echo("-" * 60)

                issue_rows = []
                for i, issue in enumerate(emp_summary.issues, 1):
                    severity_style = {"error": "red", "warning": "yellow", "info": "blue"}
                    severity = click.style(
                        {"error": "错误", "warning": "警告", "info": "提示"}[issue.severity],
                        fg=severity_style.get(issue.severity, "white")
                    )
                    needs_confirm = click.style("需确认", fg="red") if issue.needs_confirmation else ""
                    issue_rows.append([
                        i, issue.issue_type.value, issue.issue_date.strftime("%Y-%m-%d"),
                        severity, needs_confirm, issue.description
                    ])

                click.echo(tabulate(issue_rows, ["序号", "类型", "日期", "严重程度", "需确认", "描述"], tablefmt="simple"))

        except ValueError as e:
            click.echo(f"✗ 错误: {e}", err=True)
            sys.exit(1)

    else:
        if ctx.data.year and ctx.data.month:
            click.echo(f"部门考勤汇总 - {ctx.data.year}年{ctx.data.month}月")
        else:
            click.echo("部门考勤汇总")
        click.echo("=" * 60)

        if department:
            dept_summaries = [ctx.summary.generate_department_summary(department)]
        else:
            dept_summaries = ctx.summary.generate_all_department_summaries()

        headers = ["部门", "人数", "总出勤天数", "人均出勤", "缺勤次数", "总加班(小时)", "人均加班", "出勤率(%)", "需确认人数", "需确认人员"]
        rows = []

        for ds in dept_summaries:
            attendance_color = "green" if ds.average_attendance_rate >= 95 else "yellow" if ds.average_attendance_rate >= 85 else "red"
            rows.append([
                ds.department,
                ds.employee_count,
                ds.total_attendance_days,
                round(ds.total_attendance_days / ds.employee_count, 2) if ds.employee_count > 0 else 0,
                click.style(str(ds.total_absence_count), fg="red" if ds.total_absence_count > 0 else "green"),
                ds.total_overtime_hours,
                round(ds.total_overtime_hours / ds.employee_count, 2) if ds.employee_count > 0 else 0,
                click.style(str(ds.average_attendance_rate), fg=attendance_color),
                click.style(str(len(ds.employees_needing_confirmation)), fg="red" if ds.employees_needing_confirmation else "green"),
                ", ".join(ds.employees_needing_confirmation[:3]) + ("..." if len(ds.employees_needing_confirmation) > 3 else "")
            ])

        click.echo(tabulate(rows, headers, tablefmt="simple"))

        stats = ctx.summary.get_summary_stats()
        click.echo("\n" + "-" * 60)
        click.echo("整体统计")
        click.echo("-" * 60)
        overall_rows = [
            ["员工总数", stats["total_employees"]],
            ["部门总数", stats["total_departments"]],
            ["总出勤天数", stats["total_attendance_days"]],
            ["总缺勤次数", stats["total_absence_count"]],
            ["总加班时长(小时)", stats["total_overtime_hours"]],
            ["平均出勤率(%)", stats["average_attendance_rate"]],
            ["有异常员工数", click.style(str(stats["employees_with_issues"]), fg="yellow" if stats["employees_with_issues"] > 0 else "green")],
            ["需确认员工数", click.style(str(stats["employees_needing_confirmation"]), fg="red" if stats["employees_needing_confirmation"] > 0 else "green")],
            ["总异常数", click.style(str(stats["total_check_issues"]), fg="yellow" if stats["total_check_issues"] > 0 else "green")],
        ]
        click.echo(tabulate(overall_rows, tablefmt="simple"))


@cli.command()
@click.option("--employee", "-e", help="指定员工工号，不指定则显示所有员工")
@click.option("--leave-type", "-t",
              type=click.Choice(["annual", "sick", "personal", "marriage", "maternity", "paternity", "bereavement", "other"]),
              help="指定假期类型")
@click.option("--low-balance", is_flag=True, help="只显示余额不足的员工")
@pass_ctx
def leave(ctx: Context, employee: Optional[str], leave_type: Optional[str], low_balance: bool):
    """查询员工假期余额"""
    if not ctx.data.employees:
        click.echo("⚠ 未找到员工数据，请先执行 import 命令导入员工信息")
        return

    click.echo("\n" + "=" * 60)
    click.echo("假期余额查询")
    click.echo("=" * 60)

    lt = None
    if leave_type:
        lt_map = {
            "annual": LeaveType.ANNUAL,
            "sick": LeaveType.SICK,
            "personal": LeaveType.PERSONAL,
            "marriage": LeaveType.MARRIAGE,
            "maternity": LeaveType.MATERNITY,
            "paternity": LeaveType.PATERNITY,
            "bereavement": LeaveType.BEREAVEMENT,
            "other": LeaveType.OTHER,
        }
        lt = lt_map[leave_type]

    if low_balance and lt:
        employees = ctx.leave_manager.get_employees_with_low_balance(lt, 1.0)
        if not employees:
            click.echo(f"✓ 没有{lt.value}余额不足的员工")
            return

        headers = ["工号", "姓名", "部门", "假期类型", "总额", "已用", "剩余"]
        rows = []
        for emp in employees:
            remaining_color = "red" if emp["remaining_days"] <= 0 else "yellow"
            rows.append([
                emp["employee_id"], emp["name"], emp["department"],
                emp["leave_type"], emp["total_days"],
                emp["total_days"] - emp["remaining_days"],
                click.style(str(emp["remaining_days"]), fg=remaining_color)
            ])
        click.echo(tabulate(rows, headers, tablefmt="simple"))
        return

    if employee:
        balances = ctx.leave_manager.get_leave_balance(employee, lt)
        if not balances:
            click.echo(f"✗ 未找到员工 {employee} 的假期余额数据")
            return

        emp = ctx.data.get_employee(employee)
        click.echo(f"\n员工: {emp.name if emp else employee} ({employee})")
        if emp:
            click.echo(f"部门: {emp.department}")

        click.echo("\n" + "-" * 60)
        headers = ["假期类型", "总额(天)", "已用(天)", "剩余(天)", "状态"]
        rows = []

        for bal in balances:
            remaining_color = "green" if bal.remaining_days > 5 else "yellow" if bal.remaining_days > 1 else "red"
            status = "正常" if bal.remaining_days > 5 else "余额不足" if bal.remaining_days <= 1 else "即将用尽"

            rows.append([
                bal.leave_type.value,
                bal.total_days,
                bal.used_days,
                click.style(str(bal.remaining_days), fg=remaining_color),
                click.style(status, fg=remaining_color)
            ])

        click.echo(tabulate(rows, headers, tablefmt="simple"))

        records = ctx.leave_manager.get_leave_records(employee, lt)
        if records:
            click.echo("\n" + "-" * 60)
            click.echo("请假记录")
            click.echo("-" * 60)

            rec_headers = ["序号", "假别", "开始日期", "结束日期", "天数", "原因", "状态"]
            rec_rows = []
            for i, rec in enumerate(records[:20], 1):
                status = click.style("已批准", fg="green") if rec.approved else click.style("待审批", fg="yellow")
                rec_rows.append([
                    i, rec.leave_type.value,
                    rec.start_date.strftime("%Y-%m-%d"),
                    rec.end_date.strftime("%Y-%m-%d"),
                    rec.days, rec.reason[:20] if rec.reason else "",
                    status
                ])
            click.echo(tabulate(rec_rows, rec_headers, tablefmt="simple"))

    else:
        all_balances = ctx.leave_manager.get_all_leave_balances()

        headers = ["工号", "姓名", "部门"]
        leave_types = [lt for lt in LeaveType]
        for lt in leave_types:
            if lt == LeaveType.ANNUAL or (lt_map and lt == lt):
                headers.append(f"{lt.value}(总/用/余)")

        rows = []
        for emp_id, balances in all_balances.items():
            emp = ctx.data.get_employee(emp_id)
            if not emp:
                continue

            row = [emp_id, emp.name, emp.department]

            for bal in balances:
                if lt and bal.leave_type != lt:
                    continue
                if bal.total_days == 0 and not leave_type:
                    continue

                remaining_color = "green" if bal.remaining_days > 5 else "yellow" if bal.remaining_days > 1 else "red"
                row.append(f"{bal.total_days}/{bal.used_days}/{click.style(str(bal.remaining_days), fg=remaining_color)}")

            if len(row) > 3:
                rows.append(row)

        if rows:
            click.echo(tabulate(rows, headers, tablefmt="simple"))
        else:
            click.echo("⚠ 未找到假期余额数据，请先导入假期余额文件")

    leave_stats = ctx.leave_manager.get_leave_statistics()
    click.echo("\n" + "-" * 60)
    click.echo("本月请假统计")
    click.echo("-" * 60)
    stat_rows = [
        ["请假记录总数", leave_stats["total_leave_records"]],
        ["已批准", leave_stats["approved_leaves"]],
        ["待审批", leave_stats["pending_leaves"]],
        ["总请假天数", leave_stats["total_leave_days"]],
    ]
    click.echo(tabulate(stat_rows, tablefmt="simple"))

    if leave_stats["leave_type_count"]:
        click.echo("\n按假别统计:")
        type_rows = []
        for lt_name, count in leave_stats["leave_type_count"].items():
            days = leave_stats["leave_type_days"].get(lt_name, 0)
            type_rows.append([lt_name, count, days])
        click.echo(tabulate(type_rows, ["假别", "次数", "天数"], tablefmt="simple"))


@cli.command()
@click.option("--type", "-t", "export_type",
              type=click.Choice(["payroll", "department", "issues", "balance", "full"]),
              default="payroll", help="导出类型: payroll(工资核算), department(部门汇总), issues(异常记录), balance(假期余额), full(完整报告)")
@click.option("--output", "-o", help="输出文件路径")
@click.option("--format", "-f", "fmt",
              type=click.Choice(["xlsx", "csv"]),
              default="xlsx", help="输出格式")
@pass_ctx
def export(ctx: Context, export_type: str, output: Optional[str], fmt: str):
    """生成工资核算用清单"""
    if not ctx.data.employees:
        click.echo("⚠ 未找到员工数据，请先执行 import 命令导入数据")
        return

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    type_names = {
        "payroll": "工资核算清单",
        "department": "部门汇总表",
        "issues": "异常记录表",
        "balance": "假期余额表",
        "full": "完整考勤报告",
    }

    if not output:
        filename = f"{type_names[export_type]}_{timestamp}.{fmt}"
        output = f"{ctx.output_dir}/{filename}"

    try:
        click.echo(f"\n正在生成 {type_names[export_type]}...")

        if export_type == "payroll":
            path = ctx.exporter.export_payroll_data(output)
        elif export_type == "department":
            path = ctx.exporter.export_department_summary(output)
        elif export_type == "issues":
            path = ctx.exporter.export_check_issues(output)
        elif export_type == "balance":
            path = ctx.exporter.export_leave_balances(output)
        elif export_type == "full":
            if fmt == "csv":
                output = output.replace(".csv", ".xlsx")
            path = ctx.exporter.export_full_report(output)

        click.echo(f"\n✓ 导出成功！文件已保存至: {path}")

        if export_type == "payroll":
            emp_count = len(ctx.data.employees)
            click.echo(f"  包含 {emp_count} 名员工的工资核算数据")
        elif export_type == "issues":
            issue_count = len(ctx.data.check_issues)
            click.echo(f"  包含 {issue_count} 条异常记录")

    except Exception as e:
        click.echo(f"✗ 导出失败: {e}", err=True)
        sys.exit(1)


@cli.command()
@click.option("--employee", "-e", help="指定员工工号")
@click.option("--department", "-d", help="指定部门")
@click.option("--export", "-o", "export_path", help="导出待确认列表到文件")
@pass_ctx
def notify(ctx: Context, employee: Optional[str], department: Optional[str], export_path: Optional[str]):
    """列出需要员工补充说明的记录"""
    if not ctx.data.check_issues:
        click.echo("⚠ 未找到异常记录，请先执行 check 命令进行检查")
        return

    needs_confirm = [i for i in ctx.data.check_issues if i.needs_confirmation]
    if not needs_confirm:
        click.echo("✓ 没有需要员工确认的记录")
        return

    click.echo("\n" + "=" * 60)
    click.echo("待员工确认记录")
    click.echo("=" * 60)

    summary = ctx.notifier.get_overall_notification_summary()
    click.echo(f"\n统计月份: {summary['year']}年{summary['month']}月")
    click.echo(f"涉及部门: {summary['affected_departments']} 个")
    click.echo(f"涉及员工: {summary['affected_employees']} 人")
    click.echo(f"待确认总数: {click.style(str(summary['total_notifications']), fg='red')} 条")

    click.echo("\n按类型统计:")
    type_rows = [[k, v] for k, v in summary["notifications_by_type"].items()]
    click.echo(tabulate(type_rows, ["问题类型", "数量"], tablefmt="simple"))

    click.echo("\n按严重程度:")
    sev_rows = [[k, v] for k, v in summary["notifications_by_severity"].items()]
    click.echo(tabulate(sev_rows, ["严重程度", "数量"], tablefmt="simple"))

    click.echo("\n" + "-" * 60)

    if employee:
        emp_summary = ctx.notifier.get_employee_notification_summary(employee)
        click.echo(f"\n员工 {emp_summary['name']} ({employee}) 待确认记录:")

        if emp_summary["total_notifications"] == 0:
            click.echo("✓ 该员工没有需要确认的记录")
        else:
            type_rows = [[k, v] for k, v in emp_summary["notifications_by_type"].items()]
            click.echo(tabulate(type_rows, ["问题类型", "数量"], tablefmt="simple"))

            click.echo("\n详细记录:")
            issue_rows = []
            for i, issue in enumerate(emp_summary["issues"], 1):
                severity_style = {"error": "red", "warning": "yellow", "info": "blue"}
                severity = click.style(
                    {"error": "错误", "warning": "警告", "info": "提示"}[issue.severity],
                    fg=severity_style.get(issue.severity, "white")
                )
                issue_rows.append([
                    i, issue.issue_type.value, issue.issue_date.strftime("%Y-%m-%d"),
                    severity, issue.description
                ])
            click.echo(tabulate(issue_rows, ["序号", "类型", "日期", "严重程度", "描述"], tablefmt="simple"))

    elif department:
        dept_summary = ctx.notifier.get_department_notification_summary(department)
        click.echo(f"\n部门 {department} 待确认记录:")

        if dept_summary["total_notifications"] == 0:
            click.echo("✓ 该部门没有需要确认的记录")
        else:
            click.echo(f"涉及员工: {dept_summary['affected_employees']} 人")
            click.echo(f"待确认总数: {dept_summary['total_notifications']} 条")

            emp_rows = [[k, v] for k, v in dept_summary["notifications_by_employee"].items()]
            click.echo("\n按员工统计:")
            click.echo(tabulate(emp_rows, ["员工", "数量"], tablefmt="simple"))

    else:
        messages = ctx.notifier.generate_notification_messages()

        click.echo("\n通知列表:")
        msg_headers = ["序号", "员工", "部门", "待确认数", "问题类型", "通知内容"]
        msg_rows = []

        for i, msg in enumerate(messages, 1):
            msg_rows.append([
                i, msg["name"], msg["department"],
                click.style(str(msg["notification_count"]), fg="red"),
                "、".join(msg["issue_types"]),
                msg["message"]
            ])

        click.echo(tabulate(msg_rows, msg_headers, tablefmt="simple"))

        reminders = ctx.notifier.get_reminder_list()
        urgent = [r for r in reminders if r["is_urgent"]]

        if urgent:
            click.echo("\n" + "-" * 60)
            click.echo(click.style("⚠ 紧急提醒（待确认超过7天）", fg="red", bold=True))
            click.echo("-" * 60)

            urgent_rows = []
            for r in urgent[:10]:
                urgent_rows.append([
                    r["name"], r["department"], r["pending_count"],
                    r["oldest_issue_date"], r["days_pending"], r["deadline"]
                ])

            click.echo(tabulate(
                urgent_rows,
                ["员工", "部门", "待确认数", "最早日期", "已等待(天)", "截止日期"],
                tablefmt="simple"
            ))

    if export_path:
        rows = ctx.notifier.export_notification_list(export_path)
        click.echo(f"\n✓ 待确认列表已导出至: {export_path}")
        click.echo(f"  共 {len(rows)} 条记录")


def _show_data_overview(ctx: Context):
    click.echo("\n当前数据概览:")
    overview_rows = [
        ["员工信息", len(ctx.data.employees)],
        ["打卡记录", len(ctx.data.punch_records)],
        ["请假记录", len(ctx.data.leave_records)],
        ["出差记录", len(ctx.data.business_trip_records)],
        ["加班记录", len(ctx.data.overtime_records)],
        ["调休记录", len(ctx.data.time_adjustment_records)],
        ["假期余额", sum(len(v) for v in ctx.data.leave_balances.values())],
        ["检查异常", len(ctx.data.check_issues)],
    ]
    click.echo(tabulate(overview_rows, tablefmt="simple"))


if __name__ == "__main__":
    cli()
