import pandas as pd
from datetime import datetime, date, time, timedelta
from pathlib import Path
import random
from typing import List, Dict

from .models import LeaveType, AttendanceStatus


class SampleDataGenerator:
    def __init__(self, year: int = 2026, month: int = 5):
        self.year = year
        self.month = month
        self.employees = [
            ("E001", "张三", "技术部", "高级工程师"),
            ("E002", "李四", "技术部", "工程师"),
            ("E003", "王五", "技术部", "测试工程师"),
            ("E004", "赵六", "产品部", "产品经理"),
            ("E005", "钱七", "产品部", "产品专员"),
            ("E006", "孙八", "市场部", "市场经理"),
            ("E007", "周九", "市场部", "市场专员"),
            ("E008", "吴十", "人力资源部", "HR专员"),
            ("E009", "郑十一", "财务部", "会计"),
            ("E010", "王十二", "财务部", "出纳"),
        ]
        random.seed(42)

    def _get_workdays(self) -> List[date]:
        workdays = []
        import calendar
        cal = calendar.Calendar()
        for day in cal.itermonthdays(self.year, self.month):
            if day > 0:
                d = date(self.year, self.month, day)
                if d.weekday() < 5:
                    workdays.append(d)
        return workdays

    def generate_employees(self, output_path: str) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        data = []
        for emp_id, name, dept, pos in self.employees:
            data.append({
                "工号": emp_id,
                "姓名": name,
                "部门": dept,
                "职位": pos,
                "上班时间": "09:00:00",
                "下班时间": "18:00:00"
            })
        df = pd.DataFrame(data)
        df.to_excel(output_path, index=False)
        return output_path

    def generate_punches(self, output_path: str) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        workdays = self._get_workdays()
        data = []

        for emp_id, name, dept, pos in self.employees:
            for d in workdays:
                punch_in_time = time(9, 0)
                punch_out_time = time(18, 0)
                status = AttendanceStatus.NORMAL

                rand_val = random.random()
                if emp_id == "E002" and d.day == 5:
                    punch_in_time = time(9, 45)
                    status = AttendanceStatus.LATE
                elif emp_id == "E003" and d.day == 12:
                    punch_out_time = time(17, 15)
                    status = AttendanceStatus.EARLY_LEAVE
                elif emp_id == "E005" and d.day == 8:
                    punch_in_time = None
                    status = AttendanceStatus.MISSING_PUNCH
                elif emp_id == "E007" and d.day == 15:
                    punch_in_time = None
                    punch_out_time = None
                    status = AttendanceStatus.MISSING_PUNCH
                elif emp_id == "E002" and d.day == 20:
                    punch_in_time = time(10, 30)
                    status = AttendanceStatus.LATE
                elif emp_id in ["E004", "E006"] and 10 <= d.day <= 14:
                    continue
                elif emp_id == "E009" and d.day == 22:
                    continue
                elif rand_val < 0.05:
                    punch_in_time = time(9, 12)
                    status = AttendanceStatus.LATE
                elif rand_val < 0.08:
                    punch_out_time = time(17, 45)
                    status = AttendanceStatus.EARLY_LEAVE

                punch_in = datetime.combine(d, punch_in_time) if punch_in_time else None
                punch_out = datetime.combine(d, punch_out_time) if punch_out_time else None

                data.append({
                    "工号": emp_id,
                    "日期": d.strftime("%Y-%m-%d"),
                    "上班打卡": punch_in.strftime("%Y-%m-%d %H:%M:%S") if punch_in else "",
                    "下班打卡": punch_out.strftime("%Y-%m-%d %H:%M:%S") if punch_out else "",
                    "状态": status.value
                })

        df = pd.DataFrame(data)
        df.to_excel(output_path, index=False)
        return output_path

    def generate_leaves(self, output_path: str) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        data = []

        leaves = [
            ("E004", LeaveType.ANNUAL, date(2026, 5, 10), date(2026, 5, 14), 5, "年假休息"),
            ("E006", LeaveType.ANNUAL, date(2026, 5, 10), date(2026, 5, 14), 5, "年假休息"),
            ("E009", LeaveType.SICK, date(2026, 5, 22), date(2026, 5, 22), 1, "身体不适"),
            ("E002", LeaveType.PERSONAL, date(2026, 5, 25), date(2026, 5, 26), 2, "家事处理"),
            ("E008", LeaveType.MATERNITY, date(2026, 6, 1), date(2026, 8, 31), 92, "产假"),
            ("E007", LeaveType.ANNUAL, date(2026, 5, 10), date(2026, 5, 11), 2, "重复申请"),
        ]

        for emp_id, leave_type, start, end, days, reason in leaves:
            data.append({
                "工号": emp_id,
                "假别": leave_type.value,
                "开始日期": start.strftime("%Y-%m-%d"),
                "结束日期": end.strftime("%Y-%m-%d"),
                "天数": days,
                "原因": reason,
                "审批状态": "已批准"
            })

        df = pd.DataFrame(data)
        df.to_excel(output_path, index=False)
        return output_path

    def generate_business_trips(self, output_path: str) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        data = []

        trips = [
            ("E001", date(2026, 5, 18), date(2026, 5, 20), 3, "北京", "客户现场调试"),
            ("E006", date(2026, 5, 25), date(2026, 6, 2), 7, "上海", "市场推广活动"),
            ("E004", date(2026, 5, 7), date(2026, 5, 8), 2, "深圳", "产品评审会议"),
        ]

        for emp_id, start, end, days, location, purpose in trips:
            data.append({
                "工号": emp_id,
                "开始日期": start.strftime("%Y-%m-%d"),
                "结束日期": end.strftime("%Y-%m-%d"),
                "天数": days,
                "地点": location,
                "目的": purpose
            })

        df = pd.DataFrame(data)
        df.to_excel(output_path, index=False)
        return output_path

    def generate_overtime(self, output_path: str) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        data = []

        overtimes = [
            ("E001", date(2026, 5, 12), time(18, 0), time(22, 0), 4, "项目上线"),
            ("E001", date(2026, 5, 13), time(18, 0), time(23, 0), 5, "项目上线"),
            ("E002", date(2026, 5, 15), time(18, 0), time(20, 30), 2.5, "Bug修复"),
            ("E003", date(2026, 5, 20), time(18, 0), time(19, 30), 1.5, "测试报告"),
            ("E001", date(2026, 5, 22), time(9, 0), time(12, 0), 3, "加班申请与打卡时间冲突"),
            ("E002", date(2026, 5, 28), time(18, 0), time(3, 0), 9, "超长加班"),
        ]

        for emp_id, d, start, end, hours, reason in overtimes:
            data.append({
                "工号": emp_id,
                "日期": d.strftime("%Y-%m-%d"),
                "开始时间": start.strftime("%H:%M:%S"),
                "结束时间": end.strftime("%H:%M:%S"),
                "时长": hours,
                "原因": reason,
                "审批状态": "已批准"
            })

        df = pd.DataFrame(data)
        df.to_excel(output_path, index=False)
        return output_path

    def generate_time_adjustments(self, output_path: str) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        data = []

        adjustments = [
            ("E003", date(2026, 5, 10), "调休", date(2026, 5, 20), 8, "周末加班调休"),
            ("E005", date(2026, 5, 17), "调休", date(2026, 5, 24), 4, "半天调休"),
        ]

        for emp_id, orig_date, adj_type, to_date, hours, reason in adjustments:
            data.append({
                "工号": emp_id,
                "原日期": orig_date.strftime("%Y-%m-%d"),
                "类型": adj_type,
                "调至日期": to_date.strftime("%Y-%m-%d"),
                "时长": hours,
                "原因": reason,
                "审批状态": "已批准"
            })

        df = pd.DataFrame(data)
        df.to_excel(output_path, index=False)
        return output_path

    def generate_leave_balances(self, output_path: str) -> str:
        Path(output_path).parent.mkdir(parents=True, exist_ok=True)
        data = []

        balance_data = {
            "E001": {LeaveType.ANNUAL: (10, 3, 7), LeaveType.SICK: (5, 0, 5)},
            "E002": {LeaveType.ANNUAL: (10, 5, 5), LeaveType.SICK: (5, 1, 4)},
            "E003": {LeaveType.ANNUAL: (8, 0, 8), LeaveType.SICK: (5, 0, 5)},
            "E004": {LeaveType.ANNUAL: (10, 5, 5), LeaveType.SICK: (5, 0, 5)},
            "E005": {LeaveType.ANNUAL: (8, 0, 8), LeaveType.SICK: (5, 0, 5)},
            "E006": {LeaveType.ANNUAL: (15, 5, 10), LeaveType.SICK: (5, 0, 5)},
            "E007": {LeaveType.ANNUAL: (10, 2, 8), LeaveType.SICK: (5, 0, 5)},
            "E008": {LeaveType.ANNUAL: (10, 0, 10), LeaveType.MATERNITY: (158, 92, 66), LeaveType.SICK: (5, 0, 5)},
            "E009": {LeaveType.ANNUAL: (10, 0, 10), LeaveType.SICK: (5, 1, 4)},
            "E010": {LeaveType.ANNUAL: (8, 0, 8), LeaveType.SICK: (5, 0, 5)},
        }

        for emp_id, balances in balance_data.items():
            for leave_type, (total, used, remaining) in balances.items():
                data.append({
                    "工号": emp_id,
                    "假别": leave_type.value,
                    "总额": total,
                    "已用": used,
                    "剩余": remaining
                })

        df = pd.DataFrame(data)
        df.to_excel(output_path, index=False)
        return output_path

    def generate_all(self, output_dir: str = "./data") -> Dict[str, str]:
        Path(output_dir).mkdir(parents=True, exist_ok=True)
        paths = {}
        paths["employees"] = self.generate_employees(f"{output_dir}/employees.xlsx")
        paths["punches"] = self.generate_punches(f"{output_dir}/punches.xlsx")
        paths["leaves"] = self.generate_leaves(f"{output_dir}/leaves.xlsx")
        paths["trips"] = self.generate_business_trips(f"{output_dir}/business_trips.xlsx")
        paths["overtime"] = self.generate_overtime(f"{output_dir}/overtime.xlsx")
        paths["adjustments"] = self.generate_time_adjustments(f"{output_dir}/time_adjustments.xlsx")
        paths["balances"] = self.generate_leave_balances(f"{output_dir}/leave_balances.xlsx")
        return paths


def generate_sample_data_command(output_dir: str = "./data"):
    """生成示例数据"""
    generator = SampleDataGenerator(year=2026, month=5)
    paths = generator.generate_all(output_dir)
    print(f"✓ 示例数据已生成至 {output_dir} 目录:")
    for name, path in paths.items():
        print(f"  - {name}: {path}")
    return paths
