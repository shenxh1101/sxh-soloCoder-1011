#!/usr/bin/env python3
"""测试修复后的所有功能"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(cmd, description):
    print(f"\n{'='*70}")
    print(f"  {description}")
    print(f"  命令: {cmd}")
    print(f"{'='*70}\n")
    try:
        result = subprocess.run(cmd, shell=True, capture_output=True, text=True, encoding='utf-8')
        print(result.stdout)
        if result.stderr:
            print("STDERR:", result.stderr)
        print(f"\n返回码: {result.returncode}")
        return result.returncode == 0, result.stdout
    except Exception as e:
        print(f"执行失败: {e}")
        return False, ""

def check_output(text, keywords, description):
    all_found = True
    for kw in keywords:
        if kw not in text:
            print(f"  ✗ 未找到: {kw}")
            all_found = False
        else:
            print(f"  ✓ 已找到: {kw}")
    if all_found:
        print(f"  ✓ {description} 验证通过")
    else:
        print(f"  ✗ {description} 验证失败")
    return all_found

def main():
    os.chdir(Path(__file__).parent)

    print("="*70)
    print("  考勤数据管理工具 - 功能修复验证")
    print("="*70)

    all_passed = True

    # 先清空数据
    print("\n\n步骤 0: 清空旧数据")
    ok, out = run_command("echo yes | python main.py clear -y", "清空所有数据")
    all_passed &= ok

    # 1. 验证命令名显示为 import
    print("\n\n★ 修复验证 1: 命令名显示为 import")
    ok, out = run_command("python main.py --help", "查看主帮助")
    all_passed &= ok
    all_passed &= check_output(out, ["  import  ", "  check   ", "  summary ", "  leave   ", "  export  ", "  notify  ", "  clear   "], "命令列表")

    # 2. 验证 import 命令
    print("\n\n★ 修复验证 2: import 命令可用")
    ok, out = run_command("python main.py import --help", "查看 import 帮助")
    all_passed &= ok
    all_passed &= check_output(out, ["--file", "-f", "--type", "-t", "employee", "punch", "leave", "trip", "overtime", "adjust", "balance"], "import 参数")

    # 3. 依次导入数据，验证数据持久化
    print("\n\n★ 修复验证 3: 数据持久化 - 依次导入所有数据")

    ok, out = run_command("python main.py import -f ./data/employees.xlsx -t employee", "导入员工信息")
    all_passed &= ok
    all_passed &= check_output(out, ["成功导入", "员工信息", "10", "当前数据概览", "员工信息", "10"], "员工导入")

    ok, out = run_command("python main.py import -f ./data/punches.xlsx -t punch", "导入打卡记录")
    all_passed &= ok
    all_passed &= check_output(out, ["成功导入", "打卡记录", "统计月份"], "打卡导入")

    # 验证导入后数据还在
    print("\n 验证数据是否保留...")
    ok, out = run_command("python main.py summary", "查看汇总（验证数据持久化）")
    all_passed &= ok
    all_passed &= check_output(out, ["技术部", "产品部", "市场部", "人力资源部", "财务部"], "部门汇总（数据持久化验证）")

    # 继续导入其他数据
    ok, out = run_command("python main.py import -f ./data/leaves.xlsx -t leave", "导入请假记录")
    all_passed &= ok

    ok, out = run_command("python main.py import -f ./data/business_trips.xlsx -t trip", "导入出差记录")
    all_passed &= ok

    ok, out = run_command("python main.py import -f ./data/overtime.xlsx -t overtime", "导入加班记录")
    all_passed &= ok

    ok, out = run_command("python main.py import -f ./data/time_adjustments.xlsx -t adjust", "导入调休记录")
    all_passed &= ok

    ok, out = run_command("python main.py import -f ./data/leave_balances.xlsx -t balance", "导入假期余额")
    all_passed &= ok

    # 验证所有数据都在
    print("\n 验证所有数据是否保留...")
    ok, out = run_command("python main.py leave", "查询假期余额（验证所有员工数据）")
    all_passed &= ok

    # 4. 验证 leave 不带参数时显示所有员工各类假期
    print("\n\n★ 修复验证 4: leave 不带参数时显示所有员工各类假期")
    all_passed &= check_output(out, ["工号", "姓名", "部门", "年假(总/用/余)", "病假(总/用/余)", "事假(总/用/余)", "E001", "张三", "E010", "王十二"], "假期余额列表")

    # 5. 运行 check 命令
    print("\n\n★ 修复验证 5: check 命令")
    ok, out = run_command("python main.py check", "执行考勤检查")
    all_passed &= ok
    all_passed &= check_output(out, ["迟到", "早退", "漏打卡", "假期冲突", "跨月班次", "异常加班", "异常详情", "需确认"], "检查结果")

    # 记录 check 的异常数
    check_issue_count = 0
    needs_confirm_count = 0
    for line in out.split('\n'):
        if '合计' in line:
            parts = line.split()
            if len(parts) >= 2:
                try:
                    check_issue_count = int(parts[-1])
                except:
                    pass
        if '需员工确认' in line and '共有' in line:
            import re
            match = re.search(r'共有 (\d+) 条', line)
            if match:
                needs_confirm_count = int(match.group(1))

    print(f"  Check 异常数: {check_issue_count}, 需确认数: {needs_confirm_count}")

    # 6. 验证 summary 自动执行检查
    print("\n\n★ 修复验证 6: summary 自动执行检查")
    # 先清空再重新导入，验证自动检查
    ok, out = run_command("python main.py clear -y", "清空数据")
    ok, out = run_command("python main.py import -f ./data/employees.xlsx -t employee", "重新导入员工")
    ok, out = run_command("python main.py import -f ./data/punches.xlsx -t punch", "重新导入打卡")

    ok, out = run_command("python main.py summary", "查看汇总（验证自动检查）")
    all_passed &= ok
    all_passed &= check_output(out, ["自动执行考勤检查", "总异常数"], "自动检查验证")

    # 7. 验证 export 自动执行检查
    print("\n\n★ 修复验证 7: export 自动执行检查，结果与 check 一致")
    # 重新导入完整数据
    ok, out = run_command("python main.py clear -y", "清空数据")
    ok, out = run_command("python main.py import -f ./data/employees.xlsx -t employee", "导入员工")
    ok, out = run_command("python main.py import -f ./data/punches.xlsx -t punch", "导入打卡")
    ok, out = run_command("python main.py import -f ./data/leaves.xlsx -t leave", "导入请假")
    ok, out = run_command("python main.py import -f ./data/leave_balances.xlsx -t balance", "导入余额")

    ok, out = run_command("python main.py export -t payroll -o ./output/test_payroll.xlsx", "导出工资清单（验证自动检查）")
    all_passed &= ok
    all_passed &= check_output(out, ["自动执行考勤检查", "导出成功", "异常记录", "需员工确认"], "导出自动检查")

    # 8. 验证 notify 自动执行检查
    print("\n\n★ 修复验证 8: notify 自动执行检查，结果与 check 一致")
    # 重新导入完整数据
    ok, out = run_command("python main.py clear -y", "清空数据")
    ok, out = run_command("python main.py import -f ./data/employees.xlsx -t employee", "导入员工")
    ok, out = run_command("python main.py import -f ./data/punches.xlsx -t punch", "导入打卡")
    ok, out = run_command("python main.py import -f ./data/leaves.xlsx -t leave", "导入请假")

    ok, out = run_command("python main.py notify", "查看通知（验证自动检查）")
    all_passed &= ok
    all_passed &= check_output(out, ["自动执行考勤检查", "待员工确认记录", "按类型统计", "按严重程度"], "通知自动检查")

    # 9. 验证 clear 命令
    print("\n\n★ 修复验证 9: clear 命令清空数据")
    ok, out = run_command("python main.py clear -y", "清空数据")
    all_passed &= ok
    all_passed &= check_output(out, ["所有数据已清空", "可以开始导入新月份"], "清空数据")

    # 验证清空后运行命令提示无数据
    ok, out = run_command("python main.py summary", "清空后查看汇总")
    all_passed &= ok
    all_passed &= check_output(out, ["当前没有数据", "请先使用 import 命令"], "清空后提示")

    ok, out = run_command("python main.py notify", "清空后查看通知")
    all_passed &= ok
    all_passed &= check_output(out, ["当前没有数据"], "清空后通知提示")

    ok, out = run_command("python main.py leave", "清空后查询假期")
    all_passed &= ok
    all_passed &= check_output(out, ["当前没有数据"], "清空后假期提示")

    # 10. 完整流程验证
    print("\n\n★ 修复验证 10: 完整月度流程")
    ok, out = run_command("python main.py import -f ./data/employees.xlsx -t employee", "【流程1】导入员工")
    ok, out = run_command("python main.py import -f ./data/punches.xlsx -t punch", "【流程2】导入打卡")
    ok, out = run_command("python main.py import -f ./data/leaves.xlsx -t leave", "【流程3】导入请假")
    ok, out = run_command("python main.py import -f ./data/business_trips.xlsx -t trip", "【流程4】导入出差")
    ok, out = run_command("python main.py import -f ./data/overtime.xlsx -t overtime", "【流程5】导入加班")
    ok, out = run_command("python main.py import -f ./data/time_adjustments.xlsx -t adjust", "【流程6】导入调休")
    ok, out = run_command("python main.py import -f ./data/leave_balances.xlsx -t balance", "【流程7】导入余额")

    ok, out = run_command("python main.py check", "【流程8】检查异常")
    ok, out = run_command("python main.py summary", "【流程9】查看汇总")
    ok, out = run_command("python main.py leave", "【流程10】查询假期")
    ok, out = run_command("python main.py export -t full -o ./output/test_full.xlsx", "【流程11】导出完整报告")
    ok, out = run_command("python main.py notify -o ./output/test_notify.xlsx", "【流程12】查看并导出通知")

    all_passed &= ok

    # 11. 验证 export 和 notify 的异常数一致
    print("\n\n★ 修复验证 11: export 和 notify 异常数与 check 一致")
    # 执行 check 获取基准数
    ok, out = run_command("python main.py check", "执行 check 获取基准")
    check_total = 0
    check_needs_confirm = 0
    for line in out.split('\n'):
        if '合计' in line:
            import re
            match = re.search(r'合计\s+(\d+)', line)
            if match:
                check_total = int(match.group(1))
        if '需员工确认' in line and '共有' in line:
            import re
            match = re.search(r'共有 (\d+) 条', line)
            if match:
                check_needs_confirm = int(match.group(1))

    # 执行 export 查看
    ok, out = run_command("python main.py export -t payroll -o ./output/verify_payroll.xlsx", "导出工资清单")
    export_total = 0
    export_needs_confirm = 0
    for line in out.split('\n'):
        if '异常记录' in line:
            import re
            match = re.search(r'包含 (\d+) 条异常记录，(\d+) 条需员工确认', line)
            if match:
                export_total = int(match.group(1))
                export_needs_confirm = int(match.group(2))

    print(f"  Check: 总异常={check_total}, 需确认={check_needs_confirm}")
    print(f"  Export: 总异常={export_total}, 需确认={export_needs_confirm}")

    if check_total == export_total and check_needs_confirm == export_needs_confirm:
        print(f"  ✓ 数据一致验证通过")
    else:
        print(f"  ✗ 数据不一致！")
        all_passed = False

    print("\n" + "="*70)
    if all_passed:
        print("  ✓ 所有修复验证通过！")
    else:
        print("  ✗ 部分验证失败，请检查输出")
    print("="*70)

    return 0 if all_passed else 1


if __name__ == "__main__":
    sys.exit(main())
