import click
import sys
from datetime import datetime
from tabulate import tabulate
from typing import Optional
import os
import re

from .models import AttendanceData, LeaveType, ImportResult
from .importer import DataImporter
from .checker import AttendanceChecker
from .summary import AttendanceSummary
from .leave_manager import LeaveManager
from .exporter import DataExporter
from .notifier import Notifier
from .store import DataStore


class Context:
    def __init__(self, data_dir: str = "./data", output_dir: str = "./output"):
        self.data_dir = data_dir
        self.output_dir = output_dir
        self.store = DataStore("./.attendance_data")
        self.data: AttendanceData = self._load_or_create_data()
        self._init_managers()

    def _load_or_create_data(self) -> AttendanceData:
        current_month = self.store.get_current_month()
        if current_month:
            data = self.store.load(current_month)
            if data:
                return data

        now = datetime.now()
        default_month = f"{now.year}-{now.month:02d}"
        return self.store.load_or_create(default_month)

    def _init_managers(self):
        self.importer = DataImporter(self.data)
        self.checker = AttendanceChecker(self.data)
        self.summary = AttendanceSummary(self.data)
        self.leave_manager = LeaveManager(self.data)
        self.exporter = DataExporter(self.data)
        self.notifier = Notifier(self.data)

    def _reinit_managers(self):
        self.importer = DataImporter(self.data)
        self.checker = AttendanceChecker(self.data)
        self.summary = AttendanceSummary(self.data)
        self.leave_manager = LeaveManager(self.data)
        self.exporter = DataExporter(self.data)
        self.notifier = Notifier(self.data)

    def save(self):
        self.store.save(self.data)

    def switch_month(self, month_str: str):
        if not re.match(r'^\d{4}-\d{2}$', month_str):
            raise ValueError(f"月份格式错误，请使用 YYYY-MM 格式，如 2026-05")

        self.data = self.store.switch_month(month_str)
        self._reinit_managers()

    def clear_current_month(self):
        current_month = self.data.month_str
        if current_month:
            self.store.clear_month(current_month)
        self.data = AttendanceData()
        if current_month:
            year, month = map(int, current_month.split('-'))
            self.data.set_month(year, month)
        self._reinit_managers()

    def clear_all(self):
        self.store.clear_all()
        now = datetime.now()
        default_month = f"{now.year}-{now.month:02d}"
        self.data = self.store.load_or_create(default_month)
        self._reinit_managers()

    def has_data(self) -> bool:
        return len(self.data.employees) > 0

    def run_auto_check(self, force: bool = False) -> bool:
        needs_check = force or self.data.check_dirty
        if needs_check and self.data.punch_records:
            click.echo("[INFO] 数据已更新，正在重新执行检查...")
            results = self.checker.run_all_checks()
            self.save()
            click.echo(f"   检查完成，共发现 {results['total']} 条异常记录")
            return True
        return False

    def get_current_month_display(self) -> str:
        if self.data.month_str:
            return self.data.month_str
        return "未设置"


pass_ctx = click.make_pass_decorator(Context)


def _show_current_month(ctx: Context):
    click.echo(f"[INFO] 当前工作区: {ctx.get_current_month_display()}")


def _show_import_result(result: ImportResult):
    click.echo(f"\n[OK] {result.file_type} 导入完成")
    click.echo(f"  总计: {result.total} 条")

    result_rows = []
    if result.added > 0:
        result_rows.append(["新增", click.style(str(result.added), fg="green")])
    if result.updated > 0:
        result_rows.append(["更新", click.style(str(result.updated), fg="yellow")])
    if result.skipped > 0:
        result_rows.append(["跳过", click.style(str(result.skipped), fg="cyan")])
    if result.failed > 0:
        result_rows.append(["失败", click.style(str(result.failed), fg="red")])

    if result_rows:
        click.echo(tabulate(result_rows, tablefmt="plain"))

    if result.missing_columns:
        click.echo(f"\n[ERROR] 缺少必要列: {', '.join(result.missing_columns)}")
        click.echo("  请检查文件表头，确保包含上述必要信息")

    if result.failed_reasons and result.failed > 0:
        click.echo(f"\n[WARN]  失败详情（前5条）:")
        for reason in result.failed_reasons[:5]:
            click.echo(f"  - {reason}")
        if len(result.failed_reasons) > 5:
            click.echo(f"  ... 还有 {len(result.failed_reasons) - 5} 条错误")


