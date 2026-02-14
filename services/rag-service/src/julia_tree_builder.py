#!/usr/bin/env python3
# -*- coding: utf-8 -*-

"""
julia_xref.py

Dependencies:
  uv add tree-sitter tree-sitter-julia

Run:
  python julia_xref.py path/to/file.jl --out xref.json
  python julia_xref.py path/to/file.jl --dump-node-types
"""

import argparse
import json
from collections import defaultdict
from dataclasses import dataclass
from typing import Dict, List, Optional, Tuple

from tree_sitter import Parser, Language, Node
import tree_sitter_julia


# ----------------------------
# utils
# ----------------------------

def node_text(src: bytes, node: Node) -> str:
    return src[node.start_byte: node.end_byte].decode("utf8", errors="replace")


def walk(node: Node):
    stack = [node]
    while stack:
        n = stack.pop()
        yield n
        for ch in reversed(n.children):
            stack.append(ch)


def point_1based(node: Node) -> Dict[str, int]:
    # tree-sitter uses 0-based row/column
    return {"line": node.start_point[0] + 1, "col": node.start_point[1] + 1}


def range_1based(node: Node) -> Dict[str, Dict[str, int]]:
    return {"start": {"line": node.start_point[0] + 1, "col": node.start_point[1] + 1},
            "end":   {"line": node.end_point[0] + 1,   "col": node.end_point[1] + 1}}


def extract_dotted_name(src: bytes, node: Node) -> Optional[str]:
    if node.type in {"identifier", "operator", "field_identifier"}:
        return node_text(src, node)

    if node.type == "field_expression":
        parts: List[str] = []
        for sub in walk(node):
            if sub.type in {"identifier", "field_identifier"}:
                parts.append(node_text(src, sub))
        if parts:
            out = []
            for p in parts:
                if not out or out[-1] != p:
                    out.append(p)
            return ".".join(out)

    for sub in walk(node):
        if sub.type in {"identifier", "operator"}:
            return node_text(src, sub)

    return None


# ----------------------------
# grammar adaptation (common node names)
# ----------------------------

FUNCTION_DEF_TYPES = {"function_definition", "short_function_definition"}
STRUCT_DEF_TYPES = {"struct_definition", "mutable_struct_definition"}
TYPE_ANNOTATION_TYPES = {"type_annotation", "typed_expression"}

def is_function_def(n: Node) -> bool:
    return (n.type in FUNCTION_DEF_TYPES) or ("function" in n.type and "definition" in n.type)

def is_struct_def(n: Node) -> bool:
    return (n.type in STRUCT_DEF_TYPES) or ("struct" in n.type and "definition" in n.type)

def is_type_annotation(n: Node) -> bool:
    return (n.type in TYPE_ANNOTATION_TYPES) or ("type_annotation" in n.type)

def is_parametric_type(n: Node) -> bool:
    t = n.type
    return ("param" in t and "type" in t)


# ----------------------------
# top-level blocks index
# ----------------------------

@dataclass
class TopBlock:
    kind: str                 # "function" | "struct" | "toplevel"
    name: str                 # e.g. "infer" / "TrustRegionUpdate"
    node: Node                # original node (for range)

    def label(self) -> str:
        if self.kind == "toplevel":
            return "<toplevel>"
        return f"{self.kind} {self.name}"

    def span(self) -> Dict:
        return range_1based(self.node)


def get_def_name(src: bytes, node: Node) -> str:
    # best-effort: first identifier/operator near the beginning
    for ch in node.children[:30]:
        if ch.type in {"identifier", "operator"}:
            return node_text(src, ch)
        if ch.type == "field_expression":
            dn = extract_dotted_name(src, ch)
            if dn:
                return dn
    # fallback
    for sub in walk(node):
        if sub.type in {"identifier", "operator"}:
            return node_text(src, sub)
    return "<anonymous>"


def build_top_blocks(src: bytes, root: Node) -> List[TopBlock]:
    """
    Build a list of top-level blocks: direct children of root that are
    function defs / struct defs, plus an implicit <toplevel>.
    """
    blocks: List[TopBlock] = [TopBlock(kind="toplevel", name="", node=root)]

    for ch in root.children:
        if is_function_def(ch):
            blocks.append(TopBlock(kind="function", name=get_def_name(src, ch), node=ch))
        elif is_struct_def(ch):
            blocks.append(TopBlock(kind="struct", name=get_def_name(src, ch), node=ch))

    return blocks


