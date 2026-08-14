"""把服务目录加入 sys.path(服务为非包扁平模块;聚合层经 modules.* 包子模块)。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))
