"""Shared project paths, independent of the current working directory."""
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
DATA = ROOT / 'data'
DOCS = ROOT / 'docs'
TEMP = ROOT / 'tmp'
STATE_FILE = DATA / 'state.json'
