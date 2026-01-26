"""Global pytest configuration."""
import sys
from pathlib import Path

# Add project root to path BEFORE any imports
project_root = Path(__file__).parent
src_root = project_root / "02_src"
if str(src_root) not in sys.path:
    sys.path.insert(0, str(src_root))
