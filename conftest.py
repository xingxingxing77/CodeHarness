"""仓库根 conftest：确保仓库根在 sys.path（扁平导入布局）。"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
