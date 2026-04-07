"""
Tests for formula extraction from text and real RAG mock chunks.
"""

from app.services.extractors.formula_extractor import FormulaExtractor


def test_extract_from_text_supports_latex_delimiters() -> None:
    extractor = FormulaExtractor()
    text = (
        "Use $$x = y + z$$ for balance, inline $P(X\\mid Z)$ for belief, "
        "and \\begin{equation}a=b\\end{equation}."
    )

    formulas = extractor.extract_from_text(text)
    latex_values = {f.latex for f in formulas}

    assert "x = y + z" in latex_values
    assert "P(X\\mid Z)" in latex_values
    assert "a=b" in latex_values


def test_extract_from_text_deduplicates_whitespace_variants() -> None:
    extractor = FormulaExtractor()
    text = "First $$x = y + z$$ then same $$x=y+z$$ appears again."

    formulas = extractor.extract_from_text(text)

    assert len(formulas) == 1
    assert formulas[0].latex in {"x = y + z", "x=y+z"}


def test_extract_from_rag_chunks_uses_real_numbered_formula_chunk(
    mock_rag_chunks: list[dict],
) -> None:
    extractor = FormulaExtractor()
    chunks = mock_rag_chunks
    formula_chunk = next(c for c in chunks if c.get("chunk_type") == "numbered_formula")

    formulas = extractor.extract_from_rag_chunks([formula_chunk])

    assert len(formulas) == 1
    assert formulas[0].latex == formula_chunk["content"].strip()
    assert formulas[0].description in {
        "Equation",
        "Probability expression",
        "Mathematical expression",
    }


def test_extract_from_rag_chunks_reads_embedded_latex_from_real_text_chunk(
    mock_rag_chunks: list[dict],
) -> None:
    extractor = FormulaExtractor()
    chunks = mock_rag_chunks
    text_chunk = next(
        c for c in chunks if c.get("chunk_type") == "text" and "$" in c.get("content", "")
    )

    formulas = extractor.extract_from_rag_chunks([text_chunk])

    assert len(formulas) >= 1
    assert all("$$" not in formula.latex for formula in formulas)


def test_extract_from_rag_chunks_supports_nested_metadata_shape_from_real_chunk(
    mock_rag_chunks: list[dict],
) -> None:
    extractor = FormulaExtractor()
    chunks = mock_rag_chunks
    base_formula_chunk = next(c for c in chunks if c.get("chunk_type") == "numbered_formula")

    nested_shape_chunk = {
        "id": base_formula_chunk["chunk_id"],
        "content": base_formula_chunk["content"],
        "metadata": {
            "chunk_type": base_formula_chunk["chunk_type"],
            "description": base_formula_chunk.get("section_title"),
        },
    }

    formulas = extractor.extract_from_rag_chunks([nested_shape_chunk])

    assert len(formulas) == 1
    assert formulas[0].description == base_formula_chunk["section_title"]
