"""Day 5: BomjAPI — save/load, _parse_payload, _get_validator edges."""

from __future__ import annotations

import pickle

from PIG_T3.utils.BomjAPI import BomjAPI

# ---------- save / load ----------


def test_save_creates_file(tmp_path):
    api = BomjAPI()
    api.data = {"p": "r"}
    path = tmp_path / "data.pkl"
    api.save(str(path))
    assert path.exists()
    with open(path, "rb") as f:
        assert pickle.load(f) == {"p": "r"}  # noqa: S301


def test_load_roundtrip(tmp_path):
    api1 = BomjAPI()
    api1.data = {"a": "1", "b": "2"}
    path = tmp_path / "data.pkl"
    api1.save(str(path))

    api2 = BomjAPI()
    api2.load(str(path))
    assert api2.data == {"a": "1", "b": "2"}


def test_load_missing_file_noop(tmp_path):
    api = BomjAPI()
    api.load(str(tmp_path / "missing.pkl"))
    # Файл не существует — data остаётся пустым, ошибки нет
    assert api.data == {}


def test_save_overwrites(tmp_path):
    api = BomjAPI()
    path = tmp_path / "d.pkl"
    api.data = {"old": "1"}
    api.save(str(path))
    api.data = {"new": "2"}
    api.save(str(path))
    with open(path, "rb") as f:
        assert pickle.load(f) == {"new": "2"}  # noqa: S301


# ---------- _parse_payload (уже частично покрыто) ----------


def test_parse_payload_string():
    assert BomjAPI()._parse_payload("hello") == "hello"


def test_parse_payload_messages():
    result = BomjAPI()._parse_payload({"messages": [{"role": "user", "content": "x"}]})
    assert "user:" in result
    assert "x" in result


def test_parse_payload_prompt():
    assert BomjAPI()._parse_payload({"prompt": "p"}) == "p"


def test_parse_payload_promt():
    assert BomjAPI()._parse_payload({"promt": "p"}) == "p"


def test_parse_payload_empty():
    assert BomjAPI()._parse_payload({}) == "Empty prompt"


# ---------- _get_validator ----------


def test_validator_callable():
    v = lambda s: len(s) > 3  # noqa: E731
    api = BomjAPI(validators=v)
    assert api._get_validator("any") is v


def test_validator_dict():
    v = lambda s: True  # noqa: E731
    api = BomjAPI(validators={"model_a": v})
    assert api._get_validator("model_a") is v
    assert api._get_validator("model_b") is None


def test_validator_none():
    api = BomjAPI()
    assert api._get_validator("x") is None


# ---------- get_data ----------


def test_get_data_returns_dict():
    api = BomjAPI()
    api.data = {"k": "v"}
    assert api.get_data() == {"k": "v"}


def test_get_data_empty():
    assert BomjAPI().get_data() == {}
