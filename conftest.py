"""
I add the project root to sys.path here so pytest can find my src package
no matter how it's invoked or from what working directory.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))