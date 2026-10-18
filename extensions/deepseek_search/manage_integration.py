"""Check, apply or restore exact version-reviewed DeepTutor host integration files."""
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from integration_manager import main


if __name__ == "__main__":
    main(Path(__file__).resolve().parent)
