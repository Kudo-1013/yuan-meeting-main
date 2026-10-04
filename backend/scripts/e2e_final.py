#!/usr/bin/env python3
"""端到端验证入口，复用简单版完整链路测试。"""

import asyncio
import sys
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from scripts.e2e_simple import main


if __name__ == "__main__":
    asyncio.run(main())
