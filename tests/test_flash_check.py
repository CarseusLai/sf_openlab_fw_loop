import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "loop"))
import flash_check  # noqa: E402


def sketch(tmp_path, name, app_text, newline="\n"):
    d = tmp_path / name / "base"
    d.mkdir(parents=True)
    (d / "base.ino").write_bytes(b"void setup() {}\nvoid loop() {}\n")
    (d / "app.cpp").write_bytes(app_text.replace("\n", newline).encode())
    return d


def test_same_contents_share_a_build_folder_and_any_change_gets_a_new_one(tmp_path):
    a = sketch(tmp_path, "a", "float g = 2.5f;\n")
    b = sketch(tmp_path, "b", "float g = 2.5f;\n")
    c = sketch(tmp_path, "c", "float g = 24.5f;\n")
    assert flash_check.build_dir(a) == flash_check.build_dir(b)
    assert flash_check.build_dir(a) != flash_check.build_dir(c)


def test_line_endings_do_not_change_the_build_folder(tmp_path):
    lf = sketch(tmp_path, "lf", "int x;\nint y;\n")
    crlf = sketch(tmp_path, "crlf", "int x;\nint y;\n", newline="\r\n")
    assert flash_check.build_dir(lf) == flash_check.build_dir(crlf)
