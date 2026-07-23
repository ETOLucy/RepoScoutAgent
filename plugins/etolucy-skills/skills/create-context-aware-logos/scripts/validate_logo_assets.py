#!/usr/bin/env python3
"""Validate basic safety and delivery properties of SVG and PNG logo assets."""

from __future__ import annotations

import argparse
import struct
import sys
import xml.etree.ElementTree as ET
from pathlib import Path


PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"
FORBIDDEN_SVG_TAGS = {"script", "foreignObject", "iframe"}
EXTERNAL_REFERENCE_PREFIXES = ("http://", "https://", "//")


def local_name(value: str) -> str:
    return value.rsplit("}", 1)[-1]


def validate_svg(path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        root = ET.parse(path).getroot()
    except (ET.ParseError, OSError) as exc:
        return [f"invalid SVG XML: {exc}"], warnings

    if local_name(root.tag) != "svg":
        errors.append("root element is not <svg>")
    if not root.get("viewBox"):
        errors.append("missing viewBox")
    has_title = any(local_name(child.tag) == "title" for child in root)
    if not root.get("aria-label") and not has_title:
        warnings.append("missing accessible <title> or aria-label")

    for element in root.iter():
        if local_name(element.tag) in FORBIDDEN_SVG_TAGS:
            errors.append(f"contains forbidden <{local_name(element.tag)}> element")
        for attribute, value in element.attrib.items():
            if local_name(attribute) in {"href", "src"} and value.startswith(
                EXTERNAL_REFERENCE_PREFIXES
            ):
                errors.append(f"contains external reference: {value}")

    return errors, warnings


def validate_png(path: Path) -> tuple[list[str], list[str]]:
    errors: list[str] = []
    warnings: list[str] = []
    try:
        with path.open("rb") as handle:
            header = handle.read(24)
    except OSError as exc:
        return [f"cannot read PNG: {exc}"], warnings

    if len(header) < 24 or header[:8] != PNG_SIGNATURE or header[12:16] != b"IHDR":
        return ["invalid PNG header"], warnings

    width, height = struct.unpack(">II", header[16:24])
    if width == 0 or height == 0:
        errors.append("PNG has zero width or height")
    if width < 32 or height < 32:
        warnings.append(f"very small raster export: {width}x{height}")
    if path.stat().st_size > 1_000_000 and "social" in path.stem.lower():
        warnings.append("social preview exceeds 1 MB")

    return errors, warnings


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("asset_directory", type=Path)
    args = parser.parse_args()

    root = args.asset_directory.resolve()
    if not root.is_dir():
        parser.error(f"not a directory: {root}")

    assets = sorted(path for path in root.rglob("*") if path.suffix.lower() in {".svg", ".png"})
    if not assets:
        print(f"ERROR: no SVG or PNG assets found in {root}")
        return 1

    error_count = 0
    for path in assets:
        errors, warnings = (
            validate_svg(path) if path.suffix.lower() == ".svg" else validate_png(path)
        )
        relative = path.relative_to(root)
        for message in errors:
            print(f"ERROR {relative}: {message}")
        for message in warnings:
            print(f"WARN  {relative}: {message}")
        if not errors and not warnings:
            print(f"OK    {relative}")
        error_count += len(errors)

    print(f"Checked {len(assets)} asset(s); {error_count} error(s).")
    return 1 if error_count else 0


if __name__ == "__main__":
    sys.exit(main())