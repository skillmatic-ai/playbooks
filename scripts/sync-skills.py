#!/usr/bin/env python3
"""
sync-skills.py — Sync SKILL.md files to Firestore skills_catalog collection.

Walks skills/verified/ and skills/community/, parses each SKILL.md,
and upserts to the global Firestore skills_catalog/ collection.
Skills removed from the repo are deleted from Firestore.

Usage:
    python scripts/sync-skills.py \
        --skills-dir skills \
        --project-id skillmatic-ea1ab

    # Dry run (no Firestore writes):
    python scripts/sync-skills.py \
        --skills-dir skills \
        --project-id skillmatic-ea1ab \
        --dry-run
"""

import argparse
import sys
from datetime import datetime, timezone
from pathlib import Path

import yaml


REQUIRED_FIELDS = ["name", "id", "compatible_apis"]
COLLECTION_NAME = "skills_catalog"


def parse_skill_md(filepath: Path) -> dict:
    """Parse a SKILL.md file, extracting YAML frontmatter and full content."""
    text = filepath.read_text(encoding="utf-8")

    parts = text.split("---", 2)
    if len(parts) < 3:
        raise ValueError(f"Invalid SKILL.md format: missing --- delimiters in {filepath}")

    frontmatter_str = parts[1].strip()
    frontmatter = yaml.safe_load(frontmatter_str)
    if not isinstance(frontmatter, dict):
        raise ValueError(f"Invalid YAML frontmatter in {filepath}")

    return {
        "frontmatter": frontmatter,
        "content": text,
    }


def validate_skill(skill_data: dict, filepath: Path) -> list[str]:
    """Validate required fields in skill frontmatter."""
    errors = []
    fm = skill_data["frontmatter"]

    for field in REQUIRED_FIELDS:
        if field not in fm or not fm[field]:
            errors.append(f"Missing required field '{field}' in {filepath}")

    if "compatible_apis" in fm:
        if not isinstance(fm["compatible_apis"], list) or len(fm["compatible_apis"]) == 0:
            errors.append(f"'compatible_apis' must be a non-empty list in {filepath}")

    return errors


def discover_skills(skills_dir: Path) -> dict[str, dict]:
    """Walk skills directory, parse and validate all SKILL.md files."""
    skills = {}
    errors = []

    for track in ["verified", "community"]:
        track_dir = skills_dir / track
        if not track_dir.exists():
            continue

        for skill_dir in sorted(track_dir.iterdir()):
            if not skill_dir.is_dir():
                continue

            skill_file = skill_dir / "SKILL.md"
            if not skill_file.exists():
                print(f"  SKIP {skill_dir.name}/ — no SKILL.md")
                continue

            try:
                skill_data = parse_skill_md(skill_file)
            except Exception as e:
                errors.append(f"Parse error in {skill_file}: {e}")
                continue

            validation_errors = validate_skill(skill_data, skill_file)
            if validation_errors:
                errors.extend(validation_errors)
                continue

            fm = skill_data["frontmatter"]
            skill_id = fm["id"]
            skills[skill_id] = {
                "id": skill_id,
                "name": fm["name"],
                "description": fm.get("description", ""),
                "version": fm.get("version", "1.0"),
                "category": fm.get("category", ""),
                "compatible_apis": fm["compatible_apis"],
                "author": fm.get("author", "community"),
                "track": track,
                "content": skill_data["content"],
                "lastUpdated": datetime.now(timezone.utc).isoformat(),
            }
            print(f"  OK   {skill_id} ({fm['name']})")

    if errors:
        print(f"\n{'='*60}")
        print(f"ERRORS ({len(errors)}):")
        for e in errors:
            print(f"  - {e}")
        print(f"{'='*60}")
        sys.exit(1)

    return skills


def sync_to_firestore(skills: dict[str, dict], project_id: str, dry_run: bool) -> None:
    """Sync parsed skills to Firestore, deleting removed skills."""
    import firebase_admin
    from firebase_admin import credentials, firestore

    if not firebase_admin._apps:
        firebase_admin.initialize_app(credentials.ApplicationDefault(), {
            "projectId": project_id,
        })

    db = firestore.client()
    collection_ref = db.collection(COLLECTION_NAME)

    # Get existing skills in Firestore
    existing_docs = {doc.id for doc in collection_ref.stream()}
    local_ids = set(skills.keys())

    # Upsert local skills
    for skill_id, skill_data in skills.items():
        if dry_run:
            print(f"  DRY-RUN: would upsert {skill_id}")
        else:
            collection_ref.document(skill_id).set(skill_data, merge=True)
            print(f"  UPSERT  {skill_id}")

    # Delete removed skills
    removed = existing_docs - local_ids
    for doc_id in removed:
        if dry_run:
            print(f"  DRY-RUN: would delete {doc_id}")
        else:
            collection_ref.document(doc_id).delete()
            print(f"  DELETE  {doc_id}")

    print(f"\nSynced {len(skills)} skills ({len(removed)} removed)")


def main():
    parser = argparse.ArgumentParser(description="Sync SKILL.md files to Firestore")
    parser.add_argument("--skills-dir", required=True, help="Root skills directory")
    parser.add_argument("--project-id", required=True, help="GCP project ID")
    parser.add_argument("--dry-run", action="store_true", help="Print actions without writing")
    args = parser.parse_args()

    skills_dir = Path(args.skills_dir)
    if not skills_dir.exists():
        print(f"Skills directory not found: {skills_dir}")
        sys.exit(1)

    print(f"Discovering skills in {skills_dir}/...")
    skills = discover_skills(skills_dir)

    if not skills:
        print("No valid skills found")
        sys.exit(0)

    print(f"\nSyncing {len(skills)} skills to Firestore ({args.project_id})...")
    sync_to_firestore(skills, args.project_id, args.dry_run)


if __name__ == "__main__":
    main()
