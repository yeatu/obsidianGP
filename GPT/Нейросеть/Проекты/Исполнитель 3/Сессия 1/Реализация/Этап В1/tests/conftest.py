from pathlib import Path
import os
import sys

ROOT = Path(__file__).resolve().parents[1]
B1_SRC = Path(os.environ.get("SFRA_B1_SRC", "")).resolve()
if B1_SRC.is_dir():
    sys.path.insert(0, str(B1_SRC))
sys.path.insert(0, str(ROOT / "src"))
