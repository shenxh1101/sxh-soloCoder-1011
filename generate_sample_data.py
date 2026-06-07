#!/usr/bin/env python3
"""生成示例数据脚本"""

import sys
from attendance.utils import generate_sample_data_command

if __name__ == "__main__":
    output_dir = sys.argv[1] if len(sys.argv) > 1 else "./data"
    generate_sample_data_command(output_dir)
