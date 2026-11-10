"""TDD: validate_plan."""

from PIG_T3.core.plan_validator import validate_plan


def _step(**overrides):
    base = {
        "id": "step_1",
        "title": "Setup",
        "description": "create project structure and folders",
        "completed": False,
    }
    base.update(overrides)
    return base


def test_valid_plan_returns_no_issues():
    assert validate_plan([_step()]) == []


def test_empty_plan_reports_issue():
    issues = validate_plan([])
    assert len(issues) == 1
    assert "непустым" in issues[0]


def test_non_list_returns_issue():
    issues = validate_plan({"not": "a list"})  # type: ignore[arg-type]
    assert len(issues) == 1


def test_non_dict_step_reports_issue():
    issues = validate_plan(["not a dict"])  # type: ignore[list-item]
    assert any("словарем" in i for i in issues)


def test_missing_id():
    issues = validate_plan([{"title": "T", "description": "d" * 20}])
    assert any("отсутствует поле 'id'" in i for i in issues)


def test_duplicate_id():
    issues = validate_plan([_step(), _step()])
    assert any("дублирующийся id" in i for i in issues)


def test_missing_title():
    issues = validate_plan([{"id": "s1", "description": "d" * 20}])
    assert any("отсутствует поле 'title'" in i for i in issues)


def test_short_title():
    issues = validate_plan([_step(title="ab")])
    assert any("слишком короткое название" in i for i in issues)


def test_missing_description():
    issues = validate_plan([{"id": "s1", "title": "Title"}])
    assert any("отсутствует поле 'description'" in i for i in issues)


def test_short_description():
    issues = validate_plan([_step(description="short")])
    assert any("описание слишком короткое" in i for i in issues)


def test_missing_completed_defaults_false():
    step = {"id": "s1", "title": "T", "description": "d" * 20}
    validate_plan([step])
    assert step["completed"] is False
