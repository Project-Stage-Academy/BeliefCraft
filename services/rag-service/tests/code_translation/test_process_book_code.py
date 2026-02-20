import json

from code_translation.process_book_code import BookCodeProcessor


def test_extract_entities_from_julia_code_top_level_only():
    code = """
struct Foo
end

function outer()
    function inner()
    end
end

bar(x) = x
"""
    processor = BookCodeProcessor()
    structs, funcs = processor.extract_entities_from_julia_code(code)

    assert structs == ["Foo"]
    assert "outer" in funcs
    assert "bar" in funcs
    assert "inner" not in funcs


def test_get_translated_algorithms_reads_json(tmp_path):
    data = [
        {"algorithm_number": "Algorithm 1.1.", "code": "print(1)"},
    ]
    json_path = tmp_path / "translated.json"
    json_path.write_text(json.dumps(data), encoding="utf-8")

    processor = BookCodeProcessor(json_path)
    result = processor.get_translated_algorithms(["Algorithm 1.1.", "Algorithm 2.1."])

    assert result[0]["translated"] == "print(1)"
    assert result[1]["translated"] == ""


def test_filter_out_older_chapters():
    processor = BookCodeProcessor()
    blocks = ["Algorithm 2.1.", "Algorithm 3.1.", "Algorithm A.1."]

    filtered = processor.filter_out_older_chapters(blocks, "3")

    assert filtered == ["Algorithm 2.1."]

