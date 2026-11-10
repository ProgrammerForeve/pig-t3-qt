"""TDD: FileMetrics / Issue — status properties."""

from PIG_T3.core.quality.models import FileMetrics, Issue


def test_issue_dataclass():
    i = Issue(tool="pylint", msg="x", line=10)
    assert i.severity == "info"
    assert i.line == 10


def test_status_cc_green():
    assert FileMetrics(path="a", complexity=5).status_cc == "green"


def test_status_cc_yellow():
    assert FileMetrics(path="a", complexity=15).status_cc == "yellow"


def test_status_cc_red():
    assert FileMetrics(path="a", complexity=25).status_cc == "red"


def test_status_mi_green():
    assert FileMetrics(path="a", maintainability=25).status_mi == "green"


def test_status_mi_yellow():
    assert FileMetrics(path="a", maintainability=15).status_mi == "yellow"


def test_status_mi_red():
    assert FileMetrics(path="a", maintainability=5).status_mi == "red"


def test_status_pylint_green():
    assert FileMetrics(path="a", pylint_score=9.0).status_pylint == "green"


def test_status_pylint_yellow():
    assert FileMetrics(path="a", pylint_score=6.0).status_pylint == "yellow"


def test_status_pylint_red():
    assert FileMetrics(path="a", pylint_score=3.0).status_pylint == "red"


def test_status_security_green():
    assert FileMetrics(path="a", security_issues=0).status_security == "green"


def test_status_security_yellow():
    assert FileMetrics(path="a", security_issues=1).status_security == "yellow"


def test_status_security_red():
    assert FileMetrics(path="a", security_issues=2).status_security == "red"


def test_overall_status_red_wins():
    m = FileMetrics(
        path="a",
        complexity=5,
        maintainability=25,
        pylint_score=9.0,
        security_issues=2,
    )
    assert m.overall_status == "red"


def test_overall_status_yellow_when_no_red():
    m = FileMetrics(
        path="a",
        complexity=5,
        maintainability=15,
        pylint_score=9.0,
        security_issues=0,
    )
    assert m.overall_status == "yellow"


def test_overall_status_green_when_all_green():
    m = FileMetrics(
        path="a",
        complexity=5,
        maintainability=25,
        pylint_score=9.0,
        security_issues=0,
    )
    assert m.overall_status == "green"


def test_get_status_for_column():
    m = FileMetrics(path="a", complexity=15)
    assert m.get_status_for_column("sloc") == "green"
    assert m.get_status_for_column("cc") == "yellow"
    assert m.get_status_for_column("unknown") == m.overall_status
