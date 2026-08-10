import ast
from pathlib import Path


def test_model_sdk_is_only_imported_by_provider_adapter():
    backend = Path(__file__).resolve().parents[2]
    allowed = (backend / "agent" / "runtime" / "providers" / "openai_compatible.py").resolve()
    violations = []
    for path in backend.rglob("*.py"):
        if path.resolve() == allowed:
            continue
        tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import) and any(alias.name == "openai" or alias.name.startswith("openai.") for alias in node.names):
                violations.append(str(path))
            if isinstance(node, ast.ImportFrom) and node.module and (node.module == "openai" or node.module.startswith("openai.")):
                violations.append(str(path))
    assert violations == []
