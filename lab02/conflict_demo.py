"""Відтворення та розв'язання Git-конфлікту в тимчасовому репозиторії."""

import subprocess
import tempfile
from pathlib import Path


def git(directory: Path, *arguments: str, check: bool = True) -> subprocess.CompletedProcess[str]:
    """Запустити Git у тимчасовому репозиторії та повернути результат команди."""
    return subprocess.run(
        ["git", *arguments], cwd=directory, check=check, capture_output=True, text=True
    )


def main() -> None:
    """Створити дві суперечливі гілки, виявити конфлікт і завершити злиття."""
    with tempfile.TemporaryDirectory(prefix="lab02-git-") as temporary:
        directory = Path(temporary)
        readme = directory / "README.md"
        git(directory, "init", "-b", "main")
        git(directory, "config", "user.name", "Lab 02 Demo")
        git(directory, "config", "user.email", "lab02-demo@example.invalid")
        readme.write_text("Стан: початок\n", encoding="utf-8")
        git(directory, "add", "README.md")
        git(directory, "commit", "-m", "docs: create example README")

        git(directory, "switch", "-c", "feature/left")
        readme.write_text("Стан: варіант А\n", encoding="utf-8")
        git(directory, "commit", "-am", "docs: change status to A")

        git(directory, "switch", "main")
        git(directory, "switch", "-c", "feature/right")
        readme.write_text("Стан: варіант Б\n", encoding="utf-8")
        git(directory, "commit", "-am", "docs: change status to B")

        git(directory, "switch", "main")
        git(directory, "merge", "feature/left")
        conflict = git(directory, "merge", "feature/right", check=False)
        if conflict.returncode == 0 or "<<<<<<<" not in readme.read_text(encoding="utf-8"):
            raise RuntimeError("Очікуваний конфлікт злиття не виник")
        print("Git виявив конфлікт у README.md")

        # Обидві зміни збережено, а службові маркери конфлікту видалено.
        readme.write_text("Стан: варіант А і варіант Б\n", encoding="utf-8")
        git(directory, "add", "README.md")
        git(directory, "commit", "-m", "fix: resolve README merge conflict")
        print("Конфлікт розв'язано: Стан: варіант А і варіант Б")
        print(git(directory, "log", "-1", "--format=%s").stdout.strip())


if __name__ == "__main__":
    main()
