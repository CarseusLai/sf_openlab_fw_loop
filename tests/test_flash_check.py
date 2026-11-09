import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "loop"))
import flash_check  # noqa: E402


def make(path, files):
    path.mkdir(parents=True, exist_ok=True)
    for name, data in files.items():
        (path / name).write_bytes(data)
    return path


def test_only_the_sketch_objects_are_cleared(tmp_path):
    build = tmp_path / "build"
    make(build / "sketch", {"app.cpp.o": b"old"})
    make(build / "libraries", {"imu.o": b"kept"})
    flash_check.clear_sketch_objects(build)
    assert not (build / "sketch").exists()
    assert (build / "libraries" / "imu.o").read_bytes() == b"kept"
    flash_check.clear_sketch_objects(build)   # nothing to clear is fine


def line_marker(path):
    # what arduino-cli puts on top of each copied file
    return b'#line 1 "' + str(path.resolve()).replace("\\", "\\\\").encode() + b'"\n'


def test_a_compiled_copy_that_differs_from_disk_is_reported(tmp_path):
    sketch = make(tmp_path / "base", {"app.cpp": b"float g = 2.5f;\n", "app.h": b"#pragma once\n",
                                      "base.ino": b"void loop() {}\n"})
    build = tmp_path / "build"
    make(build / "sketch", {"app.cpp": line_marker(sketch / "app.cpp") + b"float g = 24.5f;\n",
                            "app.h": line_marker(sketch / "app.h") + b"#pragma once\r\n"})
    assert flash_check.compiled_copy_mismatch(sketch, build) == ["app.cpp"]   # CRLF alone is not a difference


def test_a_copy_taken_from_another_folder_is_reported(tmp_path):
    sketch = make(tmp_path / "base", {"app.cpp": b"x\n"})
    other = make(tmp_path / "old" / "base", {"app.cpp": b"x\n"})
    build = make(tmp_path / "build" / "sketch", {"app.cpp": line_marker(other / "app.cpp") + b"x\n"}).parent
    assert flash_check.compiled_copy_mismatch(sketch, build) == ["app.cpp"]


def test_a_missing_compiled_copy_is_reported(tmp_path):
    sketch = make(tmp_path / "base", {"app.cpp": b"x\n"})
    assert flash_check.compiled_copy_mismatch(sketch, tmp_path / "build") == ["app.cpp"]
