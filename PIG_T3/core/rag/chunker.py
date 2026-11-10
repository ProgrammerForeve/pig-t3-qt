"""AST-aware chunking для RAG (C1).

Python-файлы: разбиваются по функциям/классам через `ast` stdlib.
Каждый чанк — цельная единица кода + метаданные (path, kind,
name, line range).

Не-Python: line-based 50 строк с overlap 10. Простая эвристика,
достаточная для `.md`, `.json`, `.yaml`, `.sql` и т.п.

Large function (>max_lines): split по 40 строк с overlap 5,
каждый sub-chunk получает тот же name с суффиксом `#L{start}`.
"""
from __future__ import annotations

import ast
from dataclasses import dataclass, field
from pathlib import Path


_DEFAULT_MAX_LINES = 80          # выше — split
_SPLIT_TARGET_LINES = 40
_SPLIT_OVERLAP = 5
_TEXT_CHUNK_LINES = 50
_TEXT_OVERLAP_LINES = 10


@dataclass
class Chunk:
    """Единица кода для индексации."""

    path: str                    # относительный путь от root
    content: str                 # сам код (без лишних отступов)
    kind: str                    # "module" | "function" | "class" | "method" | "text"
    name: str = ""               # имя функции/класса
    start_line: int = 0          # 1-based, inclusive
    end_line: int = 0            # 1-based, inclusive
    metadata: dict = field(default_factory=dict)

    @property
    def length(self) -> int:
        return self.end_line - self.start_line + 1

    def to_header(self) -> str:
        """Короткая шапка для embedding-префикса.

        Имя функции/класса + путь помогают модели понять контекст:
        'func calculate_total (billing.py:42-58)'.
        """
        if self.kind in ("function", "method", "class") and self.name:
            return f"{self.kind} {self.name} ({self.path}:{self.start_line}-{self.end_line})"
        if self.kind == "module":
            return f"module {self.path}"
        return f"{self.kind} {self.path}:{self.start_line}-{self.end_line}"


# ---------- Python ----------


def _split_ast_node(
    lines: list[str], node: ast.AST, kind: str, name: str
) -> list[Chunk]:
    """Разбить слишком длинную функцию/класс на подчанки."""
    start = node.lineno
    end = node.end_lineno or node.lineno
    if end - start + 1 <= _DEFAULT_MAX_LINES:
        body = "\n".join(lines[start - 1 : end])
        return [
            Chunk(
                path="", content=body, kind=kind, name=name,
                start_line=start, end_line=end,
            )
        ]
    chunks: list[Chunk] = []
    step = _SPLIT_TARGET_LINES - _SPLIT_OVERLAP
    for sub_start in range(start, end + 1, step):
        sub_end = min(sub_start + _SPLIT_TARGET_LINES - 1, end)
        body = "\n".join(lines[sub_start - 1 : sub_end])
        chunks.append(
            Chunk(
                path="", content=body, kind=kind,
                name=f"{name}#L{sub_start}",
                start_line=sub_start, end_line=sub_end,
            )
        )
        if sub_end >= end:
            break
    return chunks


def _chunk_python(rel_path: str, source: str) -> list[Chunk]:
    """AST-aware chunking для Python."""
    try:
        tree = ast.parse(source)
    except SyntaxError:
        # Битый файл — fallback на текстовый чанкинг
        return _chunk_text(rel_path, source, kind="text")

    lines = source.splitlines()
    chunks: list[Chunk] = []

    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            chunks.extend(_split_ast_node(lines, node, "function", node.name))
        elif isinstance(node, ast.ClassDef):
            chunks.extend(_split_ast_node(lines, node, "class", node.name))
            # Методы внутри класса — отдельные чанки, чтобы dense search
            # находил их по имени
            for child in node.body:
                if isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef)):
                    chunks.extend(
                        _split_ast_node(
                            lines, child, "method", f"{node.name}.{child.name}"
                        )
                    )

    # Модуль-уровневые statements (imports, константы) — один общий чанк
    module_lines: list[int] = []
    for node in tree.body:
        if not isinstance(
            node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)
        ):
            if getattr(node, "end_lineno", None):
                module_lines.extend(
                    range(node.lineno, node.end_lineno + 1)
                )
    if module_lines:
        module_start, module_end = min(module_lines), max(module_lines)
        body = "\n".join(lines[module_start - 1 : module_end])
        chunks.append(
            Chunk(
                path=rel_path, content=body, kind="module",
                name="", start_line=module_start, end_line=module_end,
            )
        )

    for c in chunks:
        c.path = rel_path
    return chunks


# ---------- Не-Python ----------


def _chunk_text(
    rel_path: str, source: str, kind: str = "text"
) -> list[Chunk]:
    lines = source.splitlines()
    if not lines:
        return []
    chunks: list[Chunk] = []
    step = _TEXT_CHUNK_LINES - _TEXT_OVERLAP_LINES
    for start in range(0, len(lines), step):
        end = min(start + _TEXT_CHUNK_LINES, len(lines))
        body = "\n".join(lines[start:end])
        chunks.append(
            Chunk(
                path=rel_path, content=body, kind=kind, name="",
                start_line=start + 1, end_line=end,
            )
        )
        if end >= len(lines):
            break
    return chunks


# ---------- Public API ----------


def chunk_file(
    root_folder: str, rel_path: str, max_chunk_lines: int = _DEFAULT_MAX_LINES
) -> list[Chunk]:
    """Разбить один файл. Пустой список если файл не читается."""
    global _DEFAULT_MAX_LINES
    _DEFAULT_MAX_LINES = max_chunk_lines

    full = Path(root_folder) / rel_path
    try:
        source = full.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return []

    if rel_path.endswith(".py"):
        return _chunk_python(rel_path, source)
    return _chunk_text(rel_path, source)


def chunk_files(root_folder: str, rel_paths: list[str]) -> list[Chunk]:
    """Разбить список файлов; игнорирует нечитаемые."""
    result: list[Chunk] = []
    for rel in rel_paths:
        result.extend(chunk_file(root_folder, rel))
    return result
