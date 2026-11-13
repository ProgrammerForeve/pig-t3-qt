def test_retry_with_llm_feeds_editor(qtbot, tmp_path, monkeypatch):
    import PIG_T3.gui_qt.workers.llm_wrappers as lw
    from PIG_T3.gui_qt.tabs.editor import EditorTab

    tab = EditorTab({})
    qtbot.addWidget(tab)
    tab.set_path(str(tmp_path))
    tab.model_combo.clear()
    tab.model_combo.addItem("fake-model")

    class FakeLLM:
        def ask(self, _prompt):
            return '[{"action":"create","path":"a.py","content":"x"}]'

    monkeypatch.setattr(lw, "make_llm_client", lambda *a, **kw: FakeLLM(), raising=False)
    applied: list[bool] = []
    tab._on_apply = lambda: applied.append(True)
    tab._on_validate = lambda: True

    record = {
        "_patch_ctx": {"needs_retry": True, "failed_edits": [], "read_requests": []},
        "llm_text": "[]",
    }
    tab._on_retry_with_context(record)
    assert applied == [True]
    assert "create" in tab.editor_text.toPlainText()


def test_retry_no_model_copies_clipboard(qtbot, tmp_path, monkeypatch):
    from PIG_T3.gui_qt.tabs.editor import EditorTab

    tab = EditorTab({})
    qtbot.addWidget(tab)
    tab.model_combo.clear()
    tab.model_combo.addItem("None")

    copied: list[str] = []
    monkeypatch.setattr(
        "PIG_T3.utils.clipboard_text.copy_text_to_clipboard",
        lambda t: copied.append(t) or True,
    )
    infos: list[bool] = []
    monkeypatch.setattr(
        "PIG_T3.gui_qt.tabs.editor._show_info",
        lambda *a, **k: infos.append(True),
    )
    record = {
        "_patch_ctx": {"needs_retry": True, "failed_edits": [], "read_requests": []},
        "llm_text": "[]",
    }
    tab._on_retry_with_context(record)
    assert copied
    assert infos


def test_retry_needs_retry_false_noop(qtbot):
    from PIG_T3.gui_qt.tabs.editor import EditorTab

    tab = EditorTab({})
    qtbot.addWidget(tab)
    called: list[bool] = []
    tab._on_apply = lambda: called.append(True)
    tab._on_retry_with_context({"_patch_ctx": {"needs_retry": False}})
    assert not called
