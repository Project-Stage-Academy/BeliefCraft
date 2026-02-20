import json
from pathlib import Path

import pytest

from code_translation.translate import Translator


def test_extract_json_from_text_parses_json_block():
    payload = """```json
[{"a": 1}]
```"""

    result = Translator.extract_json_from_text(payload)

    assert result == [{"a": 1}]


def test_extract_json_from_text_raises_when_missing():
    with pytest.raises(ValueError, match="JSON block not found"):
        Translator.extract_json_from_text("no json here")


def test_add_dict_to_json_list_appends(tmp_path: Path):
    target = tmp_path / "data.json"
    target.write_text(json.dumps([]), encoding="utf-8")

    Translator.add_dict_to_json_list(target, [{"a": 1}, {"b": 2}])

    updated = json.loads(target.read_text(encoding="utf-8"))
    assert updated == [{"a": 1}, {"b": 2}]

