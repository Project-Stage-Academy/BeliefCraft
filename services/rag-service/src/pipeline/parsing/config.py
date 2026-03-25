import re
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

# Matches headers like "Algorithm 3.1" or "Algorithm A.2" (case-insensitive)
# Examples: "Algorithm 1.1", "algorithm B.3"
ALGORITHM_PATTERN = re.compile(r"^Algorithm\s+(?:\d+|[A-G])\.\d+", re.IGNORECASE)

# Matches headers like "Example 2.4" or "Example C.1"
# Examples: "Example 10.2", "example A.5"
EXAMPLE_PATTERN = re.compile(r"^Example\s+(?:\d+|[A-G])\.\d+", re.IGNORECASE)

# Matches "Figure 3.1." inside text (not anchored to start)
# Examples: "Figure 1.2.", "See Figure A.3."
FIGURE_PATTERN = re.compile(r"Figure\s+(?:\d+|[A-G])\.\d+\.")

# Matches headers like "Exercise 4.2" or "Exercise D.1"
# Examples: "Exercise 7.3", "exercise B.2"
EXERCISE_PATTERN = re.compile(r"^Exercise\s+(?:\d+|[A-G])\.\d+", re.IGNORECASE)
