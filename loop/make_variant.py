"""Copy the base firmware and apply bugs/<bug>/bug.patch to the copy.

Usage: python loop/make_variant.py b1      -> builds work/b1/base and prints it
"""
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def make_variant(bug_id, parent=None):
    """Return the sketch folder <parent>/base (default parent: work/<bug>)."""
    sketch = Path(parent or ROOT / "work" / bug_id) / "base"   # folder name must match base.ino
    if sketch.exists():
        shutil.rmtree(sketch)
    shutil.copytree(ROOT / "firmware" / "base", sketch)
    patch = ROOT / "bugs" / bug_id / "bug.patch"
    subprocess.run(["git", "apply", str(patch)], cwd=sketch, check=True)
    return sketch


if __name__ == "__main__":
    print(make_variant(sys.argv[1]))
