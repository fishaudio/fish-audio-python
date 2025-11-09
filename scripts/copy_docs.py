#!/usr/bin/env python3
"""
Script to copy generated documentation files to the docs repository.

Usage:
    python scripts/copy_docs.py <sdk_root> <docs_root>

Example:
    python scripts/copy_docs.py . ../docs
    python scripts/copy_docs.py sdk docs  # In CI context
"""

import argparse
import shutil
from pathlib import Path
from typing import Callable


def add_frontmatter(content: str, title: str, description: str, icon: str) -> str:
    """
    Add Mintlify frontmatter to markdown content.

    Args:
        content: Original markdown content
        title: Page title
        description: Page description
        icon: Icon name

    Returns:
        Content with frontmatter prepended
    """
    frontmatter = f"""---
title: "{title}"
description: "{description}"
icon: "{icon}"
---

"""
    return frontmatter + content


def copy_file_with_extension_change(
    source: Path, dest_dir: Path, new_extension: str = ".mdx"
) -> None:
    """
    Copy a single file to destination directory with extension change.

    Args:
        source: Source file path
        dest_dir: Destination directory
        new_extension: New file extension (default: .mdx)
    """
    if not source.exists():
        print(f"Warning: {source} does not exist")
        return

    dest = dest_dir / source.with_suffix(new_extension).name
    shutil.copy2(source, dest)
    print(f"  ✓ {source.name} -> {dest.name}")


def copy_files_from_directory(
    source_dir: Path, dest_dir: Path, pattern: str = "*.md", new_extension: str = ".mdx"
) -> None:
    """
    Copy all files matching pattern from source directory to destination with extension change.

    Args:
        source_dir: Source directory
        dest_dir: Destination directory
        pattern: File pattern to match (default: *.md)
        new_extension: New file extension (default: .mdx)
    """
    if not source_dir.exists():
        print(f"Warning: {source_dir} does not exist")
        return

    print(f"Copying files from {source_dir} to {dest_dir}")
    for file in source_dir.glob(pattern):
        dest = dest_dir / file.with_suffix(new_extension).name
        shutil.copy2(file, dest)
        print(f"  ✓ {file.name} -> {dest.name}")


def copy_file_with_transformation(
    source: Path,
    dest_dir: Path,
    transform_fn: Callable[[str], str],
    new_extension: str = ".mdx",
    dest_filename: str | None = None,
) -> None:
    """
    Copy a file with content transformation.

    Args:
        source: Source file path
        dest_dir: Destination directory
        transform_fn: Function to transform file content
        new_extension: New file extension (default: .mdx)
        dest_filename: Optional custom destination filename (without extension)
    """
    if not source.exists():
        print(f"Warning: {source} does not exist")
        return

    if dest_filename:
        dest = dest_dir / f"{dest_filename}{new_extension}"
    else:
        dest = dest_dir / source.with_suffix(new_extension).name

    content = source.read_text(encoding="utf-8")
    transformed_content = transform_fn(content)
    dest.write_text(transformed_content, encoding="utf-8")
    print(f"  ✓ {source.name} -> {dest.name} (transformed)")


def copy_docs(sdk_root: Path, docs_root: Path) -> None:
    """
    Copy generated documentation files to the docs repository.

    Args:
        sdk_root: Root directory of the fish-audio-python SDK
        docs_root: Root directory of the docs repository
    """
    # Source paths
    build_dir = sdk_root / "build" / "docs" / "content"
    fishaudio_dir = build_dir / "fishaudio"
    index_file = build_dir / "index.md"

    # Destination path (flat structure - all files go to the same directory)
    python_sdk_dir = docs_root / "api-reference" / "sdk" / "python"

    # Create destination directory
    python_sdk_dir.mkdir(parents=True, exist_ok=True)

    # Copy fishaudio module reference files
    copy_files_from_directory(fishaudio_dir, python_sdk_dir)

    # Copy index.md to python directory as overview.mdx with frontmatter
    copy_file_with_transformation(
        index_file,
        python_sdk_dir,
        lambda content: add_frontmatter(
            content,
            title="Python SDK",
            description="Fish Audio Python SDK for text-to-speech and voice cloning",
            icon="python",
        ),
        dest_filename="overview",
    )

    print("\nDocumentation copy completed successfully!")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Copy generated documentation files to the docs repository"
    )
    parser.add_argument(
        "sdk_root",
        type=Path,
        help="Root directory of the fish-audio-python SDK",
    )
    parser.add_argument(
        "docs_root",
        type=Path,
        help="Root directory of the docs repository",
    )

    args = parser.parse_args()

    # Validate paths
    if not args.sdk_root.exists():
        parser.error(f"SDK root directory does not exist: {args.sdk_root}")

    if not args.docs_root.exists():
        parser.error(f"Docs root directory does not exist: {args.docs_root}")

    copy_docs(args.sdk_root, args.docs_root)


if __name__ == "__main__":
    main()
