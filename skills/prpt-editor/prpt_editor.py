#!/usr/bin/env python3
"""Compact, deterministic inspector/editor for Pentaho Report Designer .prpt bundles.

The CLI never prints raw XML by default.  It identifies XML nodes with stable,
bundle-relative selectors and only rewrites the XML member selected by a change.
"""
from __future__ import annotations

import argparse
import copy
import html
import hashlib
import json
import re
import shutil
import sys
import tempfile
import zipfile
from collections import Counter
from pathlib import Path
from typing import Any, Iterable
from xml.etree import ElementTree as ET

XML_MEMBERS = ("layout.xml", "datadefinition.xml", "dataschema.xml", "content.xml", "styles.xml", "settings.xml", "meta.xml")
NAME_KEYS = ("name", "id", "key", "identifier", "role", "type")
EXPRESSION_KEYS = ("formula", "expression", "value", "query", "calculation")
MAX_TEXT = 240


class PrptError(Exception):
    pass


def local(value: str) -> str:
    return value.rsplit("}", 1)[-1]


def attr_local(node: ET.Element) -> dict[str, str]:
    return {local(k): v for k, v in node.attrib.items()}


def abbreviated(value: str | None, limit: int = MAX_TEXT) -> str:
    value = (value or "").strip().replace("\n", " ")
    return value if len(value) <= limit else value[: limit - 1] + "…"


def xml_members(bundle: zipfile.ZipFile) -> list[str]:
    return [item.filename for item in bundle.infolist() if item.filename.lower().endswith(".xml")]


def parse_member(bundle: zipfile.ZipFile, member: str) -> ET.Element:
    try:
        return ET.fromstring(bundle.read(member))
    except ET.ParseError as exc:
        raise PrptError(f"Invalid XML in {member}: {exc}") from exc


def selector(member: str, index: int) -> str:
    return f"{member}#{index}"


def iter_nodes(root: ET.Element) -> Iterable[tuple[int, ET.Element]]:
    yield from enumerate(root.iter())


def object_kind(node: ET.Element) -> str:
    tag, attrs = local(node.tag).lower(), attr_local(node)
    combined = " ".join((tag, *attrs.keys(), *attrs.values())).lower()
    if "parameter" in combined:
        return "parameter"
    if "variable" in combined or "function" in combined:
        return "variable"
    if "field" in combined or "column" in combined:
        return "field"
    if any(key in attrs for key in EXPRESSION_KEYS) or tag in {"expression", "formula"} or (tag == "value" and "$" in (node.text or "")):
        return "expression"
    if "style" in tag:
        return "style"
    if any(token in tag for token in ("band", "item", "label", "text", "element")):
        return "element"
    return "node"


def node_summary(member: str, index: int, node: ET.Element, include_expression: bool = True) -> dict[str, Any]:
    attrs = attr_local(node)
    identity = {key: attrs[key] for key in NAME_KEYS if key in attrs}
    result: dict[str, Any] = {"selector": selector(member, index), "type": object_kind(node), "tag": local(node.tag), "identity": identity}
    if include_expression:
        expression = next((attrs[key] for key in EXPRESSION_KEYS if key in attrs and attrs[key].strip()), None)
        if expression is None and local(node.tag).lower() in {"expression", "formula"}:
            expression = node.text
        if expression:
            result["expression"] = abbreviated(expression)
        elif local(node.tag).lower() == "value" and "$" in (node.text or ""):
            result["expression"] = abbreviated(node.text)
    if object_kind(node) == "variable":
        if "class" in attrs:
            result["class"] = abbreviated(attrs["class"])
        properties = {attr_local(child).get("name"): abbreviated(child.text) for child in node if local(child.tag) == "properties" for child in child if attr_local(child).get("name")}
        if properties:
            result["properties"] = properties
    text = abbreviated(node.text)
    if text and "expression" not in result:
        result["text"] = text
    return result


def inspect(path: Path) -> dict[str, Any]:
    with zipfile.ZipFile(path) as bundle:
        members = bundle.infolist()
        parsed = []
        types: Counter[str] = Counter()
        named: dict[str, list[str]] = {kind: [] for kind in ("parameter", "variable", "field")}
        for member in xml_members(bundle):
            root = parse_member(bundle, member)
            count = 0
            for index, node in iter_nodes(root):
                count += 1
                kind = object_kind(node)
                types[kind] += 1
                summary = node_summary(member, index, node, False)
                identity = summary["identity"]
                if kind in named and identity:
                    named[kind].append(next(iter(identity.values())))
            parsed.append({"member": member, "root": local(root.tag), "nodes": count})
        return {"report": path.name, "members": len(members), "xml_members": parsed, "object_counts": dict(sorted(types.items())), "named": {k: sorted(set(v))[:100] for k, v in named.items()}}


