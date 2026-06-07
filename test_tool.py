#!/usr/bin/env python3
"""测试考勤工具功能"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(cmd, description):
    print(f"\n{'='*60}")
    print(f"测试: {description}")
    print(f"命令: {cmd}")
    print(f"{'='*60}")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8')
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        print(f"\n返回码: {result.returncode}")
        return result.returncode == 0
    except Exception as e:
        print(f"执行失败: {e}")
        return False

def main():
    os.chdir(Path(__file__).parent)

    print("="*60)
    print("考勤数据管理工具 - 功能测试")
    print("="*60)

    all_passed = True

    print("\n步骤 1: 生成示例数据")
    run_command("python generate_sample_data.py", "生成示例数据")

    print("\n步骤 2: 查看帮助信息")
    run_command("python main.py --help", "查看主帮助")

    print("\n步骤 3: 导入员工数据")
    all_passed &= run_command("python main.py import -f ./data/employees.xlsx -t employee", "导入员工信息")

    print("\n步骤 4: 导入打卡数据")
    all_passed &= run_command("python main.py import -f ./data/punches.xlsx -t punch", "导入打卡记录")

    print("\n步骤 5: 导入请假数据")
    all_passed &= run_command("python main.py import -f ./data/leaves.xlsx -t leave", "导入请假记录")

    print("\n步骤 6: 导入出差数据")
    all_passed &= run_command("python main.py import -f ./data/business_trips.xlsx -t trip", "导入出差记录")

    print("\n步骤 7: 导入加班数据")
    all_passed &= run_command("python main.py import -f ./data/overtime.xlsx -t overtime", "导入加班记录")

    print("\n步骤 8: 导入调休数据")
    all_passed &= run_command("python main.py import -f ./data/time_adjustments.xlsx -t adjust", "导入调休记录")

    print("\n步骤 9: 导入假期余额数据")
    all_passed &= run_command("python main.py import -f ./data/leave_balances.xlsx -t balance", "导入假期余额")

    print("\n步骤 10: 执行考勤检查")
    all_passed &= run_command("python main.py check", "执行全部检查")

    print("\n步骤 11: 查看部门汇总")
    all_passed &= run_command("python main.py summary", "查看部门汇总")

    print("\n步骤 12: 查看指定员工详情")
    all_passed &= run_command("python main.py summary -e E001", "查看员工E001详情")

    print("\n步骤 13: 查询假期余额")
    all_passed &= run_command("python main.py leave", "查询所有员工假期余额")

    print("\n步骤 14: 查询指定员工假期余额")
    all_passed &= run_command("python main.py leave -e E002", "查询员工E002假期余额")

    print("\n步骤 15: 查询年假余额不足的员工")
    all_passed &= run_command("python main.py leave -t annual --low-balance", "查询年假余额不足的员工")

    print("\n步骤 16: 导出工资核算清单")
    all_passed &= run_command("python main.py export -t payroll -f xlsx", "导出工资核算清单")

    print("\n步骤 17: 导出部门汇总表")
    all_passed &= run_command("python main.py export -t department -f xlsx", "导出部门汇总表")

    print("\n步骤 18: 导出异常记录表")
    all_passed &= run_command("python main.py export -t issues -f xlsx", "导出异常记录表")

    print("\n步骤 19: 导出完整考勤报告")
    all_passed &= run_command("python main.py export -t full -f xlsx", "导出完整考勤报告")

    print("\n步骤 20: 查看待确认通知")
    all_passed &= run_command("python main.py notify", "查看待确认通知")

    print("\n步骤 21: 查看指定部门待确认记录")
    all_passed &= run_command("python main.py notify -d 技术部", "查看技术部待确认记录")

    print("\n" + "="*60)
    if all_passed:
        print("✓ 所有测试通过！")
    else:
        print("✗ 部分测试失败，请检查输出")
    print("="*60)

    return 0 if all_passed else 1

if __name__ == "__main__":
    sys.exit(main())
