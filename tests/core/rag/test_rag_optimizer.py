"""C4a: RagOptimizer — build + retrieve + dedupe + cap."""

from __future__ import annotations

from PIG_T3.core.rag.optimizer import RagOptimizer


class _FakeBackend:
    def __init__(self, dim: int = 4):
        self._dim = dim

    @property
    def model_name(self) -> str:
        return "fake"

    @property
    def dimension(self) -> int:
        return self._dim

    def embed(self, texts):
        # embedding по длине + first-char код (грубая семантика)
        return [[float(len(t)), float(ord(t[0]) if t else 0)] + [0.0] * (self._dim - 2) for t in texts]


def _make_project(tmp_path):
    (tmp_path / "billing.py").write_text("def calculate_total(cart):\n    return sum(cart)\n")
    (tmp_path / "auth.py").write_text("def login(user, password):\n    return True\n")
    (tmp_path / "README.md").write_text("# app\n")
    return tmp_path


def _opts(root, **overrides):
    base = {
        "root_folder": str(root),
        "task": "calculate total for cart",
        "limit_tokens": 10_000,
        "scan_config": {
            "extensions": ".py, .md",
            "ignore_list": "",
            "strict_mode": False,
        },
        "backend": _FakeBackend(),
        "force_reindex": False,
    }
    base.update(overrides)
    return base


def test_optimize_builds_index(tmp_path):
    root = _make_project(tmp_path)
    opt = RagOptimizer(**_opts(root))
    result = opt.optimize()
    assert result
    assert (root / ".pig" / "rag.db").exists()


def test_optimize_returns_absolute_paths(tmp_path):
    root = _make_project(tmp_path)
    opt = RagOptimizer(**_opts(root))
    result = opt.optimize()
    for p in result:
        assert p.startswith(str(root))
        assert os.path.isfile(p)


def test_optimize_force_reindex(tmp_path):
    root = _make_project(tmp_path)
    opt1 = RagOptimizer(**_opts(root))
    opt1.optimize()
    # при повторном запуске без force — не переиндексирует
    opt2 = RagOptimizer(**_opts(root, force_reindex=False))
    result = opt2.optimize()
    assert result


def test_optimize_caps_by_tokens(tmp_path):
    # большой файл — должен отсечься по limit
    (tmp_path / "big.py").write_text("x = 1\n" * 10_000)
    (tmp_path / "small.py").write_text("y = 2\n")
    opt = RagOptimizer(**_opts(tmp_path, limit_tokens=100, force_reindex=True))
    result = opt.optimize()
    # В cap попадут только файлы до лимита
    assert all(os.path.getsize(p) // 4 <= 100 for p in result)


def test_optimize_progress_callback(tmp_path):
    root = _make_project(tmp_path)
    opt = RagOptimizer(**_opts(root, force_reindex=True))
    events: list[tuple[int, str]] = []
    opt.optimize(progress_callback=lambda p, m: events.append((p, m)))
    assert events
    assert events[-1][0] == 100


def test_optimize_empty_project(tmp_path):
    opt = RagOptimizer(**_opts(tmp_path, force_reindex=True))
    result = opt.optimize()
    assert result == []


import os  # в конце, чтобы не перетирать другие импорты
