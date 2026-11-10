#!/usr/bin/env python3
"""List GitHub organization packages matching a regex, then delete them after manual review.

Workflow:
  1. list   -> writes a CSV review file with every matching package (delete=yes).
  2. review -> edit the CSV: set delete=no or remove rows you want to keep.
  3. delete -> deletes every row still marked delete=yes (honors DRY_RUN).

The token needs the `read:packages` and `delete:packages` scopes (plus `repo` for
packages linked to private repositories).
"""

import argparse
import csv
import os
from pathlib import Path
import re
import sys
from typing import Iterator, Optional, Sequence
from urllib.parse import quote

from dotenv import dotenv_values
import requests

API_URL = "https://api.github.com"
PACKAGE_TYPES = ("npm", "maven", "rubygems", "docker", "nuget", "container")
CSV_FIELDS = (
    "delete",
    "package_type",
    "name",
    "visibility",
    "repository",
    "version_count",
    "created_at",
    "updated_at",
    "html_url",
)


class Config:
    def __init__(self, env_file: Path):
        if not env_file.is_file():
            sys.exit(f"Env file not found: {env_file}")
        values = dotenv_values(env_file)
        self.org = (values.get("ORG") or "").strip()
        self.token = (values.get("GH_TOKEN") or "").strip()
        if not self.org or not self.token:
            sys.exit("ORG and GH_TOKEN must be set in the env file.")
        self.dir = Path(os.path.expanduser(values.get("DIR") or "~/.cache/packages-to-clean-up"))
        self.dry_run = (values.get("DRY_RUN") or "true").strip().lower() not in ("false", "0", "no")


def build_session(token: str) -> requests.Session:
    session = requests.Session()
    session.headers.update(
        {
            "Accept": "application/vnd.github+json",
            "Authorization": f"Bearer {token}",
            "X-GitHub-Api-Version": "2022-11-28",
        }
    )
    return session


def check_auth(session: requests.Session, org: str) -> None:
    resp = session.get(f"{API_URL}/orgs/{quote(org, safe='')}", timeout=30)
    if resp.status_code != 200:
        sys.exit(f"Unable to access organization '{org}': {resp.status_code} {resp.text}")
    scopes = resp.headers.get("X-OAuth-Scopes")
    if scopes is not None:
        print(f"Authenticated. Token scopes: {scopes or '(none)'}")


def iter_packages(session: requests.Session, org: str, package_type: str) -> Iterator[dict]:
    url: Optional[str] = f"{API_URL}/orgs/{quote(org, safe='')}/packages"
    params: Optional[dict] = {"package_type": package_type, "per_page": 100}
    while url:
        resp = session.get(url, params=params, timeout=30)
        if resp.status_code != 200:
            print(f"  ! Failed listing {package_type} packages: {resp.status_code} {resp.text}", file=sys.stderr)
            return
        yield from resp.json()
        url = resp.links.get("next", {}).get("url")
        params = None  # the "next" link already carries the query string


