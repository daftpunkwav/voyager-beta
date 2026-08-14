"""把服务目录加入 sys.path:服务为非包扁平模块,测试需从服务目录导入。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
