# PDF Ingestion Pipeline

## Overview

The `pdf-ingestion-pipeline` is a core data ingestion module within the `rag-service`. It is responsible for transforming raw technical PDF documents into structured, semantically-rich JSON chunks suitable for RAG (Retrieval-Augmented Generation) workflows.

### Implementation Details
* **Primary Engine**: `PyMuPDF` (fitz) for geometric analysis and text extraction.
* **Visual Detection**: `OpenCV` for template-based figure matching.
* **Formatting**: `BeautifulSoup4` for HTML table sanitization and `Regex` for hierarchical header detection.
* **Output**: Generates `ULTIMATE_BOOK_DATA.json` containing logic-based chunks.

---

## Core Ingestion Components

### 1. `BlockProcessor` & `ImageProcessor`

These components handle the spatial identification of specialized document elements:

* **Pattern-Based Extraction**: Uses regular expressions to identify `Algorithm`, `Example`, and `Exercise` blocks based on naming conventions (e.g., `Algorithm 1.1`).
* **Computer Vision Matching**: `ImageProcessor` utilizes `cv2.matchTemplate` to find high-resolution figure templates from `dm-figures.pdf` within the main document.
* **Spatial Filtering**: Distinguishes main content from side-notes by applying horizontal thresholds (`COLUMNS_DIVIDER_X`).

### 2. `MathTableEngine`

A specialized processor for complex structured data:

* **Formula Alignment**: Maps formula labels (e.g., `(1.2)`) to LaTeX blocks by calculating vertical overlap and Euclidean distance.
* **Table-Caption Association**: Links tables to descriptions in side-columns using nearest-neighbor centroid matching.
* **HTML Sanitization**: Strips styling while preserving `colspan` and `rowspan` attributes for downstream LLM readability.

### 3. `MetadataExtractor`

Maintains the stateful document hierarchy during processing:

* **Hierarchy Tracking**: Monitors current `Section`, `Subsection`, and `Subsubsection`.
* **Chunking Triggers**: Signals the `DocumentAssembler` to create a new chunk when a header change is detected (`force_new_chunk`).
* **Reference Extraction**: Automatically extracts cross-references (`referenced_figures`, `referenced_formulas`) from text blocks to build a retrieval graph.

---

## Data Flow & Integration

1. **Extraction**: `BlockProcessor` scans the PDF for visual boundaries and headers.
2. **Refinement**: `MathTableEngine` and `ImageProcessor` enrich the raw blocks with LaTeX and figure links.
3. **Assembly**: `DocumentAssembler` merges OCR data from `paddle_results` with the enriched metadata.
4. **Deduplication**: Validates bounding boxes to ensure caption text is not duplicated within the text stream.
5. **Output**: Produces deterministic `chunk_ids` (SHA-256) for stable indexing.

## Environment Configuration

To correctly generate image links in the output JSON, ensure the following variable is set in your `.env` file:

* **FIGURES_BUCKET_URL**: The base URL for the cloud storage bucket where figures are hosted (e.g., GCS or S3). You
can find it in .env.example of rag-service.

---

## Running the Parser

FIGURES_BUCKET_URL environment variable is required and must not be empty. It defines the base URL for generating figure image links.

To execute the full processing cycle (assembling the final JSON), run:

1. Put `dm.pdf` and `dm-figures.pdf` in the `data_source/` directory.
2. Run this to generate `figures_metadata.json` from `dm.pdf` and `dm-figures.pdf`:
```bash
PYTHONPATH=services/rag-service/src uv run python -m pipeline.parsing.image_processor
```
3. Now your working directory has `figures_metadata.json`. Move it to `data_source/` directory.
4. Run this to generate `blocks_metadata.json` from `dm.pdf`:
```bash
PYTHONPATH=services/rag-service/src uv run python -m pipeline.parsing.block_processor
```
5. Now your working directory has `blocks_metadata.json`. Move it to `data_source/` directory.
6. Also put `extracted_tables.json` and `formula_mapping.json` from google drive into `data_source/` directory.
7. Create folder `paddle_results` inside `data_source/` and put paddleocr results from google drive into it(files from
`1-100.json` to `601-700.json`).
8. Run this to generate `ULTIMATE_BOOK_DATA.json`:
```bash
PYTHONPATH=services/rag-service/src uv run python -m pipeline.parsing.main
```

### Replacing Julia with Python translations

Put `translated_algorithms.json` and `translated_examples.json` from google drive into `data_source/` directory and run
```bash
uv run services/rag-service/src/pipeline/code_processing/julia_code_translation/update_chunks_with_translated_code.py\
--chunks ULTIMATE_BOOK_DATA.json   --translated-algorithms data_source/translated_algorithms.json\
--translated-examples data_source/translated_examples.json   --output ULTIMATE_BOOK_DATA_translated.json
```
