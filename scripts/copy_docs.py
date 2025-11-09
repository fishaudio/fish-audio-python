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
    fish_audio_sdk_file = build_dir / "fish_audio_sdk.md"
    index_file = build_dir / "index.md"

    # Destination paths
    module_ref_dir = docs_root / "sdk-reference" / "python" / "module-reference"
    python_sdk_dir = docs_root / "sdk-reference" / "python"

    # Create destination directories
    module_ref_dir.mkdir(parents=True, exist_ok=True)
    python_sdk_dir.mkdir(parents=True, exist_ok=True)

    # Copy fishaudio module reference files
    if fishaudio_dir.exists():
        print(f"Copying files from {fishaudio_dir} to {module_ref_dir}")
        for md_file in fishaudio_dir.glob("*.md"):
            dest = module_ref_dir / md_file.name
            shutil.copy2(md_file, dest)
            print(f"  ✓ {md_file.name}")
    else:
        print(f"Warning: {fishaudio_dir} does not exist")

    # Copy fish_audio_sdk.md
    if fish_audio_sdk_file.exists():
        dest = module_ref_dir / fish_audio_sdk_file.name
        shutil.copy2(fish_audio_sdk_file, dest)
        print(f"  ✓ {fish_audio_sdk_file.name}")
    else:
        print(f"Warning: {fish_audio_sdk_file} does not exist")

    # Copy index.md to python directory with frontmatter
    if index_file.exists():
        dest = python_sdk_dir / index_file.name
        # Read original content
        content = index_file.read_text(encoding="utf-8")
        # Add Mintlify frontmatter
        content_with_frontmatter = add_frontmatter(
            content,
            title="Python SDK",
            description="Fish Audio Python SDK for text-to-speech and voice cloning",
            icon="python",
        )
        # Write to destination
        dest.write_text(content_with_frontmatter, encoding="utf-8")
        print(f"  ✓ {index_file.name} -> {python_sdk_dir} (with frontmatter)")
    else:
        print(f"Warning: {index_file} does not exist")

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