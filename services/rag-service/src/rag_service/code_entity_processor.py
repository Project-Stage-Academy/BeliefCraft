from typing import Any

from .constants import CLASS_REF_FIELD, ChunkCodeReferenceField, CodeEntityReferenceField
from .models import Document

_CODE_DEF_EXPANSION_FIELDS = (
    ChunkCodeReferenceField.REFERENCED_CLASSES,
    ChunkCodeReferenceField.REFERENCED_METHODS,
    ChunkCodeReferenceField.REFERENCED_FUNCTIONS,
)

_CODE_DEF_NESTED_FIELDS = (
    CodeEntityReferenceField.INITIALIZED_CLASSES,
    CodeEntityReferenceField.REFERENCED_METHODS,
    CodeEntityReferenceField.REFERENCED_FUNCTIONS,
)


class CodeDefinitionProcessor:
    """
    Stateless processor that converts raw Weaviate code-definition objects into
    ordered :class:`~models.Document` lists and reconstructs them into a single
    Python source fragment.

    All methods are static — there is no instance state.  The class acts as a
    cohesive namespace for the two-phase pipeline:

    1. :meth:`collect_code_definitions` — graph traversal (Weaviate objects → Documents).
    2. :meth:`restore_code_fragment`    — source reconstruction (Documents → Python source).

    **Terminology** — the three Weaviate collections handled here are:

    * ``CodeClass``    — class header + ``__init__``.
    * ``CodeMethod``   — individual method body; references its parent class via ``class_ref``.
    * ``CodeFunction`` — top-level function body.
    """

    @staticmethod
    def collect_code_definitions(weaviate_objects: list[Any]) -> list[Document]:
        """
        Traverse the code-definition reference graph for a batch of root objects
        and return a flat, deduplicated, post-order list of :class:`Document`
        instances (callees before callers).

        Args:
            weaviate_objects: Raw Weaviate query results with code-definition
                              references already resolved.

        Returns:
            Deduplicated :class:`Document` list in post-order.
        """
        seen_uuids: set[str] = set()
        documents: list[Document] = []

        for obj in weaviate_objects:
            for field in _CODE_DEF_EXPANSION_FIELDS:
                if not obj.references:
                    continue
                field_ref = obj.references.get(field)
                if not field_ref:
                    continue
                for ref_obj in field_ref.objects or []:
                    CodeDefinitionProcessor._traverse(ref_obj, seen_uuids, documents)

        return documents

    @staticmethod
    def _traverse(obj: Any, seen_uuids: set[str], documents: list[Document]) -> None:
        """
        Post-order DFS for a single code-definition Weaviate object.

        Recurse into all dependencies first, then append *obj* itself.
        For ``CodeMethod`` objects the parent ``CodeClass`` document is emitted
        immediately before the method so that :meth:`restore_code_fragment`
        can group them correctly.
        """
        if obj.uuid in seen_uuids:
            return
        seen_uuids.add(obj.uuid)

        collection: str | None = getattr(obj, "collection", None)
        doc, class_name = CodeDefinitionProcessor._to_document(obj, collection)

        # Post-order: visit dependencies BEFORE appending self.
        # CodeClass is a leaf — its methods point to it, not the reverse.
        if collection != "CodeClass" and obj.references is not None:
            for field in _CODE_DEF_NESTED_FIELDS:
                nested_ref = obj.references.get(field)
                if not nested_ref:
                    continue
                for nested_obj in nested_ref.objects or []:
                    CodeDefinitionProcessor._traverse(nested_obj, seen_uuids, documents)

        if collection == "CodeMethod" and class_name:
            CodeDefinitionProcessor._emit_parent_class(obj, class_name, seen_uuids, documents)

        documents.append(doc)

    @staticmethod
    def _to_document(obj: Any, collection: str | None) -> tuple[Document, str | None]:
        """
        Convert a raw Weaviate code-definition object to a :class:`Document`.

        For ``CodeMethod`` objects ``class_name`` is extracted from ``class_ref``
        and stored in ``metadata["class_name"]`` so that
        :meth:`restore_code_fragment` can group methods with their class.

        Returns:
            ``(document, class_name)`` — *class_name* is ``None`` for non-methods.
        """
        properties: dict[str, Any] = dict(obj.properties or {})
        content: str = properties.pop("content", "")
        metadata: dict[str, Any] = {**properties, "collection": collection}

        class_name: str | None = None
        if collection == "CodeMethod" and obj.references:
            class_name = CodeDefinitionProcessor._resolve_class_name(obj)
            if class_name:
                metadata["class_name"] = class_name

        return Document(id=str(obj.uuid), content=content, metadata=metadata), class_name

    @staticmethod
    def _resolve_class_name(method_obj: Any) -> str | None:
        """Extract the parent class name from a ``CodeMethod``'s ``class_ref``."""
        class_ref = method_obj.references.get(CLASS_REF_FIELD)
        if not class_ref or not class_ref.objects:
            return None
        props = class_ref.objects[0].properties or {}
        return props.get("name") or props.get("entity_id")

    @staticmethod
    def _emit_parent_class(
        method_obj: Any,
        class_name: str,
        seen_uuids: set[str],
        documents: list[Document],
    ) -> None:
        """
        Append the ``CodeClass`` document to *documents* just before the method
        that owns it, so the class definition immediately precedes its methods
        in the post-order stream.
        """
        class_ref = method_obj.references.get(CLASS_REF_FIELD)
        if not class_ref or not class_ref.objects:
            return
        class_obj = class_ref.objects[0]
        if class_obj.uuid in seen_uuids:
            return

        seen_uuids.add(class_obj.uuid)
        cls_props: dict[str, Any] = dict(class_obj.properties or {})
        cls_content = cls_props.pop("content", "")
        documents.append(
            Document(
                id=str(class_obj.uuid),
                content=cls_content,
                metadata={**cls_props, "collection": "CodeClass"},
            )
        )

    @staticmethod
    def restore_code_fragment(documents: list[Document]) -> str:
        """
        Reconstruct a single ordered Python source fragment from a post-order
        list of code-definition :class:`Document` objects.

        Each top-level block (standalone function or full class) is positioned
        at the index of its *last* document in the deduplicated list, ensuring
        the block sorts after all external functions any of its members depend on.

        Args:
            documents: Post-order list from :meth:`collect_code_definitions`.

        Returns:
            Python source string; top-level blocks separated by two blank lines,
            classes united with their ``__init__`` and all methods.
        """
        unique_docs = CodeDefinitionProcessor._deduplicate(documents)
        class_docs, methods_by_class, class_last_idx, fn_entries = (
            CodeDefinitionProcessor._classify(unique_docs)
        )
        blocks = CodeDefinitionProcessor._render_blocks(
            fn_entries, class_docs, methods_by_class, class_last_idx
        )
        blocks.sort(key=lambda t: t[0])
        return "\n\n\n".join(code for _, code in blocks)

    @staticmethod
    def _deduplicate(documents: list[Document]) -> list[Document]:
        """Remove duplicates by UUID, first-seen wins."""
        seen: set[str] = set()
        result: list[Document] = []
        for doc in documents:
            if doc.id not in seen:
                seen.add(doc.id)
                result.append(doc)
        return result

    @staticmethod
    def _classify(
        unique_docs: list[Document],
    ) -> tuple[
        dict[str, Document],
        dict[str, list[Document]],
        dict[str, int],
        list[tuple[int, Document]],
    ]:
        """
        Classify deduplicated documents into:
        - ``class_docs``      — class_name → CodeClass document
        - ``methods_by_class``— class_name → ordered list of CodeMethod documents
        - ``class_last_idx``  — class_name → index of its last document
        - ``fn_entries``      — (index, document) for standalone CodeFunctions
        """
        class_docs: dict[str, Document] = {}
        methods_by_class: dict[str, list[Document]] = {}
        class_last_idx: dict[str, int] = {}
        fn_entries: list[tuple[int, Document]] = []

        for idx, doc in enumerate(unique_docs):
            collection = doc.metadata.get("collection", "")
            class_name = doc.metadata.get("class_name")
            name = doc.metadata.get("name", "")

            if class_name:
                methods_by_class.setdefault(class_name, []).append(doc)
                class_last_idx[class_name] = idx
            elif collection == "CodeClass" or (
                not collection and name and name in methods_by_class
            ):
                class_docs[name] = doc
                class_last_idx[name] = max(class_last_idx.get(name, idx), idx)
            else:
                fn_entries.append((idx, doc))

        # Second pass: catch CodeClass docs that arrived before any of their methods.
        for idx, doc in enumerate(unique_docs):
            if doc.metadata.get("collection") == "CodeClass":
                name = doc.metadata.get("name", "")
                if name and name not in class_docs:
                    class_docs[name] = doc
                    class_last_idx[name] = max(class_last_idx.get(name, idx), idx)

        return class_docs, methods_by_class, class_last_idx, fn_entries

    @staticmethod
    def _render_blocks(
        fn_entries: list[tuple[int, Document]],
        class_docs: dict[str, Document],
        methods_by_class: dict[str, list[Document]],
        class_last_idx: dict[str, int],
    ) -> list[tuple[int, str]]:
        """Produce ``(position, source_code)`` pairs for every top-level block."""
        blocks: list[tuple[int, str]] = [(idx, doc.content.rstrip()) for idx, doc in fn_entries]
        emitted_method_ids: set[str] = set()
        for class_name in set(class_docs) | set(methods_by_class):
            position = class_last_idx.get(class_name, 0)
            rendered = CodeDefinitionProcessor._render_class_block(
                class_name, class_docs, methods_by_class, emitted_method_ids
            )
            blocks.append((position, rendered))
        return blocks

    @staticmethod
    def _render_class_block(
        class_name: str,
        class_docs: dict[str, Document],
        methods_by_class: dict[str, list[Document]],
        emitted_method_ids: set[str],
    ) -> str:
        """
        Render one class: header + ``__init__`` from the CodeClass doc,
        followed by all methods indented one level.
        """

        def _indent(code: str, spaces: int = 4) -> str:
            pad = " " * spaces
            return "\n".join(pad + line if line.strip() else line for line in code.splitlines())

        class_code = (
            class_docs[class_name].content.rstrip()
            if class_name in class_docs
            else f"class {class_name}:"
        )

        method_parts: list[str] = []
        for mth_doc in methods_by_class.get(class_name, []):
            if mth_doc.id in emitted_method_ids:
                continue
            emitted_method_ids.add(mth_doc.id)
            method_parts.append(_indent(mth_doc.content.rstrip()))

        if not method_parts:
            return class_code
        return class_code + "\n\n" + "\n\n".join(method_parts)
