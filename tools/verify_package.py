"""Check a built archive before it goes out.

Parsing a file proves it is grammatical. It does not prove the names resolve,
that the manifest is ordered the way hassfest wants, or that the archive
actually contains the edit that was just made -- and each of those has shipped
broken at least once.

Run:  python3 tools/verify_package.py path/to/ha_poolsmart.zip
"""

from __future__ import annotations

import ast
import importlib.util
import json
import re
import sys
import tempfile
import zipfile
from pathlib import Path

BASE = "ha_poolsmart/custom_components/poolsmart/"

#: Modules with no Home Assistant imports, which therefore have to import
#: cleanly on their own. This is the check that catches a name used before it is
#: defined, which a syntax check happily walks straight past.
PURE_MODULES = (
    "const",
    "core.config",
    "core.models",
    "core.chemistry",
    "core.learning",
    "core.heating",
    "core.optimizer",
    "core.filtration",
    "core.safety",
    "core.ladder",
    "core.trace",
)


def check(archive: Path) -> list[str]:
    problems: list[str] = []
    zf = zipfile.ZipFile(archive)
    names = set(zf.namelist())

    with tempfile.TemporaryDirectory() as tmp:
        zf.extractall(tmp)
        root = Path(tmp) / BASE

        # 1. Everything parses.
        for path in root.rglob("*.py"):
            try:
                ast.parse(path.read_text())
            except SyntaxError as err:
                problems.append(f"syntax: {path.name}: {err}")

        # 2. The pure modules import, names and all.
        sys.path.insert(0, str(root))
        for module in PURE_MODULES:
            spec = importlib.util.find_spec(module)
            if spec is None:
                problems.append(f"import: {module} not found")
                continue
            try:
                importlib.import_module(module)
            except Exception as err:  # noqa: BLE001 -- reporting, not handling
                problems.append(f"import: {module}: {type(err).__name__}: {err}")
        sys.path.remove(str(root))

        # 3. JSON is valid, and the manifest is ordered the way hassfest insists.
        for path in root.rglob("*.json"):
            try:
                data = json.loads(path.read_text())
            except ValueError as err:
                problems.append(f"json: {path.name}: {err}")
                continue
            if path.name == "manifest.json":
                keys = list(data)
                if keys[:2] != ["domain", "name"]:
                    problems.append("manifest: domain and name must come first")
                if keys[2:] != sorted(keys[2:]):
                    problems.append("manifest: remaining keys not alphabetical")

        # 4. Translation selector keys match hassfest's rule exactly.
        for language in ("en", "nl"):
            path = root / "translations" / f"{language}.json"
            if not path.exists():
                problems.append(f"translations: {language}.json missing")
                continue
            data = json.loads(path.read_text())
            for selector, body in data.get("selector", {}).items():
                for option in body.get("options", {}):
                    if not re.fullmatch(r"[a-z0-9_-]+", option) or option[0] in "_-" or option[-1] in "_-":
                        problems.append(
                            f"translations: {language}/{selector}: bad key {option!r}"
                        )

        # 5. Both languages carry the same panel strings.
        panel = (root / "www" / "poolsmart-panel.js").read_text()
        blocks = {
            language: re.search(rf"\b{language}:\s*\{{(.*?)\n  \}},", panel, re.S)
            for language in ("en", "nl")
        }
        if all(blocks.values()):
            keys = {
                language: set(re.findall(r"(\w+):", match.group(1)))
                for language, match in blocks.items()
            }
            if keys["en"] != keys["nl"]:
                problems.append(
                    f"panel strings out of step: {sorted(keys['en'] ^ keys['nl'])}"
                )

    # 6. The archive holds what it should.
    for required in ("hacs.json", "README.md", "CHANGELOG.md"):
        if f"ha_poolsmart/{required}" not in names:
            problems.append(f"archive: {required} missing")

    return problems


def main() -> int:
    if len(sys.argv) < 2:
        print(__doc__)
        return 2
    archive = Path(sys.argv[1])
    problems = check(archive)
    if problems:
        print(f"{len(problems)} problem(s):")
        for problem in problems:
            print("  -", problem)
        return 1
    print(f"{archive.name}: all checks passed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
