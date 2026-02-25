from pathlib import Path

# --- Data Paths ---
BASE_DATA_DIR = Path("./data_source")

# Input files
MAIN_PDF = BASE_DATA_DIR / "dm.pdf"
FIGURES_PDF = BASE_DATA_DIR / "dm-figures.pdf"
PADDLE_RESULTS_DIR = BASE_DATA_DIR / "paddle_results"

# Intermediate JSON metadata
OUTPUT_FIGURES_JSON = BASE_DATA_DIR / "figures_metadata.json"
OUTPUT_BLOCKS_JSON = BASE_DATA_DIR / "blocks_metadata.json"
TABLES_JSON = BASE_DATA_DIR / "extracted_tables.json"
FORMULAS_JSON = BASE_DATA_DIR / "formula_mapping.json"

# Final output
FINAL_BOOK_JSON = "ULTIMATE_BOOK_DATA.json"


# --- Parsing & Semantic Settings ---
PAGE_OFFSET = 18  # PDF page numbering offset
DPI_RENDER = 200  # Page rendering quality for CV
SCALE_FACTOR = 72 / DPI_RENDER

# Keywords for object detection
CAPTION_KEYWORDS = ["figure", "fig.", "table", "algorithm"]
BLOCK_KEYWORDS = ["example", "exercise"]
