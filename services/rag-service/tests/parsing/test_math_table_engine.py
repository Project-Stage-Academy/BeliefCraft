import pytest
from pipeline.parsing.math_table_engine import MathTableEngine, clean_html_attributes


@pytest.fixture
def engine():
    return MathTableEngine(side_notes_threshold=600)


def test_get_poly_bbox_from_points(engine):
    # Тест витягування координат з точок полігону
    item = {"block_polygon_points": [[10, 20], [50, 20], [50, 100], [10, 100]]}
    bbox = engine._get_poly_bbox(item)
    assert bbox == [10.0, 20.0, 50.0, 100.0]


def test_get_poly_bbox_from_standard_bbox(engine):
    # Тест використання звичайного bbox, якщо точок немає
    item = {"block_bbox": [5, 5, 50, 50]}
    bbox = engine._get_poly_bbox(item)
    assert bbox == [5.0, 5.0, 50.0, 50.0]


def test_clean_html_attributes(engine):
    # Тест очищення HTML тегів від зайвих атрибутів (module-level function)
    html = '<table style="color: red;" border="1"><tr id="1"><td colspan="2">Data</td></tr></table>'
    cleaned = clean_html_attributes(html)

    # Має залишити colspan, але видалити style, border та id
    assert 'colspan="2"' in cleaned
    assert "style=" not in cleaned
    assert "id=" not in cleaned
    assert "<table" in cleaned


def test_clean_html_links(engine):
    # Тест збереження href у посиланнях (module-level function)
    html = '<a href="http://test.com" class="btn">Link</a>'
    cleaned = clean_html_attributes(html)
    assert 'href="http://test.com"' in cleaned
    assert "class=" not in cleaned


def test_process_formulas_linking(engine):
    # Емуляція сторінки з формулою та її номером
    page_items = [
        {
            "block_label": "display_formula",
            "block_content": "E = mc^2",
            "block_bbox": [100, 100, 200, 120],
        },
        {
            "block_label": "formula_number",
            "block_content": "(1.1)",
            "block_bbox": [500, 100, 550, 120],  # Знаходиться на тій же висоті (Y)
        },
    ]

    results = engine.process_formulas(page_items)

    assert len(results) == 1
    assert results[0]["entity_id"] == "1.1"
    assert "E = mc^2" in results[0]["content"]


def test_process_tables_association(engine):
    # Емуляція таблиці та підпису в боковій нотатці (Side Note)
    page_items = [
        {
            "block_label": "table",
            "block_content": "<table>...</table>",
            "block_bbox": [100, 200, 400, 400],
        },
        {
            "block_label": "text",  # Підпис часто маркується як текст
            "block_content": "Table 2.1. Results",
            "block_bbox": [650, 210, 800, 250],  # X > 600 (Threshold)
        },
    ]

    results = engine.process_tables(page_items, page_num=1)

    assert len(results) == 1
    assert results[0]["entity_id"] == "2.1"
    assert results[0]["chunk_type"] == "numbered_table"
    assert results[0]["caption"] == "Table 2.1. Results"


def test_join_latex_parts(engine):
    # Тест об'єднання багаторядкових формул
    parts = ["a + b = c", "x = y"]
    joined = engine._join_latex_parts(parts)
    assert "\\begin{gathered}" in joined
    assert "\\\\" in joined

    assert engine._join_latex_parts(["single"]) == "single"
    assert engine._join_latex_parts([]) == ""