@click.group()
@click.version_option(version="2.0.0", prog_name="attendance")
@click.option("--data-dir", default="./data", help="数据文件目录")
@click.option("--output-dir", default="./output", help="输出文件目录")
@click.pass_context
def cli(ctx, data_dir: str, output_dir: str):
    """人力资源考勤数据管理命令行工具 - 支持按月份独立管理"""
    ctx_obj = Context(data_dir, output_dir)
    ctx.obj = ctx_obj


@cli.command("use")
@click.argument("month_str")
@pass_ctx
def use_command(ctx: Context, month_str: str):
    """切换到指定月份工作区，格式: YYYY-MM（如 2026-05）"""
    try:
        old_month = ctx.get_current_month_display()
        ctx.switch_month(month_str)
        ctx.save()
        click.echo(f"\n[OK] 已从 {old_month} 切换到 {month_str}")
        _show_data_overview(ctx, quiet=True)

        if ctx.data.check_dirty and ctx.data.punch_records:
            click.echo(f"\n[WARN]  该月份数据需要重新检查，请运行 check 命令")

    except ValueError as e:
        click.echo(f"[ERROR] {e}", err=True)
        sys.exit(1)


@cli.command("list")
@click.option("--details", "-d", is_flag=True, help="显示详细信息")
@pass_ctx
def list_command(ctx: Context, details: bool):
    """列出所有可用的月份工作区"""
    months_info = ctx.store.get_all_months_info()

    if not months_info:
        click.echo("[INFO] 暂无可用的月份数据")
        return

    click.echo(f"\n[INFO] 共找到 {len(months_info)} 个月份工作区")
    click.echo("=" * 60)

    if details:
        headers = ["月份", "当前", "员工", "打卡", "请假", "出差", "加班", "异常", "最后更新"]
        rows = []
        for info in months_info:
            current_mark = "*" if info.get("is_current") else ""
            rows.append([
                info.get("month", ""),
                current_mark,
                info.get("employees", 0),
                info.get("punch_records", 0),
                info.get("leave_records", 0),
                info.get("business_trips", 0),
                info.get("overtime_records", 0),
                info.get("check_issues", 0),
                info.get("last_updated", "")[:16] if info.get("last_updated") else ""
            ])
        click.echo(tabulate(rows, headers, tablefmt="simple"))
        click.echo("\n* 表示当前工作区")
    else:
        for info in months_info:
            prefix = "* " if info.get("is_current") else "  "
            month = info.get("month", "")
            emp_count = info.get("employees", 0)
            issue_count = info.get("check_issues", 0)
            dirty = " (需要重新检查)" if info.get("check_dirty") and issue_count > 0 else ""
            click.echo(f"{prefix}{month}  - {emp_count} 名员工, {issue_count} 条异常{dirty}")


@cli.command("import")
@click.option("--file", "-f", required=True, help="文件路径")
@click.option("--type", "-t", "file_type", required=True,
              type=click.Choice(["employee", "punch", "leave", "trip", "overtime", "adjust", "balance", "holiday"]),
              help="文件类型: employee(员工), punch(打卡), leave(请假), trip(出差), overtime(加班), adjust(调休), balance(余额), holiday(节假日)")