def top_block_for_node(blocks: List[TopBlock], node: Node) -> TopBlock:
    """
    Find the smallest top-level block that contains `node` by byte range.
    Priority: function/struct over <toplevel>.
    """
    nb0, nb1 = node.start_byte, node.end_byte

    best = blocks[0]  # <toplevel>
    best_size = best.node.end_byte - best.node.start_byte

    for b in blocks[1:]:
        if b.node.start_byte <= nb0 and nb1 <= b.node.end_byte:
            size = b.node.end_byte - b.node.start_byte
            if size <= best_size:
                best = b
                best_size = size

    return best


# ----------------------------
# main extraction with locations
# ----------------------------

def extract_xref_with_locations(src: bytes, root: Node) -> Dict:
    top_blocks = build_top_blocks(src, root)

    # Results
    definitions = {"functions": [], "structs": []}
    uses = {"calls": [], "types": []}

    # Collect defs (with locations)
    for ch in root.children:
        if is_function_def(ch):
            name = get_def_name(src, ch)
            definitions["functions"].append({
                "name": name,
                "at": point_1based(ch),
                "span": range_1based(ch),
            })
        elif is_struct_def(ch):
            name = get_def_name(src, ch)
            definitions["structs"].append({
                "name": name,
                "at": point_1based(ch),
                "span": range_1based(ch),
            })

    # Collect uses across entire file
    for n in walk(root):
        blk = top_block_for_node(top_blocks, n)

        # function calls
        if n.type == "call_expression" and n.children:
            callee = n.children[0]
            callee_name = extract_dotted_name(src, callee)
            if callee_name:
                uses["calls"].append({
                    "name": callee_name,
                    "at": point_1based(callee),
                    "in": {
                        "top": blk.label(),
                        "span": blk.span(),
                    }
                })

        # type annotations ::T (or equivalent nodes)
        if is_type_annotation(n):
            # capture each identifier inside annotation as a "type mention"
            for sub in walk(n):
                if sub.type == "identifier":
                    tname = node_text(src, sub)
                    uses["types"].append({
                        "name": tname,
                        "at": point_1based(sub),
                        "in": {
                            "top": blk.label(),
                            "span": blk.span(),
                        }
                    })

        # parametric types Foo{T}
        if is_parametric_type(n):
            for sub in walk(n):
                if sub.type == "identifier":
                    tname = node_text(src, sub)
                    uses["types"].append({
                        "name": tname,
                        "at": point_1based(sub),
                        "in": {
                            "top": blk.label(),
                            "span": blk.span(),
                        }
                    })

    # optional: de-duplicate identical use records (same name + same location)
    def dedup(records):
        seen = set()
        out = []
        for r in records:
            key = (r["name"], r["at"]["line"], r["at"]["col"], r["in"]["top"])
            if key not in seen:
                seen.add(key)
                out.append(r)
        return out

    uses["calls"] = dedup(uses["calls"])
    uses["types"] = dedup(uses["types"])

    return {"definitions": definitions, "uses": uses}


# ----------------------------
# CLI
# ----------------------------

def dump_node_types(root: Node) -> Dict[str, int]:
    freq = defaultdict(int)
    for n in walk(root):
        freq[n.type] += 1
    return dict(sorted(freq.items(), key=lambda kv: (-kv[1], kv[0])))


def main():
    # ap = argparse.ArgumentParser(description="Julia xref (definitions + call graph + used types) via Tree-sitter.")
    # ap.add_argument("path", default="julia_tree_builder.py", help="Path to .jl file")
    # ap.add_argument("--out", default="", help="Write JSON output to this file (default: stdout)")
    # ap.add_argument("--dump-node-types", action="store_true",
    #                 help="Dump node.type frequency table (debug grammar differences).")
    # args = ap.parse_args()

    # Create parser language (fix for PyCapsule vs Language)
    julia_lang = Language(tree_sitter_julia.language())

    parser = Parser()
    parser.language = julia_lang

    with open("decision_making_code.jl", "rb") as f:
        src = f.read()

    tree = parser.parse(src)
    root = tree.root_node

    print(json.dumps(dump_node_types(root), ensure_ascii=False, indent=2))

    result = build_xref(src, root)

    print(json.dumps(result, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
