"""T-111a: BomjAPI на PySide6 — базовые тесты (без модального show)."""

from PIG_T3.utils.BomjAPI import BomjAPI


def test_parse_payload_string():
    api = BomjAPI()
    assert api._parse_payload("hello") == "hello"


def test_parse_payload_dict_prompt():
    api = BomjAPI()
    assert api._parse_payload({"prompt": "hi"}) == "hi"


def test_parse_payload_messages():
    api = BomjAPI()
    result = api._parse_payload({"messages": [{"role": "user", "content": "x"}]})
    assert "user:" in result
    assert "x" in result


def test_validator_callable():
    v = lambda s: len(s) > 3  # noqa: E731
    api = BomjAPI(validators=v)
    assert api._get_validator("any") is v


def test_validator_dict():
    v = lambda s: True  # noqa: E731
    api = BomjAPI(validators={"BomjAPI": v})
    assert api._get_validator("BomjAPI") is v
    assert api._get_validator("other") is None


def test_save_load(tmp_path):
    import pickle

    api = BomjAPI()
    api.data = {"p": "r"}
    path = tmp_path / "data.pkl"
    api.save(str(path))
    with open(path, "rb") as f:
        assert pickle.load(f) == {"p": "r"}  # noqa: S301

    api2 = BomjAPI()
    api2.load(str(path))
    assert api2.data == {"p": "r"}