@pass_ctx
def import_command(ctx: Context, file: str, file_type: str):
    """导入考勤相关文件（支持员工、打卡、请假、出差、加班、调休、假期余额、节假日）"""
    _show_current_month(ctx)

    type_names = {
        "employee": "员工信息",
        "punch": "打卡记录",
        "leave": "请假记录",
        "trip": "出差记录",
        "overtime": "加班记录",
        "adjust": "调休记录",
        "balance": "假期余额",
        "holiday": "节假日设置",
    }

    try:
        result = ctx.importer.import_file(file, file_type)

        if result.missing_columns:
            _show_import_result(result)
            sys.exit(1)

        _show_import_result(result)

        if result.added > 0 or result.updated > 0:
            ctx.data.clear_check_results()
            ctx.save()
            click.echo(f"\n[INFO] 已清除旧检查结果，下次运行 check/summary/export/notify 时将自动重新计算")

        if file_type == "punch" and ctx.data.year and ctx.data.month:
            click.echo(f"  统计月份: {ctx.data.year}年{ctx.data.month}月")

        _show_data_overview(ctx)

    except FileNotFoundError as e:
        click.echo(f"[ERROR] 错误: {e}", err=True)
        sys.exit(1)
    except ValueError as e:
        click.echo(f"[ERROR] 错误: {e}", err=True)
        sys.exit(1)
    except Exception as e:
        click.echo(f"[ERROR] 导入失败: {e}", err=True)
        sys.exit(1)


@cli.command("clear")
@click.option("--month", "-m", help="清空指定月份（格式: YYYY-MM），不指定则清空当前月份")
@click.option("--all", "-a", is_flag=True, help="清空所有月份数据")
@click.option("--yes", "-y", is_flag=True, help="跳过确认直接清空")
@pass_ctx
def clear_command(ctx: Context, month: Optional[str], all: bool, yes: bool):
    """清空数据，支持按月份清空或全部清空"""
    if all:
        target = "所有月份"
    elif month:
        target = month
    else:
        target = f"当前月份 ({ctx.get_current_month_display()})"

    if not yes:
        click.echo("\n" + "=" * 60)
        click.echo(click.style(f"[WARN]  即将清空 {target} 的所有考勤数据", fg="yellow", bold=True))
        click.echo("=" * 60)

        if all:
            months = ctx.store.list_available_months()
            if months:
                click.echo(f"\n将清空以下月份:")
                for m in months:
                    click.echo(f"  - {m}")
            else:
                click.echo("\n当前没有任何月份数据")
        else:
            if ctx.has_data():
                _show_data_overview(ctx, quiet=True)
            else:
                click.echo("\n当前没有数据")

        click.echo()
        confirm = click.prompt("确认要清空吗？请输入 'yes' 继续", default="")
        if confirm.lower() != "yes":
            click.echo("已取消清空操作")
            return

    try:
        if all:
            count = ctx.store.clear_all()
            ctx.clear_all()
            click.echo(f"\n[OK] 已清空所有月份数据，共 {count} 个月份")
        elif month:
            if not re.match(r'^\d{4}-\d{2}$', month):
                raise ValueError(f"月份格式错误，请使用 YYYY-MM 格式，如 2026-05")
            success = ctx.store.delete_month(month)
            if success:
                if ctx.data.month_str == month:
                    ctx.data = ctx._load_or_create_data()
                    ctx._reinit_managers()
                click.echo(f"\n[OK] 已清空 {month} 的数据")
            else:
                click.echo(f"[WARN]  {month} 不存在或已被清空")
        else:
            ctx.clear_current_month()
            ctx.save()
            click.echo(f"\n[OK] 已清空 {target} 的所有数据")

        click.echo("  可以开始导入新的考勤数据了")

    except ValueError as e:
        click.echo(f"[ERROR] {e}", err=True)
        sys.exit(1)


@cli.command("check")
@click.option("--check-type", "-c", multiple=True,
              type=click.Choice(["late", "early", "missing", "absent", "conflict", "cross_month", "overtime"]),
              help="指定检查类型，可多选。不指定则执行全部检查")
