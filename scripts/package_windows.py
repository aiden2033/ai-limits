#!/usr/bin/env python3

import hashlib
import sys
from pathlib import Path
from zipfile import ZIP_DEFLATED, ZipFile


def digest(path):
    return hashlib.sha256(path.read_bytes()).hexdigest()


def main():
    if len(sys.argv) != 3:
        raise SystemExit("Usage: package_windows.py <executable> <output-zip>")
    executable = Path(sys.argv[1]).resolve()
    output = Path(sys.argv[2]).resolve()
    root = Path(__file__).resolve().parents[1]
    if not executable.is_file():
        raise SystemExit(f"Executable not found: {executable}")

    output.parent.mkdir(parents=True, exist_ok=True)
    output.unlink(missing_ok=True)
    with ZipFile(output, "w", ZIP_DEFLATED) as archive:
        archive.write(executable, executable.name)
        archive.write(root / "README.md", "README.md")
        archive.write(root / "config.example.json", "config.example.json")

    checksum = output.with_name(f"{output.name}.sha256")
    checksum.write_text(f"{digest(output)}  {output.name}\n", encoding="utf-8")


if __name__ == "__main__":
    main()
