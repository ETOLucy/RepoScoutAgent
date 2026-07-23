#!/usr/bin/env python3
"""Plan or apply GitHub repository metadata and synchronized rename operations."""

from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import re
import shutil
import subprocess
import sys
from urllib.parse import urlparse


TOPIC_RE = re.compile(r"^[a-z0-9]+(?:-[a-z0-9]+)*$")


def run(command: list[str], cwd: Path, *, capture: bool = False) -> str:
    result = subprocess.run(
        command,
        cwd=cwd,
        check=True,
        text=True,
        stdout=subprocess.PIPE if capture else None,
        stderr=subprocess.PIPE if capture else None,
    )
    return result.stdout.strip() if capture else ""


def current_repository(repo_path: Path) -> tuple[str, str, str]:
    remote = run(["git", "remote", "get-url", "origin"], repo_path, capture=True)
    normalized = remote.removesuffix(".git")
    if normalized.startswith("git@github.com:"):
        slug = normalized.split(":", 1)[1]
        scheme = "ssh"
    else:
        parsed = urlparse(normalized)
        if parsed.hostname != "github.com":
            raise ValueError(f"origin is not a github.com repository: {remote}")
        slug = parsed.path.strip("/")
        scheme = "https"
    parts = slug.split("/")
    if len(parts) != 2 or not all(parts):
        raise ValueError(f"cannot determine OWNER/REPOSITORY from origin: {remote}")
    return parts[0], parts[1], scheme


def canonical_remote(owner: str, name: str, scheme: str) -> str:
    if scheme == "ssh":
        return f"git@github.com:{owner}/{name}.git"
    return f"https://github.com/{owner}/{name}.git"


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Preview by default; pass --apply to mutate the GitHub repository."
    )
    parser.add_argument("--repo-path", type=Path, default=Path.cwd())
    parser.add_argument("--name", help="New repository and local directory name.")
    parser.add_argument("--description", help="GitHub description (maximum 350 characters).")
    parser.add_argument("--homepage", help="GitHub homepage URL.")
    parser.add_argument("--topic", action="append", default=[], help="Topic to add; repeatable.")
    parser.add_argument("--rename-local", action="store_true")
    parser.add_argument("--apply", action="store_true")
    return parser.parse_args()


def validate(args: argparse.Namespace, repo_path: Path) -> None:
    if not (repo_path / ".git").exists():
        raise ValueError(f"not a Git checkout root: {repo_path}")
    if args.description is not None and len(args.description) > 350:
        raise ValueError("description exceeds GitHub's 350-character limit")
    if args.name and ("/" in args.name or "\\" in args.name or args.name in {".", ".."}):
        raise ValueError("--name must be a repository name, not a path")
    invalid = [topic for topic in args.topic if not TOPIC_RE.fullmatch(topic)]
    if invalid:
        raise ValueError("invalid topics: " + ", ".join(invalid))
    if args.homepage:
        parsed = urlparse(args.homepage)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            raise ValueError("--homepage must be an absolute HTTP(S) URL")


def main() -> int:
    args = parse_args()
    repo_path = args.repo_path.resolve()
    try:
        validate(args, repo_path)
        owner, old_name, scheme = current_repository(repo_path)
    except (ValueError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 2

    new_name = args.name or old_name
    old_slug = f"{owner}/{old_name}"
    new_slug = f"{owner}/{new_name}"
    edit_command = ["gh", "repo", "edit", old_slug]
    if args.description is not None:
        edit_command += ["--description", args.description]
    if args.homepage is not None:
        edit_command += ["--homepage", args.homepage]
    for topic in dict.fromkeys(args.topic):
        edit_command += ["--add-topic", topic]

    operations: list[list[str]] = []
    if len(edit_command) > 4:
        operations.append(edit_command)
    if new_name != old_name:
        operations.append(["gh", "repo", "rename", new_name, "--repo", old_slug, "--yes"])
        operations.append(
            ["git", "remote", "set-url", "origin", canonical_remote(owner, new_name, scheme)]
        )

    local_target = repo_path.parent / new_name
    plan = {
        "mode": "apply" if args.apply else "preview",
        "repository": {"before": old_slug, "after": new_slug},
        "commands": operations,
        "local_rename": (
            {"from": str(repo_path), "to": str(local_target)}
            if args.rename_local and local_target != repo_path
            else None
        ),
    }
    print(json.dumps(plan, indent=2, ensure_ascii=True))

    if not args.apply:
        return 0
    if shutil.which("gh") is None:
        print("error: GitHub CLI (gh) is required", file=sys.stderr)
        return 2
    try:
        run(["gh", "auth", "status"], repo_path)
        for command in operations:
            run(command, repo_path)
        if args.rename_local and local_target != repo_path:
            if local_target.exists():
                raise FileExistsError(f"local rename target already exists: {local_target}")
            os.chdir(repo_path.parent)
            repo_path.rename(local_target)
            print(f"renamed local checkout to {local_target}")
    except (OSError, subprocess.CalledProcessError) as error:
        print(f"error: {error}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