@pass_ctx
def check_command(ctx: Context, check_type):
    """检查考勤异常（迟到、早退、漏打卡、缺勤、假期冲突、跨月班次、异常加班）"""
    _show_current_month(ctx)

    if not ctx.has_data():
        click.echo("[WARN]  当前没有数据，请先使用 import 命令导入员工信息和打卡记录")
        return

    if not ctx.data.punch_records and not check_type:
        click.echo("[WARN]  未找到打卡数据，请先使用 import -t punch 导入打卡记录")
        return

    check_map = {
        "late": ("迟到检查", ctx.checker.check_late_arrival),
        "early": ("早退检查", ctx.checker.check_early_leave),
        "missing": ("漏打卡检查", ctx.checker.check_missing_punch),
        "absent": ("缺勤检查", ctx.checker.check_absent_on_special_workdays),
        "conflict": ("假期冲突检查", ctx.checker.check_leave_conflicts),
        "cross_month": ("跨月班次检查", ctx.checker.check_cross_month_shifts),
        "overtime": ("异常加班检查", ctx.checker.check_abnormal_overtime),
    }

    click.echo("\n" + "=" * 60)
    click.echo("考勤异常检查")
    click.echo("=" * 60)

    if ctx.data.check_dirty:
        click.echo("[INFO] 检测到数据已更新，将执行全新检查")

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
        ctx.data.mark_check_done()
    else:
        click.echo("\n正在执行全部检查...")
        results = ctx.checker.run_all_checks()

    ctx.save()

    click.echo("\n" + "-" * 60)
    click.echo("检查结果汇总")
    click.echo("-" * 60)

    result_headers = ["检查项目", "异常数量"]
    result_rows = []

    check_names = {
        "late_arrival": "迟到",
        "early_leave": "早退",
        "missing_punch": "漏打卡",
        "absent": "缺勤",
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

        for i, issue in enumerate(ctx.data.get_month_issues()[:50], 1):
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

        if len(ctx.data.get_month_issues()) > 50:
            click.echo(f"\n... 还有 {len(ctx.data.get_month_issues()) - 50} 条异常未显示，使用 export 命令导出完整报告")

    needs_confirm = [i for i in ctx.data.get_month_issues() if i.needs_confirmation]
    if needs_confirm:
        click.echo(f"\n[WARN]  共有 {len(needs_confirm)} 条记录需要员工确认，可使用 notify 命令查看详情")


@cli.command("summary")
@click.option("--department", "-d", help="指定部门，不指定则显示所有部门")
@click.option("--employee", "-e", help="指定员工工号，显示该员工详情")
@pass_ctx
def summary_command(ctx: Context, department: Optional[str], employee: Optional[str]):
    """按部门输出出勤统计（出勤天数、缺勤次数、加班时长、需确认人员）"""
    _show_current_month(ctx)

    if not ctx.has_data():
        click.echo("[WARN]  当前没有数据，请先使用 import 命令导入员工信息和打卡记录")
        return

    if not ctx.data.punch_records and not ctx.data.leave_records:
        click.echo("[WARN]  未找到打卡或请假记录，统计结果可能不完整")
        click.echo("  请使用 import -t punch 导入打卡记录")

    rechecked = ctx.run_auto_check()

    click.echo("\n" + "=" * 60)

    if employee:
        click.echo(f"员工考勤详情 - {employee}")
        click.echo("=" * 60)

        if employee not in ctx.data.employees:
            click.echo(f"[ERROR] 错误: 未找到工号为 {employee} 的员工")
            return

        try:
            emp_summary = ctx.summary.generate_employee_summary(employee)
            emp = ctx.data.get_employee(employee)

            info_rows = [
                ["工号", emp_summary.employee_id],
                ["姓名", emp_summary.name],
                ["部门", emp_summary.department],
                ["职位", emp.position if emp else ""],
                ["统计月份", ctx.data.month_str or f"{ctx.data.year}年{ctx.data.month}月"],
                ["标准工作日", emp_summary.standard_workdays],
            ]
            if rechecked:
                info_rows.append(["数据状态", click.style("已重新计算", fg="green")])
            click.echo(tabulate(info_rows, tablefmt="plain"))

            click.echo("\n" + "-" * 60)
            click.echo("考勤统计")
            click.echo("-" * 60)

            stat_rows = [
                ["应出勤天数", emp_summary.standard_workdays],
                ["实际出勤天数", emp_summary.attendance_days],
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

            if emp_summary.issue_summary:
                issue_parts = [f"{k}×{v}" for k, v in emp_summary.issue_summary.items()]
                stat_rows.append(["异常汇总", "、".join(issue_parts)])

            stat_rows.append(["需确认", click.style("是", fg="red") if emp_summary.needs_confirmation else "否"])

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
                    deadline = issue.deadline.strftime("%Y-%m-%d") if issue.deadline else ""
                    issue_rows.append([
                        i, issue.issue_type.value, issue.issue_date.strftime("%Y-%m-%d"),
                        severity, needs_confirm, deadline, issue.description
                    ])

                click.echo(tabulate(issue_rows, ["序号", "类型", "日期", "严重程度", "需确认", "截止日期", "描述"], tablefmt="simple"))

        except ValueError as e:
            click.echo(f"[ERROR] 错误: {e}", err=True)
            sys.exit(1)

    else:
        if ctx.data.month_str:
            click.echo(f"部门考勤汇总 - {ctx.data.month_str}")
        else:
            click.echo("部门考勤汇总")
        click.echo("=" * 60)

        if department:
            dept_emps = [eid for eid, e in ctx.data.employees.items() if e.department == department]
            if not dept_emps:
                click.echo(f"[ERROR] 错误: 未找到部门 '{department}'")
                return
            dept_summaries = [ctx.summary.generate_department_summary(department)]
        else:
            dept_summaries = ctx.summary.generate_all_department_summaries()

        headers = ["部门", "人数", "标准工作日", "总出勤天数", "人均出勤", "缺勤次数", "总加班(小时)", "人均加班", "出勤率(%)", "需确认人数", "需确认人员"]
        rows = []

        for ds in dept_summaries:
            attendance_color = "green" if ds.average_attendance_rate >= 95 else "yellow" if ds.average_attendance_rate >= 85 else "red"
            rows.append([
                ds.department,
                ds.employee_count,
                ds.standard_workdays,
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
            ["统计月份", stats.get("month_str", f"{stats['year']}年{stats['month']}月")],
            ["标准工作日", stats["standard_workdays"]],
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
        if rechecked:
            overall_rows.append(["数据状态", click.style("已重新计算", fg="green")])
        click.echo(tabulate(overall_rows, tablefmt="simple"))


@cli.command("leave")
@click.option("--employee", "-e", help="指定员工工号，不指定则显示所有员工")
@click.option("--leave-type", "-t",
              type=click.Choice(["annual", "sick", "personal", "marriage", "maternity", "paternity", "bereavement", "other"]),
              help="指定假期类型")
@click.option("--low-balance", is_flag=True, help="只显示余额不足的员工")
@pass_ctx
def leave_command(ctx: Context, employee: Optional[str], leave_type: Optional[str], low_balance: bool):
    """查询员工假期余额"""
    _show_current_month(ctx)

    if not ctx.has_data():
        click.echo("[WARN]  当前没有数据，请先使用 import 命令导入员工信息和假期余额")
        return

    if not ctx.data.leave_balances:
        click.echo("[WARN]  未找到假期余额数据，请先使用 import -t balance 导入假期余额文件")
        return

    click.echo("\n" + "=" * 60)
    click.echo("假期余额查询")
    click.echo("=" * 60)

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

    lt = lt_map[leave_type] if leave_type else None

    if low_balance:
        if not lt:
            lt = LeaveType.ANNUAL
            click.echo(f"[INFO]  未指定假期类型，默认检查{lt.value}余额")
        employees = ctx.leave_manager.get_employees_with_low_balance(lt, 1.0)
        if not employees:
            click.echo(f"[OK] 没有{lt.value}余额不足的员工")
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
        if employee not in ctx.data.employees:
            click.echo(f"[ERROR] 错误: 未找到工号为 {employee} 的员工")
            return

        balances = ctx.leave_manager.get_leave_balance(employee, lt)

        emp = ctx.data.get_employee(employee)
        click.echo(f"\n员工: {emp.name if emp else employee} ({employee})")
        if emp:
            click.echo(f"部门: {emp.department}")

        click.echo("\n" + "-" * 60)
        headers = ["假期类型", "总额(天)", "已用(天)", "剩余(天)", "状态"]
        rows = []

        has_balance = False
        for bal in balances:
            if lt and bal.leave_type != lt:
                continue
            has_balance = True
            remaining_color = "green" if bal.remaining_days > 5 else "yellow" if bal.remaining_days > 1 else "red"
            status = "正常" if bal.remaining_days > 5 else "余额不足" if bal.remaining_days <= 1 else "即将用尽"

            rows.append([
                bal.leave_type.value,
                bal.total_days,
                bal.used_days,
                click.style(str(bal.remaining_days), fg=remaining_color),
                click.style(status, fg=remaining_color)
            ])

        if not has_balance:
            if lt:
                click.echo(f"[ERROR] 未找到员工 {employee} 的{lt.value}余额数据")
            else:
                click.echo(f"[ERROR] 未找到员工 {employee} 的假期余额数据")
            return

        click.echo(tabulate(rows, headers, tablefmt="simple"))

        records = ctx.leave_manager.get_leave_records(employee, lt)
        if records:
            click.echo("\n" + "-" * 60)
            click.echo("本月请假记录")
            click.echo("-" * 60)

            rec_headers = ["序号", "假别", "开始日期", "结束日期", "天数", "原因", "状态"]
            rec_rows = []
            for i, rec in enumerate(records[:20], 1):
                if not ctx.data.is_in_month(rec.start_date) and not ctx.data.is_in_month(rec.end_date):
                    continue
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

        all_leave_types = [lt_val for lt_val in LeaveType]
        if lt:
            all_leave_types = [lt]

        headers = ["工号", "姓名", "部门"]
        for lt_val in all_leave_types:
            headers.append(f"{lt_val.value}(总/用/余)")

        rows = []
        for emp_id in sorted(ctx.data.employees.keys()):
            emp = ctx.data.get_employee(emp_id)
            if not emp:
                continue

            balances = all_balances.get(emp_id, [])
            balance_dict = {b.leave_type: b for b in balances}

            row = [emp_id, emp.name, emp.department]

            for lt_val in all_leave_types:
                bal = balance_dict.get(lt_val)
                if bal:
                    remaining_color = "green" if bal.remaining_days > 5 else "yellow" if bal.remaining_days > 1 else "red"
                    row.append(f"{bal.total_days}/{bal.used_days}/{click.style(str(bal.remaining_days), fg=remaining_color)}")
                else:
                    row.append("-/-/-")

            rows.append(row)

        if rows:
            click.echo(tabulate(rows, headers, tablefmt="simple"))
        else:
            click.echo("[WARN]  未找到假期余额数据，请先导入假期余额文件")

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


@cli.command("export")
@click.option("--type", "-t", "export_type",
              type=click.Choice(["payroll", "department", "issues", "balance", "full"]),
              default="payroll", help="导出类型: payroll(工资核算), department(部门汇总), issues(异常记录), balance(假期余额), full(完整报告)")
@click.option("--output", "-o", help="输出文件路径")
@click.option("--format", "-f", "fmt",
              type=click.Choice(["xlsx", "csv"]),
              default="xlsx", help="输出格式")
@pass_ctx
def export_command(ctx: Context, export_type: str, output: Optional[str], fmt: str):
    """生成工资核算用清单（自动执行必要的检查）"""
    _show_current_month(ctx)

    if not ctx.has_data():
        click.echo("[WARN]  当前没有数据，请先使用 import 命令导入数据")
        return

    rechecked = False
    if export_type in ["payroll", "department", "issues", "full"]:
        rechecked = ctx.run_auto_check()

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    type_names = {
        "payroll": "工资核算清单",
        "department": "部门汇总表",
        "issues": "异常记录表",
        "balance": "假期余额表",
        "full": "完整考勤报告",
    }

    if not output:
        os.makedirs(ctx.output_dir, exist_ok=True)
        month_str = ctx.data.month_str or datetime.now().strftime("%Y-%m")
        filename = f"{month_str}_{type_names[export_type]}_{timestamp}.{fmt}"
        output = f"{ctx.output_dir}/{filename}"

    try:
        click.echo(f"\n正在生成 {type_names[export_type]}...")
        if rechecked:
            click.echo("[INFO] 基于最新数据重新计算完成")

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
                click.echo("[INFO]  完整报告仅支持 Excel 格式，已自动转换为 .xlsx")
            path = ctx.exporter.export_full_report(output)

        click.echo(f"\n[OK] 导出成功！文件已保存至: {path}")

        emp_count = len(ctx.data.employees)
        issue_count = len(ctx.data.get_month_issues())
        needs_confirm = len([i for i in ctx.data.get_month_issues() if i.needs_confirmation])

        if export_type == "payroll":
            click.echo(f"  包含 {emp_count} 名员工的工资核算数据")
            if issue_count > 0:
                click.echo(f"  其中包含 {issue_count} 条异常记录，{needs_confirm} 条需员工确认")
        elif export_type == "issues":
            click.echo(f"  包含 {issue_count} 条异常记录，{needs_confirm} 条需员工确认")
        elif export_type == "full":
            click.echo(f"  包含 {emp_count} 名员工，{issue_count} 条异常记录")

    except Exception as e:
        click.echo(f"[ERROR] 导出失败: {e}", err=True)
        sys.exit(1)


@cli.command("notify")
@click.option("--employee", "-e", help="指定员工工号")
@click.option("--department", "-d", help="指定部门")
@click.option("--export", "-o", "export_path", help="导出待确认列表到文件")
@pass_ctx
def notify_command(ctx: Context, employee: Optional[str], department: Optional[str], export_path: Optional[str]):
    """列出需要员工补充说明的记录（自动执行必要的检查）"""
    _show_current_month(ctx)

    if not ctx.has_data():
        click.echo("[WARN]  当前没有数据，请先使用 import 命令导入数据")
        return

    rechecked = ctx.run_auto_check()

    if not ctx.data.get_month_issues():
        click.echo("[OK] 没有发现异常记录，所有考勤数据正常")
        return

    needs_confirm = [i for i in ctx.data.get_month_issues() if i.needs_confirmation]
    if not needs_confirm:
        click.echo("[OK] 没有需要员工确认的记录，所有异常已处理")
        return

    click.echo("\n" + "=" * 60)
    click.echo("待员工确认记录")
    click.echo("=" * 60)

    if rechecked:
        click.echo("[INFO] 基于最新数据重新计算完成")

    summary_stats = ctx.notifier.get_overall_notification_summary()
    month_display = summary_stats.get('month_str') or "{}年{}月".format(summary_stats["year"], summary_stats["month"])
    click.echo("\n统计月份: {}".format(month_display))
    click.echo(f"涉及部门: {summary_stats['affected_departments']} 个")
    click.echo(f"涉及员工: {summary_stats['affected_employees']} 人")
    click.echo(f"待确认总数: {click.style(str(summary_stats['total_notifications']), fg='red')} 条")

    click.echo("\n按类型统计:")
    type_rows = [[k, v] for k, v in summary_stats["notifications_by_type"].items()]
    click.echo(tabulate(type_rows, ["问题类型", "数量"], tablefmt="simple"))

    click.echo("\n按严重程度:")
    sev_rows = [[k, v] for k, v in summary_stats["notifications_by_severity"].items()]
    click.echo(tabulate(sev_rows, ["严重程度", "数量"], tablefmt="simple"))

    click.echo("\n" + "-" * 60)

    if employee:
        if employee not in ctx.data.employees:
            click.echo(f"[ERROR] 错误: 未找到工号为 {employee} 的员工")
            return

        emp_summary = ctx.notifier.get_employee_notification_summary(employee)
        emp = ctx.data.get_employee(employee)
        click.echo(f"\n员工 {emp.name if emp else employee} ({employee}) 待确认记录:")

        if emp_summary["total_notifications"] == 0:
            click.echo("[OK] 该员工没有需要确认的记录")
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
                deadline = issue.deadline.strftime("%Y-%m-%d") if issue.deadline else ""
                issue_rows.append([
                    i, issue.issue_type.value, issue.issue_date.strftime("%Y-%m-%d"),
                    severity, deadline, issue.description
                ])
            click.echo(tabulate(issue_rows, ["序号", "类型", "日期", "严重程度", "截止日期", "描述"], tablefmt="simple"))

    elif department:
        dept_emps = [eid for eid, e in ctx.data.employees.items() if e.department == department]
        if not dept_emps:
            click.echo(f"[ERROR] 错误: 未找到部门 '{department}'")
            return

        dept_summary = ctx.notifier.get_department_notification_summary(department)
        click.echo(f"\n部门 {department} 待确认记录:")

        if dept_summary["total_notifications"] == 0:
            click.echo("[OK] 该部门没有需要确认的记录")
        else:
            click.echo(f"涉及员工: {dept_summary['affected_employees']} 人")
            click.echo(f"待确认总数: {dept_summary['total_notifications']} 条")

            emp_rows = [[k, v] for k, v in dept_summary["notifications_by_employee"].items()]
            click.echo("\n按员工统计:")
            click.echo(tabulate(emp_rows, ["员工", "数量"], tablefmt="simple"))

    else:
        messages = ctx.notifier.generate_notification_messages()

        click.echo("\n通知列表:")
        msg_headers = ["序号", "员工", "部门", "待确认数", "问题类型", "最早截止日期", "通知内容"]
        msg_rows = []

        for i, msg in enumerate(messages, 1):
            deadline_str = msg["earliest_deadline"].strftime("%Y-%m-%d") if msg["earliest_deadline"] else ""
            msg_rows.append([
                i, msg["name"], msg["department"],
                click.style(str(msg["notification_count"]), fg="red"),
                "、".join(msg["issue_types"]),
                deadline_str,
                msg["message"]
            ])

        click.echo(tabulate(msg_rows, msg_headers, tablefmt="simple"))

        reminders = ctx.notifier.get_reminder_list()
        urgent = [r for r in reminders if r["is_urgent"]]
        overdue = [r for r in reminders if r["is_overdue"]]

        if overdue:
            click.echo("\n" + "-" * 60)
            click.echo(click.style("[WARN]  已逾期（超过截止日期）", fg="red", bold=True))
            click.echo("-" * 60)

            overdue_rows = []
            for r in overdue[:10]:
                overdue_rows.append([
                    r["name"], r["department"], r["pending_count"],
                    r["oldest_issue_date"], r["earliest_deadline"], r["days_pending"]
                ])

            click.echo(tabulate(
                overdue_rows,
                ["员工", "部门", "待确认数", "最早日期", "截止日期", "已等待(天)"],
                tablefmt="simple"
            ))

        if urgent:
            click.echo("\n" + "-" * 60)
            click.echo(click.style("[WARN]  紧急提醒（待确认超过7天）", fg="red", bold=True))
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
        saved_path = ctx.notifier.export_notification_list(export_path)
        click.echo(f"\n[OK] 待确认列表已导出至: {saved_path}")
        click.echo(f"  共 {len(needs_confirm)} 条待确认记录")
        click.echo(f"  包含字段: 部门、工号、姓名、异常日期、异常类型、异常原因、严重程度、处理截止日期")


def _show_data_overview(ctx: Context, quiet: bool = False):
    if not quiet:
        click.echo("\n当前数据概览:")
    overview_rows = [
        ["员工信息", len(ctx.data.employees)],
        ["打卡记录", len(ctx.data.get_month_punches())],
        ["请假记录", len(ctx.data.get_month_leaves())],
        ["出差记录", len(ctx.data.get_month_business_trips())],
        ["加班记录", len(ctx.data.get_month_overtimes())],
        ["调休记录", len(ctx.data.time_adjustment_records)],
        ["假期余额", sum(len(v) for v in ctx.data.leave_balances.values())],
        ["节假日设置", len(ctx.data.holidays)],
        ["检查异常", len(ctx.data.get_month_issues())],
    ]
    if ctx.data.check_dirty and ctx.data.has_any_records():
        overview_rows.append(["数据状态", click.style("需要重新检查", fg="yellow")])
    click.echo(tabulate(overview_rows, tablefmt="simple"))


if __name__ == "__main__":
    cli()