def cmd_list(args: argparse.Namespace, cfg: Config) -> int:
    try:
        pattern = re.compile(args.pattern, 0 if args.case_sensitive else re.IGNORECASE)
    except re.error as exc:
        sys.exit(f"Invalid regex '{args.pattern}': {exc}")

    session = build_session(cfg.token)
    check_auth(session, cfg.org)

    rows = []
    for package_type in args.package_type:
        print(f"Scanning {package_type} packages in '{cfg.org}'...")
        for pkg in iter_packages(session, cfg.org, package_type):
            if not pattern.search(pkg["name"]):
                continue
            rows.append(
                {
                    "delete": "yes",
                    "package_type": pkg.get("package_type", package_type),
                    "name": pkg["name"],
                    "visibility": pkg.get("visibility", ""),
                    "repository": (pkg.get("repository") or {}).get("full_name", ""),
                    "version_count": pkg.get("version_count", ""),
                    "created_at": pkg.get("created_at", ""),
                    "updated_at": pkg.get("updated_at", ""),
                    "html_url": pkg.get("html_url", ""),
                }
            )

    output = Path(args.output) if args.output else cfg.dir / f"packages-{cfg.org}.csv"
    output.parent.mkdir(parents=True, exist_ok=True)
    with output.open("w", newline="") as fh:
        writer = csv.DictWriter(fh, fieldnames=CSV_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    print(f"\nFound {len(rows)} package(s) matching /{args.pattern}/.")
    print(f"Review file written to: {output}")
    print("Set 'delete' to 'no' (or remove the row) for anything you want to keep, then run the 'delete' command.")
    return 0


def read_review_file(path: Path) -> list:
    if not path.is_file():
        sys.exit(f"Review file not found: {path}")
    with path.open(newline="") as fh:
        reader = csv.DictReader(fh)
        missing = {"delete", "package_type", "name"} - set(reader.fieldnames or [])
        if missing:
            sys.exit(f"Review file is missing column(s): {', '.join(sorted(missing))}")
        rows = [r for r in reader if (r.get("delete") or "").strip().lower() in ("yes", "y", "true", "1")]
    for row in rows:
        if row["package_type"] not in PACKAGE_TYPES:
            sys.exit(f"Invalid package_type '{row['package_type']}' for package '{row['name']}'.")
    return rows


def cmd_delete(args: argparse.Namespace, cfg: Config) -> int:
    review_file = Path(args.input) if args.input else cfg.dir / f"packages-{cfg.org}.csv"
    rows = read_review_file(review_file)
    dry_run = cfg.dry_run if args.dry_run is None else args.dry_run

    if not rows:
        print("No packages marked for deletion.")
        return 0

    print(f"{len(rows)} package(s) marked for deletion in '{cfg.org}':")
    for row in rows:
        print(f"  - [{row['package_type']}] {row['name']}")

    if dry_run:
        print("\nDRY_RUN is enabled; nothing was deleted. Use --no-dry-run or set DRY_RUN=false to delete.")
        return 0

    session = build_session(cfg.token)
    check_auth(session, cfg.org)

    if not args.yes:
        print("\nConfirm each package: [y]es / [N]o / [a]ll remaining / [q]uit")
    confirm_all = args.yes
    deleted = skipped = failures = 0
    for row in rows:
        label = f"[{row['package_type']}] {row['name']}"
        if not confirm_all:
            answer = input(f"Delete {label}? [y/N/a/q] ").strip().lower()
            if answer == "q":
                print("Quitting; remaining packages were not deleted.")
                skipped += len(rows) - deleted - skipped - failures
                break
            if answer == "a":
                confirm_all = True
            elif answer != "y":
                skipped += 1
                print(f"  skipped  {label}")
                continue

        url = (
            f"{API_URL}/orgs/{quote(cfg.org, safe='')}/packages/"
            f"{quote(row['package_type'], safe='')}/{quote(row['name'], safe='')}"
        )
        resp = session.delete(url, timeout=30)
        if resp.status_code == 204:
            deleted += 1
            print(f"  deleted  {label}")
        else:
            failures += 1
            print(f"  FAILED   {label}: {resp.status_code} {resp.text}", file=sys.stderr)

    print(f"\nDone. Deleted {deleted}, skipped {skipped}, failed {failures}.")
    return 1 if failures else 0


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-file", default=".env", help="Env file with ORG, GH_TOKEN, DIR, DRY_RUN (default: .env)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_list = sub.add_parser("list", help="List packages matching a regex and write a review CSV.")
    p_list.add_argument("pattern", help="Regex matched (re.search) against package names.")
    p_list.add_argument(
        "--package-type",
        nargs="+",
        choices=PACKAGE_TYPES,
        default=list(PACKAGE_TYPES),
        help="Package types to scan (default: all).",
    )
    p_list.add_argument("--case-sensitive", action="store_true", help="Match the regex case-sensitively.")
    p_list.add_argument("-o", "--output", help="Review CSV path (default: $DIR/packages-<org>.csv).")
    p_list.set_defaults(func=cmd_list)

    p_del = sub.add_parser("delete", help="Delete packages marked delete=yes in the review CSV.")
    p_del.add_argument("-i", "--input", help="Review CSV path (default: $DIR/packages-<org>.csv).")
    p_del.add_argument(
        "--dry-run",
        action=argparse.BooleanOptionalAction,
        default=None,
        help="Override DRY_RUN from the env file.",
    )
    p_del.add_argument("-y", "--yes", action="store_true", help="Delete all marked packages without per-package prompts.")
    p_del.set_defaults(func=cmd_delete)
    return parser


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)
    cfg = Config(Path(args.env_file).expanduser())
    return args.func(args, cfg)


if __name__ == "__main__":
    sys.exit(main())
