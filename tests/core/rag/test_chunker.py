"""C1: chunker — AST + text fallback."""

from __future__ import annotations

from PIG_T3.core.rag.chunker import Chunk, chunk_file, chunk_files

# ---------- Python AST ----------


def _make_project(tmp_path):
    (tmp_path / "pkg").mkdir()
    (tmp_path / "pkg" / "mod.py").write_text(
        '"""Module doc."""\n'
        "import os\n"
        "CONST = 42\n"
        "\n"
        "def f(a, b):\n"
        "    return a + b\n"
        "\n"
        "class C:\n"
        "    def m(self):\n"
        "        return 1\n"
        "    def n(self):\n"
        "        return 2\n"
    )
    return tmp_path


def test_python_finds_function(tmp_path):
    root = _make_project(tmp_path)
    chunks = chunk_file(str(root), "pkg/mod.py")
    funcs = [c for c in chunks if c.kind == "function"]
    assert any(c.name == "f" for c in funcs)


def test_python_finds_class(tmp_path):
    root = _make_project(tmp_path)
    chunks = chunk_file(str(root), "pkg/mod.py")
    classes = [c for c in chunks if c.kind == "class"]
    assert any(c.name == "C" for c in classes)


def test_python_finds_methods(tmp_path):
    root = _make_project(tmp_path)
    chunks = chunk_file(str(root), "pkg/mod.py")
    methods = [c for c in chunks if c.kind == "method"]
    names = {c.name for c in methods}
    assert "C.m" in names
    assert "C.n" in names


def test_python_module_chunk_holds_imports(tmp_path):
    root = _make_project(tmp_path)
    chunks = chunk_file(str(root), "pkg/mod.py")
    module_chunks = [c for c in chunks if c.kind == "module"]
    assert module_chunks
    assert any("import os" in c.content for c in module_chunks)
    assert any("CONST = 42" in c.content for c in module_chunks)


def test_python_line_ranges_1based(tmp_path):
    root = _make_project(tmp_path)
    chunks = chunk_file(str(root), "pkg/mod.py")
    func = next(c for c in chunks if c.kind == "function" and c.name == "f")
    # f() начинается со строки 5 (после docstring, import, CONST)
    assert func.start_line == 5
    assert func.end_line == 6


def test_python_syntax_error_falls_back_to_text(tmp_path):
    (tmp_path / "bad.py").write_text("def f(:\n    pass\n")
    chunks = chunk_file(str(tmp_path), "bad.py")
    assert chunks
    assert all(c.kind == "text" for c in chunks)


def test_python_large_function_split(tmp_path):
    body = "\n".join(f"    x{i} = {i}" for i in range(200))
    (tmp_path / "big.py").write_text(f"def huge():\n{body}\n")
    chunks = chunk_file(str(tmp_path), "big.py", max_chunk_lines=80)
    funcs = [c for c in chunks if c.kind == "function"]
    # split на части с суффиксом #L
    assert len(funcs) >= 3
    assert any("#L" in c.name for c in funcs)


# ---------- Text fallback ----------


def test_text_chunking_markdown(tmp_path):
    (tmp_path / "doc.md").write_text("\n".join(f"line {i}" for i in range(120)))
    chunks = chunk_file(str(tmp_path), "doc.md")
    assert chunks
    assert all(c.kind == "text" for c in chunks)
    # 120 строк / (50-10) ≈ 3 чанка
    assert len(chunks) >= 3


def test_text_overlap(tmp_path):
    (tmp_path / "doc.md").write_text("\n".join(f"line {i}" for i in range(60)))
    chunks = chunk_file(str(tmp_path), "doc.md")
    # Пересечение: последние 10 строк первого чанка == первые 10 второго
    assert len(chunks) >= 2
    first_lines = chunks[0].content.splitlines()[-10:]
    second_lines = chunks[1].content.splitlines()[:10]
    assert first_lines == second_lines


def test_empty_file_no_chunks(tmp_path):
    (tmp_path / "empty.py").write_text("")
    assert chunk_file(str(tmp_path), "empty.py") == []


def test_missing_file_no_chunks(tmp_path):
    assert chunk_file(str(tmp_path), "nope.py") == []


# ---------- chunk_files ----------


def test_chunk_files_multiple(tmp_path):
    _make_project(tmp_path)
    (tmp_path / "doc.md").write_text("# hi\n")
    chunks = chunk_files(str(tmp_path), ["pkg/mod.py", "doc.md"])
    assert any(c.kind == "function" for c in chunks)
    assert any(c.kind == "text" for c in chunks)


# ---------- Chunk helpers ----------


def test_chunk_length():
    c = Chunk(path="x.py", content="a\nb\nc", kind="function", name="f", start_line=1, end_line=3)
    assert c.length == 3


def test_chunk_to_header_function():
    c = Chunk(path="billing.py", content="...", kind="function", name="calculate_total", start_line=42, end_line=58)
    assert c.to_header() == "function calculate_total (billing.py:42-58)"


def test_chunk_to_header_module():
    c = Chunk(path="main.py", content="...", kind="module", start_line=1, end_line=10)
    assert c.to_header() == "module main.py"


def test_chunk_to_header_text():
    c = Chunk(path="doc.md", content="...", kind="text", start_line=1, end_line=50)
    assert c.to_header() == "text doc.md:1-50"