def find(path: Path, query: str | None, kind: str | None, expression: str | None, limit: int) -> dict[str, Any]:
    pattern = re.compile(query, re.I) if query else None
    expression_pattern = re.compile(expression, re.I) if expression else None
    hits: list[dict[str, Any]] = []
    with zipfile.ZipFile(path) as bundle:
        for member in xml_members(bundle):
            root = parse_member(bundle, member)
            for index, node in iter_nodes(root):
                summary = node_summary(member, index, node)
                searchable = " ".join((local(node.tag), *node.attrib.values(), node.text or ""))
                if kind and summary["type"] != kind:
                    continue
                if pattern and not pattern.search(searchable):
                    continue
                if expression_pattern and ("expression" not in summary or not expression_pattern.search(summary["expression"])):
                    continue
                hits.append(summary)
                if len(hits) >= limit:
                    return {"report": path.name, "matches": hits, "truncated": True}
    return {"report": path.name, "matches": hits, "truncated": False}


def split_selector(value: str) -> tuple[str, int]:
    match = re.fullmatch(r"([^#]+)#(\d+)", value)
    if not match:
        raise PrptError("Selector must be in the exact form member.xml#node-index, returned by find.")
    return match.group(1), int(match.group(2))


def rewrite_member(path: Path, member: str, data: bytes, backup: bool) -> Path:
    if backup:
        backup_path = path.with_suffix(path.suffix + ".bak")
        if backup_path.exists():
            raise PrptError(f"Backup already exists: {backup_path}; remove it or pass --no-backup.")
        shutil.copy2(path, backup_path)
    fd, temporary = tempfile.mkstemp(prefix=path.stem + ".", suffix=".prpt", dir=path.parent)
    try:
        with open(fd, "wb", closefd=True) as raw, zipfile.ZipFile(path) as source, zipfile.ZipFile(raw, "w") as target:
            for info in source.infolist():
                payload = data if info.filename == member else source.read(info.filename)
                copied = copy.copy(info)
                target.writestr(copied, payload, compress_type=info.compress_type)
        Path(temporary).replace(path)
    except Exception:
        Path(temporary).unlink(missing_ok=True)
        raise
    return path.with_suffix(path.suffix + ".bak") if backup else path


def modify_expression(path: Path, target: str, new_expression: str, expected: str | None, backup: bool) -> dict[str, Any]:
    member, wanted = split_selector(target)
    with zipfile.ZipFile(path) as bundle:
        if member not in bundle.namelist():
            raise PrptError(f"Member not found: {member}")
        original = bundle.read(member)
    root = ET.fromstring(original)
    nodes = list(root.iter())
    if wanted >= len(nodes):
        raise PrptError(f"Target not found: {target}")
    node = nodes[wanted]
    attrs = attr_local(node)
    candidates = [key for key in EXPRESSION_KEYS if key in attrs]
    text_expression = local(node.tag).lower() in {"expression", "formula"} or (local(node.tag).lower() == "value" and "$" in (node.text or ""))
    if len(candidates) > 1:
        raise PrptError(f"Ambiguous expression attributes at {target}: {', '.join(candidates)}")
    if not candidates and not text_expression:
        raise PrptError(f"Target {target} does not have a supported expression attribute.")
    old = attrs[candidates[0]] if candidates else (node.text or "")
    if expected is not None and old != expected:
        raise PrptError("Expected expression did not match; report was not changed.")
    # Do not serialize the ElementTree: PRD keeps design-time whitespace and
    # namespace prefixes that ElementTree would normalize.  After structural
    # validation above, replace one escaped lexical occurrence only.
    try:
        source = original.decode("utf-8")
    except UnicodeDecodeError as exc:
        raise PrptError(f"{member} is not UTF-8; refusing a byte-unsafe edit.") from exc
    old_lexical = html.escape(old, quote=bool(candidates))
    new_lexical = html.escape(new_expression, quote=bool(candidates))
    occurrences = source.count(old_lexical)
    if occurrences != 1:
        raise PrptError(f"Refusing lexical edit: expected one occurrence of the target expression, found {occurrences}.")
    rendered = source.replace(old_lexical, new_lexical, 1).encode("utf-8")
    rewrite_member(path, member, rendered, backup)
    return {"report": path.name, "modified": [{"selector": target, "expression_before": abbreviated(old), "expression_after": abbreviated(new_expression)}], "backup": str(path.with_suffix(path.suffix + ".bak")) if backup else None, "unchanged_members": "all ZIP members except " + member}


