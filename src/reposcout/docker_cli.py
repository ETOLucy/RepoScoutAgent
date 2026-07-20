from __future__ import annotations

import argparse
import os
import subprocess
from collections.abc import Sequence
from urllib.parse import urlparse


def _proxy_url(value: str) -> str:
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise argparse.ArgumentTypeError(
            "proxy must be an absolute http(s) URL, for example http://127.0.0.1:7897"
        )
    return value


def create_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run RepoScout Docker Compose commands with an optional pull/build proxy."
    )
    parser.add_argument(
        "action",
        nargs="?",
        choices=("up", "down", "status", "logs"),
        default="up",
        help="Compose action to run (default: %(default)s)",
    )
    parser.add_argument(
        "--proxy",
        type=_proxy_url,
        help=(
            "temporary HTTP/HTTPS proxy for Docker Hub pulls and image builds; "
            "use only when direct access fails"
        ),
    )
    parser.add_argument(
        "--build",
        action="store_true",
        help="build the RepoScout image before starting (only valid with action 'up')",
    )
    parser.add_argument(
        "--foreground",
        action="store_true",
        help="keep Compose attached (only valid with action 'up')",
    )
    parser.add_argument(
        "--follow",
        action="store_true",
        help="follow log output (only valid with action 'logs')",
    )
    return parser


def _compose_command(namespace: argparse.Namespace, parser: argparse.ArgumentParser) -> list[str]:
    if namespace.build and namespace.action != "up":
        parser.error("--build is only valid with action 'up'")
    if namespace.foreground and namespace.action != "up":
        parser.error("--foreground is only valid with action 'up'")
    if namespace.follow and namespace.action != "logs":
        parser.error("--follow is only valid with action 'logs'")

    command = ["docker", "compose"]
    if namespace.action == "up":
        command.append("up")
        if namespace.build:
            command.append("--build")
        if not namespace.foreground:
            command.append("-d")
    elif namespace.action == "down":
        command.append("down")
    elif namespace.action == "status":
        command.append("ps")
    else:
        command.append("logs")
        if namespace.follow:
            command.append("--follow")
    return command


def _docker_environment(proxy: str | None) -> dict[str, str]:
    environment = os.environ.copy()
    if proxy is None:
        return environment

    environment["HTTP_PROXY"] = proxy
    environment["HTTPS_PROXY"] = proxy
    existing_no_proxy = environment.get("NO_PROXY", "")
    entries = [item for item in existing_no_proxy.split(",") if item]
    for host in ("localhost", "127.0.0.1"):
        if host not in entries:
            entries.append(host)
    environment["NO_PROXY"] = ",".join(entries)
    return environment


def main(args: Sequence[str] | None = None) -> int:
    parser = create_parser()
    namespace = parser.parse_args(args)
    command = _compose_command(namespace, parser)
    try:
        completed = subprocess.run(
            command,
            env=_docker_environment(namespace.proxy),
            check=False,
        )
    except FileNotFoundError:
        parser.error("Docker CLI was not found; install or start Docker Desktop first")
    return completed.returncode
