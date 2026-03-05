import shutil
from pathlib import Path

# Source of truth
SOURCE_DIR = Path(".agents/skills")

# Destination directories
DEST_DIRS = [Path(".claude/skills"), Path(".github/skills")]


def sync_skills():
    """Syncs skills from the source of truth to destination directories."""
    if not SOURCE_DIR.exists():
        print(f"Source directory {SOURCE_DIR} does not exist. Skipping.")
        return

    for dest in DEST_DIRS:
        print(f"Syncing to {dest}...")

        # Ensure destination exists
        dest.mkdir(parents=True, exist_ok=True)

        # Clear existing skills in destination to ensure exact match
        for item in dest.iterdir():
            if item.is_dir():
                shutil.rmtree(item)
            else:
                item.unlink()

        # Copy each skill from source to destination
        for skill_dir in SOURCE_DIR.iterdir():
            if skill_dir.is_dir():
                target_dir = dest / skill_dir.name
                shutil.copytree(skill_dir, target_dir)
                print(f"  Copied skill: {skill_dir.name}")

    print("Sync complete.")


if __name__ == "__main__":
    sync_skills()
