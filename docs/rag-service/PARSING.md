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

* **FIGURES_BUCKET_URL**: The base URL for the cloud storage bucket where figures are hosted (e.g., GCS or S3).
  * **Where to get**: Access the project's Google Cloud Console or ask the DevOps team for the current production bucket URL.
  * **Format**: `https://storage.googleapis.com/your-bucket-name/` (the code automatically handles trailing slashes).
  * **Default**: If not set, links will default to a local path, which may break in the cloud environment.

---

## Running the Parser

To execute the full processing cycle (assembling the final JSON), run:

```bash
# Run the main assembler module
uv run python -m services.rag_service.src.rag_service.main

```

### Running Individual Components (Debug Mode)

If you need to run only the block processor, image processing or math engine components independently:

```bash
# Process text blocks only
uv run python -m services.rag_service.src.rag_service.block_processor

# Process CV-based image matching only
uv run python -m services.rag_service.src.rag_service.image_processor

# Process formulas and tabels only
uv run python -m services.rag_service.src.rag_service.math_table_engine
