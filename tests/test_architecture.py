"""レイヤー間の依存方向を機械的に検証する。"""

from __future__ import annotations

import ast
from pathlib import Path

import pytest

PACKAGE = "daily2video"
SRC = Path(__file__).resolve().parents[1] / "src" / PACKAGE

# 各レイヤーが import してはいけないパッケージ内モジュール
FORBIDDEN_INTERNAL = {
    "domain": {"application", "infrastructure", "presentation", "core", "composition", "app"},
    "application": {"infrastructure", "presentation", "core", "composition", "app"},
    "infrastructure": {"presentation", "composition", "app"},
    "presentation": {"infrastructure", "composition", "app"},
    "core": {"domain", "application", "infrastructure", "presentation", "composition", "app"},
}

# Domain / Application に持ち込まない外部ライブラリ
FRAMEWORKS = {
    "fastapi", "pydantic", "pydantic_settings", "openai", "requests", "httpx",
    "google", "googleapiclient", "google_auth_oauthlib", "sync", "PIL", "uvicorn",
}
FORBIDDEN_EXTERNAL = {"domain": FRAMEWORKS, "application": FRAMEWORKS}


def _imported_modules(path: Path) -> set[str]:
    """ファイルが import する絶対モジュール名の集合を返す。"""
    package_parts = [PACKAGE, *path.relative_to(SRC).parent.parts]
    modules: set[str] = set()
    for node in ast.walk(ast.parse(path.read_text(encoding="utf-8"))):
        if isinstance(node, ast.Import):
            modules.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom):
            if node.level:
                base = package_parts[: len(package_parts) - node.level + 1]
                target = ".".join([*base, node.module] if node.module else base)
                modules.add(target)
                # `from . import api` のような形は名前側がモジュール
                modules.update(f"{target}.{alias.name}" for alias in node.names)
            elif node.module:
                modules.add(node.module)
    return modules


def _violations(layer: str) -> list[str]:
    found = []
    for path in sorted((SRC / layer).rglob("*.py")):
        for module in _imported_modules(path):
            parts = module.split(".")
            if parts[0] == PACKAGE:
                if len(parts) > 1 and parts[1] in FORBIDDEN_INTERNAL[layer]:
                    found.append(f"{path.relative_to(SRC)} -> {module}")
            elif parts[0] in FORBIDDEN_EXTERNAL.get(layer, set()):
                found.append(f"{path.relative_to(SRC)} -> {module}")
    return found


@pytest.mark.parametrize("layer", sorted(FORBIDDEN_INTERNAL))
def test_layer_dependencies(layer: str) -> None:
    assert _violations(layer) == []


def test_checker_detects_a_violation(tmp_path, monkeypatch) -> None:
    """検査自体が空振りしていないことを確認する。"""
    bad = tmp_path / "domain"
    bad.mkdir()
    (bad / "leak.py").write_text("from ..infrastructure.clients import esa_client\nimport requests\n")
    monkeypatch.setattr("test_architecture.SRC", tmp_path)
    found = _violations("domain")
    assert "domain/leak.py -> requests" in found
    assert "domain/leak.py -> daily2video.infrastructure.clients.esa_client" in found
