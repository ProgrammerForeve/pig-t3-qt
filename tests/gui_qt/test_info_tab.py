"""TDD: InfoTab (T-201 + T-202)."""

import pytest

from PIG_T3.gui_qt.tabs.info import InfoTab


@pytest.fixture
def tab(qtbot):
    t = InfoTab()
    qtbot.addWidget(t)
    return t


def test_sections_listed(tab):
    assert tab.nav.count() == 5
    titles = [tab.nav.item(i).text() for i in range(tab.nav.count())]
    assert any("БАЗОВАЯ" in t for t in titles)
    assert any("JSON" in t for t in titles)


def test_initial_section_is_basic(tab):
    assert tab.nav.currentRow() == 0
    assert "БАЗОВАЯ" in tab.content.toHtml()


@pytest.mark.parametrize(
    "row,needle",
    [
        (1, "Analyzer"),
        (2, "replace_lines"),
        (3, "Cyclomatic"),
        (4, "Ollama"),
    ],
)
def test_switch_section_updates_html(tab, row, needle):
    tab.nav.setCurrentRow(row)
    assert needle in tab.content.toHtml()


def test_all_sections_have_html(tab):
    for row in range(tab.nav.count()):
        tab.nav.setCurrentRow(row)
        html = tab.content.toHtml()
        assert len(html) > 50
