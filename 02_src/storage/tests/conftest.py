"""
Pytest configuration for storage tests.

Ensures proper module resolution for tests.
"""
import sys
from pathlib import Path

# Add 02_src to PYTHONPATH for absolute imports
src_root = Path(__file__).parent.parent.parent
if str(src_root) not in sys.path:
    sys.path.insert(0, str(src_root))
