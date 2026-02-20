import json

import pytest

from code_translation.translate import Translator


def test_add_dict_to_json_list_raises_for_non_list(tmp_path):
    target = tmp_path / "data.json"
    target.write_text(json.dumps({"a": 1}), encoding="utf-8")

    with pytest.raises(ValueError, match="JSON must be a list"):
        Translator.add_dict_to_json_list(target, [{"a": 2}])

