"""Streamlit entry point for the V8 warm UI preview branch.

Keep the V8 candidate self-contained under its existing upload directory.
This entry point forwards control without reading Sheets or altering credentials.
"""
from pathlib import Path
import runpy
import sys

APP_DIR = Path(__file__).resolve().parent / "FCN_Portfolio_Pro_V8_Warm_UI_Candidate"
APP_FILE = APP_DIR / "streamlit_app.py"
if not APP_FILE.is_file():
    raise RuntimeError("V8 preview files are missing; keep the uploaded candidate folder.")
sys.path.insert(0, str(APP_DIR))
runpy.run_path(str(APP_FILE), run_name="__main__")
