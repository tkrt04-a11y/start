"""Validate JSON payloads against schema and schema_version compatibility."""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))

from src.schema_validation import main


if __name__ == "__main__":
    raise SystemExit(main())
