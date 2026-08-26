"""把仓库根加入 sys.path:测试经包路径 services.code-exec.<mod> 导入。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[3]))  # 仓库根
