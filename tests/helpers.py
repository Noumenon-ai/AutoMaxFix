from __future__ import annotations

import subprocess
from pathlib import Path

from automaxfix.config import write_default_config
from automaxfix.ticket import create_bug_ticket, save_ticket
from automaxfix.utils import ensure_directory


def run_checked(argv: list[str], *, cwd: Path) -> None:
    subprocess.run(argv, cwd=str(cwd), check=True, capture_output=True, text=True)


def create_phase2_repo(tmp_path: Path) -> tuple[Path, Path]:
    repo_root = tmp_path / "repo"
    repo_root.mkdir()
    (repo_root / ".gitignore").write_text(
        ".automaxfix/\n__pycache__/\n", encoding="utf-8"
    )
    (repo_root / "calculator.py").write_text(
        "def add(a, b):\n    return a - b\n",
        encoding="utf-8",
    )
    tests_dir = repo_root / "tests"
    tests_dir.mkdir()
    (tests_dir / "test_calculator.py").write_text(
        "from calculator import add\n\n\n"
        "def test_add():\n"
        "    assert add(2, 2) == 4\n",
        encoding="utf-8",
    )

    run_checked(["git", "init"], cwd=repo_root)
    run_checked(["git", "config", "user.email", "tests@example.com"], cwd=repo_root)
    run_checked(["git", "config", "user.name", "AutoMaxFix Tests"], cwd=repo_root)
    run_checked(
        ["git", "add", ".gitignore", "calculator.py", "tests/test_calculator.py"],
        cwd=repo_root,
    )
    run_checked(["git", "commit", "-m", "initial"], cwd=repo_root)

    automaxfix_dir = ensure_directory(repo_root / ".automaxfix")
    ensure_directory(automaxfix_dir / "tickets")
    ensure_directory(automaxfix_dir / "reports")
    ensure_directory(automaxfix_dir / "logs")
    write_default_config(automaxfix_dir / "config.yml")

    ticket, ticket_path = create_bug_ticket(
        "sample duplicated reminder bug",
        automaxfix_dir / "tickets",
    )
    ticket.reproduction_test = "tests/test_calculator.py"
    ticket.suspected_files = ["calculator.py"]
    save_ticket(ticket, automaxfix_dir / "tickets")
    return repo_root, ticket_path


def write_repo_config(repo_root: Path, text: str) -> Path:
    path = repo_root / ".automaxfix" / "config.yml"
    path.write_text(text, encoding="utf-8")
    return path


def build_fix_patch() -> str:
    return """diff --git a/calculator.py b/calculator.py
--- a/calculator.py
+++ b/calculator.py
@@ -1,2 +1,2 @@
 def add(a, b):
-    return a - b
+    return a + b
"""


def build_new_test_patch() -> str:
    return """diff --git a/tests/test_repro.py b/tests/test_repro.py
new file mode 100644
--- /dev/null
+++ b/tests/test_repro.py
@@ -0,0 +1,2 @@
+def test_repro():
+    assert True
"""


def build_new_source_patch() -> str:
    return """diff --git a/new_module.py b/new_module.py
new file mode 100644
--- /dev/null
+++ b/new_module.py
@@ -0,0 +1,2 @@
+def added():
+    return 1
"""
