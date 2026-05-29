"""Test conftest — adds app/ to sys.path for peer-level imports."""
import sys
from pathlib import Path

# Add app/ to sys.path so tests can import agent, mcp_tools, etc. as peer-level modules.
_app_dir = str(Path(__file__).parent.parent / "app")
if _app_dir not in sys.path:
    sys.path.insert(0, _app_dir)
