#!/usr/bin/env python3
"""
sync-catalog.py — Sync PLAYBOOK.md files to Firestore playbook_catalog collection.

Walks playbooks/verified/ and playbooks/community/, parses each PLAYBOOK.md,
and upserts to the global Firestore playbook_catalog/ collection.
Playbooks removed from the repo are deleted from Firestore.

Usage:
    python scripts/sync-catalog.py \
        --playbooks-dir playbooks \
        --project-id skillmatic-ea1ab \
        --repo-url https://github.com/skillmatic-ai/playbooks

    # Dry run (no Firestore writes):
    python scripts/sync-catalog.py \
        --playbooks-dir playbooks \
        --project-id skillmatic-ea1ab \
        --repo-url https://github.com/skillmatic-ai/playbooks \
        --dry-run

    # Skip image validation (for bootstrapping before images exist):
    python scripts/sync-catalog.py \
        --playbooks-dir playbooks \
        --project-id skillmatic-ea1ab \
        --repo-url https://github.com/skillmatic-ai/playbooks \
        --skip-image-validation
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


REQUIRED_FIELDS = ["name", "description", "version", "category", "steps"]
COLLECTION_NAME = "playbook_catalog"


def parse_playbook_md(filepath: Path) -> dict:
    """Parse a PLAYBOOK.md file, extracting YAML frontmatter and full content."""
    text = filepath.read_text(encoding="utf-8")

    # Split on --- delimiters to extract frontmatter
    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"Invalid PLAYBOOK.md format: missing --- delimiters in {filepath}")

    frontmatter_str = parts[1].strip()
    frontmatter = yaml.safe_load(frontmatter_str)
    if not isinstance(frontmatter, dict):
        raise ValueError(f"Invalid YAML frontmatter in {filepath}")

    return {
        "frontmatter": frontmatter,
        "content": text,
    }


def validate_frontmatter(frontmatter: dict, filepath: Path) -> list[str]:
    """Validate required fields are present. Returns list of error messages."""
    errors = []
    for field in REQUIRED_FIELDS:
        if field not in frontmatter:
            errors.append(f"{filepath}: missing required field '{field}'")

    steps = frontmatter.get("steps", [])
    if not isinstance(steps, list):
        errors.append(f"{filepath}: 'steps' must be a list")
    else:
        for i, step in enumerate(steps):
            if not isinstance(step, dict):
                errors.append(f"{filepath}: step {i} is not a dict")
                continue
            for req in ["id", "title", "assignedRole"]:
                if req not in step:
                    errors.append(f"{filepath}: step {i} missing required field '{req}'")

    # Validate trigger inputs (if present)
    trigger = frontmatter.get("trigger", {})
    if isinstance(trigger, dict) and "inputs" in trigger:
        inputs = trigger["inputs"]
        if not isinstance(inputs, list):
            errors.append(f"{filepath}: trigger.inputs must be a list")
        else:
            for i, inp in enumerate(inputs):
                if not isinstance(inp, dict) or "name" not in inp:
                    errors.append(f"{filepath}: trigger.inputs[{i}] must have a 'name' field")

    return errors


def determine_track(filepath: Path) -> str:
    """Return 'verified' or 'community' based on the parent directory path."""
    parts = filepath.parts
    for part in parts:
        if part == "verified":
            return "verified"
        if part == "community":
            return "community"
    raise ValueError(f"Cannot determine track for {filepath}: not under verified/ or community/")


def extract_step_summary(steps: list[dict]) -> list[dict]:
    """Extract lightweight step summary for catalog display."""
    return [
        {
            "id": step.get("id", ""),
            "title": step.get("title", ""),
            "agentImage": step.get("agentImage", ""),
            "assignedRole": step.get("assignedRole", ""),
        }
        for step in steps
        if isinstance(step, dict)
    ]


def collect_agent_images(steps: list[dict]) -> set[str]:
    """Collect unique agentImage references from steps."""
    images = set()
    for step in steps:
        if isinstance(step, dict) and step.get("agentImage"):
            images.add(step["agentImage"])
    return images


def build_catalog_doc(
    playbook_id: str,
    frontmatter: dict,
    content: str,
    track: str,
    repo_url: str,
    relative_path: str,
) -> dict:
    """Build a PlaybookCatalogDoc-shaped dict from parsed playbook data."""
    metadata = frontmatter.get("metadata", {})
    if not isinstance(metadata, dict):
        metadata = {}

    tags = metadata.get("tags", frontmatter.get("tags", []))
    if not isinstance(tags, list):
        tags = []

    steps = frontmatter.get("steps", [])

    now = datetime.now(timezone.utc).isoformat()

    return {
        "id": playbook_id,
        "name": frontmatter.get("name", ""),
        "description": frontmatter.get("description", ""),
        "version": frontmatter.get("version", ""),
        "category": frontmatter.get("category", ""),
        "tags": tags,
        "track": track,
        "author": metadata.get("author", frontmatter.get("author", "unknown")),
        "stars": 0,
        "content": content,
        "stepSummary": extract_step_summary(steps),
        "gitUrl": f"{repo_url}/blob/main/{relative_path}",
        "lastUpdated": now,
        "syncedAt": now,
    }


def discover_playbooks(playbooks_dir: Path) -> list[tuple[str, Path]]:
    """Find all PLAYBOOK.md files under verified/ and community/.

    Returns list of (playbook_id, filepath) tuples.
    The playbook_id is the directory name containing the PLAYBOOK.md.
    """
    results = []
    for track_dir in ["verified", "community"]:
        track_path = playbooks_dir / track_dir
        if not track_path.is_dir():
            continue
        for child in sorted(track_path.iterdir()):
            if not child.is_dir():
                continue
            playbook_md = child / "PLAYBOOK.md"
            if playbook_md.is_file():
                results.append((child.name, playbook_md))
    return results


def sync_to_firestore(db, catalog_docs: dict[str, dict], dry_run: bool = False) -> dict:
    """Upsert catalog docs and delete removed ones.

    Returns dict with added, updated, deleted counts.
    """
    # Get existing doc IDs (skip if dry-run without a db connection)
    existing_ids: set[str] = set()
    if db is not None:
        collection_ref = db.collection(COLLECTION_NAME)
        for doc in collection_ref.stream():
            existing_ids.add(doc.id)

    added = 0
    updated = 0
    deleted = 0

    # Upsert
    for doc_id, doc_data in catalog_docs.items():
        if dry_run:
            action = "update" if doc_id in existing_ids else "add"
            print(f"  [dry-run] Would {action}: {doc_id}")
        else:
            db.collection(COLLECTION_NAME).document(doc_id).set(doc_data)

        if doc_id in existing_ids:
            updated += 1
        else:
            added += 1

    # Delete removed
    removed_ids = existing_ids - set(catalog_docs.keys())
    for doc_id in removed_ids:
        if dry_run:
            print(f"  [dry-run] Would delete: {doc_id}")
        else:
            db.collection(COLLECTION_NAME).document(doc_id).delete()
        deleted += 1

    return {"added": added, "updated": updated, "deleted": deleted}


def main():
    parser = argparse.ArgumentParser(
        description="Sync PLAYBOOK.md files to Firestore playbook_catalog collection"
    )
    parser.add_argument(
        "--playbooks-dir",
        required=True,
        help="Path to the playbooks/ directory containing verified/ and community/",
    )
    parser.add_argument("--project-id", required=True, help="GCP project ID for Firebase")
    parser.add_argument(
        "--repo-url",
        required=True,
        help="GitHub repo base URL (e.g., https://github.com/skillmatic-ai/playbooks)",
    )
    parser.add_argument("--dry-run", action="store_true", help="Parse and validate only, no Firestore writes")
    parser.add_argument(
        "--skip-image-validation",
        action="store_true",
        help="Skip Artifact Registry image validation (for bootstrapping)",
    )
    args = parser.parse_args()

    playbooks_dir = Path(args.playbooks_dir)
    if not playbooks_dir.is_dir():
        print(f"Error: {playbooks_dir} is not a directory", file=sys.stderr)
        sys.exit(1)

    # Discover playbooks
    playbook_files = discover_playbooks(playbooks_dir)
    print(f"Found {len(playbook_files)} playbook(s)")

    if not playbook_files:
        print("No playbooks found. Checking for stale Firestore docs to clean up...")
        if not args.dry_run:
            import firebase_admin
            from firebase_admin import firestore as fs

            firebase_admin.initialize_app(options={"projectId": args.project_id})
            db = fs.client()
            result = sync_to_firestore(db, {}, dry_run=False)
            if result["deleted"] > 0:
                print(f"Deleted {result['deleted']} stale doc(s) from Firestore")
            else:
                print("No stale docs to clean up")
        sys.exit(0)

    # Parse and validate
    all_errors: list[str] = []
    all_images: set[str] = set()
    catalog_docs: dict[str, dict] = {}

    for playbook_id, filepath in playbook_files:
        print(f"Parsing: {filepath}")
        try:
            parsed = parse_playbook_md(filepath)
        except ValueError as e:
            all_errors.append(str(e))
            continue

        frontmatter = parsed["frontmatter"]

        # Validate required fields
        errors = validate_frontmatter(frontmatter, filepath)
        if errors:
            all_errors.extend(errors)
            continue

        # Determine track
        try:
            track = determine_track(filepath)
        except ValueError as e:
            all_errors.append(str(e))
            continue

        # Collect agent images for validation
        steps = frontmatter.get("steps", [])
        images = collect_agent_images(steps)
        all_images.update(images)

        # Build catalog doc
        relative_path = str(filepath.relative_to(playbooks_dir.parent))
        doc = build_catalog_doc(
            playbook_id=playbook_id,
            frontmatter=frontmatter,
            content=parsed["content"],
            track=track,
            repo_url=args.repo_url,
            relative_path=relative_path,
        )
        catalog_docs[playbook_id] = doc

    # Report validation errors
    if all_errors:
        print(f"\nValidation errors ({len(all_errors)}):", file=sys.stderr)
        for err in all_errors:
            print(f"  - {err}", file=sys.stderr)
        sys.exit(1)

    # Image validation
    if all_images and not args.skip_image_validation:
        print(f"\nAgent images referenced: {', '.join(sorted(all_images))}")
        print("Image validation not yet implemented — use --skip-image-validation to bypass")
        sys.exit(1)
    elif all_images:
        print(f"\nSkipping image validation for: {', '.join(sorted(all_images))}")

    # Sync to Firestore
    print(f"\nPrepared {len(catalog_docs)} catalog doc(s)")

    if args.dry_run:
        print("\n[DRY RUN] No Firestore writes will be made:")
        result = sync_to_firestore(None, catalog_docs, dry_run=True)
    else:
        import firebase_admin
        from firebase_admin import firestore as fs

        firebase_admin.initialize_app(options={"projectId": args.project_id})
        db = fs.client()
        result = sync_to_firestore(db, catalog_docs, dry_run=False)

    print(f"\nSync complete: {result['added']} added, {result['updated']} updated, {result['deleted']} deleted")


if __name__ == "__main__":
    main()
