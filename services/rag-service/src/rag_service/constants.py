from enum import StrEnum

from .models import EntityType

# mapping of mcp tool entity types to chunk types used in metadata of chunk
ENTITY_TYPE_TO_CHUNK_TYPE: dict[EntityType, str] = {
    EntityType.FORMULA: "numbered_formula",
    EntityType.TABLE: "numbered_table",
    EntityType.ALGORITHM: "algorithm",
    EntityType.IMAGE: "captioned_image",
    EntityType.EXERCISE: "exercise",
    EntityType.EXAMPLE: "example",
}

# mapping of mcp tool entity types to the corresponding reference fields in the metadata of chunk
TRAVERSE_TYPE_TO_REFERENCE_FIELD: dict[EntityType, str] = {
    EntityType.FORMULA: "referenced_formulas",
    EntityType.TABLE: "referenced_tables",
    EntityType.ALGORITHM: "referenced_algorithms",
    EntityType.IMAGE: "referenced_figures",
    EntityType.EXERCISE: "referenced_exercises",
    EntityType.EXAMPLE: "referenced_examples",
}

# mapping of reference fields to chunk types, derived from the above two mappings
REFERENCE_TYPE_MAP: dict[str, str] = {
    reference_field: ENTITY_TYPE_TO_CHUNK_TYPE[traverse_type]
    for traverse_type, reference_field in TRAVERSE_TYPE_TO_REFERENCE_FIELD.items()
}

# Name of the collection in the Weaviate where all chunks are stored.
COLLECTION_NAME = "unified_collection"

# Names of the code schema collections.
CODE_CLASS_COLLECTION = "CodeClass"
CODE_METHOD_COLLECTION = "CodeMethod"
CODE_FUNCTION_COLLECTION = "CodeFunction"


class CodeEntityRef(StrEnum):
    """Reference fields used inside code-definition collections (CodeMethod/CodeFunction)."""

    INITIALIZED_CLASSES = "initialized_classes"
    REFERENCED_METHODS = "referenced_methods"
    REFERENCED_FUNCTIONS = "referenced_functions"


class ChunkCodeRef(StrEnum):
    """Reference fields stored on unified_collection algorithm/example chunks."""

    REFERENCED_CLASSES = "referenced_classes"
    REFERENCED_METHODS = "referenced_methods"
    REFERENCED_FUNCTIONS = "referenced_functions"


CLASS_REF_FIELD = "class_ref"
ALGORITHM_REF_FIELD = "algorithm_ref"
