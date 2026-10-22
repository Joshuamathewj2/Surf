import os
import sys
import tempfile

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, ROOT)
os.environ.setdefault("SURF_LOG_FILE", os.path.join(tempfile.gettempdir(), "surf-test.log"))
