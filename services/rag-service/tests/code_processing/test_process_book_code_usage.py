from pipeline.code_processing.julia_code_translation.process_julia_code import UsageIndexBuilder


def test_usage_index_skips_defined_functions_and_tracks_struct_usage():
    builder = UsageIndexBuilder()

    blocks = [
        {
            "block_type": "Algorithm",
            "number": "Algorithm 2.1.",
            "text": "struct Foo\nend\n\nfunction bar(x)\n    Foo(x)\n    baz(x)\nend",
            "structs": {"Foo": []},
            "functions": {"bar": []},
        },
        {
            "block_type": "Algorithm",
            "number": "Algorithm 2.2.",
            "text": "baz(x) = x + 1\nfoo = Foo(2)",
            "structs": {"Foo": []},
            "functions": {"baz": []},
        },
    ]

    builder.populate_usage(blocks, blocks_type=type("BlockType", (), {"value": "Algorithm"}))

    assert blocks[0]["structs"]["Foo"] == ["Algorithm 2.2."]
    assert blocks[1]["structs"]["Foo"] == ["Algorithm 2.1."]
    assert blocks[0]["functions"]["bar"] == []
    assert blocks[1]["functions"]["baz"] == ["Algorithm 2.1."]