def add_parameter(path: Path, name: str, value_type: str, default: str | None, label: str | None, mandatory: bool, backup: bool) -> dict[str, Any]:
    """Add the documented PRD 9.x plain-parameter shape without reformatting XML."""
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.-]*", name):
        raise PrptError("Parameter name must be a simple identifier (letters, digits, _, ., or -).")
    member = "datadefinition.xml"
    with zipfile.ZipFile(path) as bundle:
        if member not in bundle.namelist(): raise PrptError("Missing datadefinition.xml")
        original = bundle.read(member)
    root = ET.fromstring(original)
    definitions = [node for node in root.iter() if local(node.tag) == "parameter-definition"]
    if len(definitions) != 1: raise PrptError("Expected exactly one parameter-definition; refusing to guess.")
    for node in definitions[0]:
        if attr_local(node).get("name") == name:
            raise PrptError(f"Parameter already exists: {name}")
    try: source = original.decode("utf-8")
    except UnicodeDecodeError as exc: raise PrptError("datadefinition.xml is not UTF-8; refusing a byte-unsafe edit.") from exc
    closing = "</parameter-definition>"
    if source.count(closing) != 1: raise PrptError("Cannot locate a unique parameter-definition closing tag.")
    attrs = f'name="{html.escape(name, quote=True)}" mandatory="{str(mandatory).lower()}" type="{html.escape(value_type, quote=True)}"'
    if default is not None: attrs += f' default-value="{html.escape(default, quote=True)}"'
    parameter = f"\n    <plain-parameter {attrs}>"
    if label:
        parameter += f'\n      <attribute namespace="http://reporting.pentaho.org/namespaces/engine/parameter-attributes/core" name="label">{html.escape(label)}</attribute>'
    parameter += "\n    </plain-parameter>\n  "
    rendered = source.replace(closing, parameter + closing, 1).encode("utf-8")
    rewrite_member(path, member, rendered, backup)
    return {"report": path.name, "modified": [{"parameter": name, "type": value_type, "default": default, "mandatory": mandatory}], "backup": str(path.with_suffix(path.suffix + ".bak")) if backup else None, "unchanged_members": "all ZIP members except datadefinition.xml"}


def validate(path: Path) -> dict[str, Any]:
    issues: list[str] = []
    try:
        with zipfile.ZipFile(path) as bundle:
            bad = bundle.testzip()
            if bad:
                issues.append(f"CRC failure in {bad}")
            names = bundle.namelist()
            if "mimetype" not in names:
                issues.append("Missing mimetype entry")
            elif bundle.read("mimetype") != b"application/vnd.pentaho.reporting.classic":
                issues.append("Unexpected mimetype value")
            for member in xml_members(bundle):
                parse_member(bundle, member)
    except (OSError, zipfile.BadZipFile, PrptError) as exc:
        issues.append(str(exc))
    return {"report": path.name, "valid": not issues, "issues": issues}


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    for command in ("inspect", "validate"):
        item = sub.add_parser(command); item.add_argument("report", type=Path)
    item = sub.add_parser("find"); item.add_argument("report", type=Path); item.add_argument("query", nargs="?"); item.add_argument("--type", choices=("parameter", "variable", "field", "expression", "element", "style", "node")); item.add_argument("--expression"); item.add_argument("--limit", type=int, default=50)
    item = sub.add_parser("modify-expression"); item.add_argument("report", type=Path); item.add_argument("--target", required=True); item.add_argument("--expression", required=True); item.add_argument("--expect"); item.add_argument("--no-backup", action="store_true")
    item = sub.add_parser("add-parameter"); item.add_argument("report", type=Path); item.add_argument("--name", required=True); item.add_argument("--type", default="java.lang.String"); item.add_argument("--default"); item.add_argument("--label"); item.add_argument("--mandatory", action="store_true"); item.add_argument("--no-backup", action="store_true")
    args = parser.parse_args()
    try:
        if not args.report.is_file(): raise PrptError(f"Report not found: {args.report}")
        if args.command == "inspect": result = inspect(args.report)
        elif args.command == "find": result = find(args.report, args.query, args.type, args.expression, args.limit)
        elif args.command == "validate": result = validate(args.report)
        elif args.command == "modify-expression": result = modify_expression(args.report, args.target, args.expression, args.expect, not args.no_backup)
        else: result = add_parameter(args.report, args.name, args.type, args.default, args.label, args.mandatory, not args.no_backup)
        print(json.dumps(result, indent=2, sort_keys=True))
        return 0 if result.get("valid", True) else 1
    except PrptError as exc:
        print(json.dumps({"error": str(exc)}, indent=2), file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
