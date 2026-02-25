import json

import pytest
from pipeline.code_translation.translate import TranslationRepository


def test_append_items_raises_for_non_list(tmp_path):
    target = tmp_path / "data.json"
    target.write_text(json.dumps({"a": 1}), encoding="utf-8")

    with pytest.raises(ValueError, match="JSON must be a list"):
        TranslationRepository(target).append_items([{"a": 2}])


def test_append_items_raises_for_non_dict(tmp_path):
    target = tmp_path / "data.json"
    target.write_text(json.dumps([]), encoding="utf-8")

    with pytest.raises(TypeError, match="new_items must contain dicts"):
        TranslationRepository(target).append_items(["not a dict"])  # type: ignore[list-item]
