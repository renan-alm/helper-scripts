#!/usr/bin/env python3
"""Manage repository access for GitHub Container Registry packages."""

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys
from typing import Mapping, Optional, Sequence
from urllib.parse import unquote, urljoin, urlparse

from dotenv import dotenv_values


DEFAULT_PROFILE_DIR = "~/.cache/github-packages-inheritance"
DEFAULT_ENV_FILE = Path(__file__).with_name(".env")
PACKAGE_LIST_URL = "https://github.com/orgs/{org}/packages?ecosystem=container"


@dataclass(frozen=True)
class Configuration:
    """Resolved command-line and environment configuration."""

    org: str
    profile_dir: Path
    dry_run: bool


def build_parser() -> argparse.ArgumentParser:
    """Create the command-line parser."""
    parser = argparse.ArgumentParser(
        description=(
            "Find GitHub Container Registry packages and grant their linked "
            "repositories Admin access."
        )
    )
    parser.add_argument("--org", type=str, help="GitHub organization slug (or ORG).")
    parser.add_argument(
        "--env-file",
        type=str,
        help="Environment file to load (default: .env beside this script).",
    )
    parser.add_argument(
        "--profile-dir",
        type=str,
        help="Persistent Playwright browser profile directory (or DIR).",
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "--dry-run",
        dest="dry_run",
        action="store_const",
        const=True,
        default=None,
        help="Report planned access changes without applying them.",
    )
    mode.add_argument(
        "--apply",
        dest="dry_run",
        action="store_const",
        const=False,
        help="Apply access changes, overriding DRY_RUN.",
    )
    return parser


def parse_boolean(value: str, variable_name: str) -> bool:
    """Parse a conventional environment-variable boolean."""
    normalized = value.strip().lower()
    if normalized in {"1", "true", "yes", "on"}:
        return True
    if normalized in {"0", "false", "no", "off"}:
        return False
    raise ValueError(
        f"{variable_name} must be one of true/false, 1/0, yes/no, or on/off."
    )


def parse_configuration(
    argv: Optional[Sequence[str]] = None,
    environ: Optional[Mapping[str, str]] = None,
    env_file: Optional[Path] = DEFAULT_ENV_FILE,
) -> Configuration:
    """Load file and process environment, then let explicit CLI options win."""
    arguments = build_parser().parse_args(argv)
    selected_env_file = (
        Path(arguments.env_file).expanduser() if arguments.env_file else env_file
    )
    environment = {}
    if selected_env_file is not None:
        environment = {
            key: value
            for key, value in dotenv_values(selected_env_file).items()
            if value is not None
        }
    environment.update(os.environ if environ is None else environ)

    org = arguments.org if arguments.org is not None else environment.get("ORG")
    if org is None or not org.strip():
        raise ValueError("Set ORG or pass --org with a GitHub organization slug.")

    profile_dir = (
        arguments.profile_dir
        if arguments.profile_dir is not None
        else environment.get("DIR", DEFAULT_PROFILE_DIR)
    )
    dry_run = arguments.dry_run
    if dry_run is None:
        env_dry_run = environment.get("DRY_RUN")
        dry_run = parse_boolean(env_dry_run, "DRY_RUN") if env_dry_run else False

    return Configuration(
        org=org.strip(),
        profile_dir=Path(profile_dir).expanduser().resolve(),
        dry_run=dry_run,
    )


def extract_package_urls(org: str, hrefs: Sequence[str]) -> list[str]:
    """Return unique container-package URLs belonging to the organization."""
    package_urls: list[str] = []
    prefix = ["orgs", org.casefold(), "packages", "container"]
    for href in hrefs:
        parsed = urlparse(urljoin("https://github.com", href))
        if parsed.netloc.casefold() != "github.com":
            continue
        segments = [unquote(part) for part in parsed.path.strip("/").split("/")]
        if len(segments) != 5 or [part.casefold() for part in segments[:4]] != prefix:
            continue
        if not segments[4]:
            continue
        canonical_url = f"https://github.com/{'/'.join(segments)}"
        if canonical_url not in package_urls:
            package_urls.append(canonical_url)
    return package_urls


def extract_associated_repository(org: str, hrefs: Sequence[str]) -> str:
    """Return a sole organization repository link or fail closed."""
    repositories: set[str] = set()
    for href in hrefs:
        parsed = urlparse(urljoin("https://github.com", href))
        if parsed.netloc.casefold() != "github.com":
            continue
        segments = [unquote(part) for part in parsed.path.strip("/").split("/")]
        if (
            len(segments) == 2
            and segments[0].casefold() == org.casefold()
            and segments[1]
        ):
            repositories.add(segments[1])
    if len(repositories) != 1:
        reason = "none" if not repositories else "multiple"
        raise ValueError(f"Expected one linked repository, found {reason}.")
    return next(iter(repositories))


def _page_hrefs(page) -> list[str]:
    """Read links currently rendered on a Playwright page."""
    return page.locator("a[href]").evaluate_all(
        "anchors => anchors.map(anchor => anchor.href)"
    )


def _wait_for_sign_in(page, destination: str) -> None:
    """Pause for interactive sign-in if GitHub redirected to its login page."""
    if "/login" not in urlparse(page.url).path:
        return
    print("Sign in to GitHub in the opened browser, then return here.", file=sys.stderr)
    input("Press Enter after sign-in is complete... ")
    page.goto(destination, wait_until="domcontentloaded")
    if "/login" in urlparse(page.url).path:
        raise RuntimeError("GitHub still requires sign-in; stopping without changes.")


def _repository_row(page, org: str, repository: str):
    """Find an access-table row for a repository, if one is present."""
    rows = page.locator("tr")
    for index in range(rows.count()):
        row = rows.nth(index)
        try:
            row_repository = extract_associated_repository(org, _page_hrefs(row))
        except ValueError:
            continue
        if row_repository.casefold() == repository.casefold():
            return row
    return None


def _select_admin_role(container) -> None:
    """Choose Admin using a visible select or menu control."""
    selects = container.get_by_role("combobox")
    if selects.count():
        selects.first.select_option(label="Admin")
        return

    role_buttons = container.get_by_role(
        "button", name=re.compile(r"^(read|write|admin)$", re.IGNORECASE)
    )
    if role_buttons.count():
        role_buttons.first.click()
        admin_option = container.get_by_role("menuitem", name="Admin", exact=True)
        if not admin_option.count():
            admin_option = container.get_by_role("option", name="Admin", exact=True)
        if admin_option.count():
            admin_option.first.click()
            return
    raise RuntimeError("Could not identify the repository role control in GitHub UI.")


def _ensure_repository_admin(page, org: str, package_url: str, repository: str) -> None:
    """Add a repository to package access or promote its existing role to Admin."""
    package_path = urlparse(package_url).path.rstrip("/")
    settings_url = f"https://github.com{package_path}/settings"
    page.goto(settings_url, wait_until="domcontentloaded")
    _wait_for_sign_in(page, settings_url)

    row = _repository_row(page, org, repository)
    if row is not None:
        if re.search(r"\badmin\b", row.inner_text(), re.IGNORECASE):
            print(f"Already Admin: {org}/{repository}")
            return
        _select_admin_role(row)
        save_button = page.get_by_role("button", name=re.compile(r"^save$", re.IGNORECASE))
        if save_button.count():
            save_button.first.click()
        updated_row = _repository_row(page, org, repository)
        if updated_row is None or not re.search(
            r"\badmin\b", updated_row.inner_text(), re.IGNORECASE
        ):
            raise RuntimeError(f"Could not verify Admin access for {org}/{repository}.")
        print(f"Granted Admin: {org}/{repository}")
        return

    add_button = page.get_by_role(
        "button", name=re.compile(r"add repository", re.IGNORECASE)
    )
    if not add_button.count():
        add_button = page.get_by_role("link", name=re.compile(r"add repository", re.IGNORECASE))
    if not add_button.count():
        raise RuntimeError("Could not find GitHub's Add repository control.")
    add_button.first.click()

    dialogs = page.get_by_role("dialog")
    dialog = dialogs.first if dialogs.count() else page
    search_fields = dialog.locator('input[type="text"], input[type="search"]')
    if not search_fields.count():
        raise RuntimeError("Could not find the repository search field.")
    search_fields.first.fill(f"{org}/{repository}")

    repository_option = dialog.get_by_text(f"{org}/{repository}", exact=True)
    if not repository_option.count():
        repository_option = dialog.get_by_text(repository, exact=True)
    if not repository_option.count():
        raise RuntimeError(f"GitHub did not offer repository {org}/{repository}.")
    repository_option.first.click()
    _select_admin_role(dialog)

    submit = dialog.get_by_role(
        "button", name=re.compile(r"^add repository$", re.IGNORECASE)
    )
    if not submit.count():
        raise RuntimeError("Could not find the confirmation control for adding a repository.")
    submit.first.click()

    verified_row = _repository_row(page, org, repository)
    if verified_row is None or not re.search(
        r"\badmin\b", verified_row.inner_text(), re.IGNORECASE
    ):
        raise RuntimeError(f"Could not verify Admin access for {org}/{repository}.")
    print(f"Granted Admin: {org}/{repository}")


def process_package(
    page, configuration: Configuration, package_url: str, repository: str
) -> None:
    """Report or apply the access change for one package."""
    package_name = unquote(urlparse(package_url).path.rstrip("/").split("/")[-1])
    if configuration.dry_run:
        print(
            f"Would grant Admin to {configuration.org}/{repository} "
            f"for package {package_name}."
        )
        return
    _ensure_repository_admin(page, configuration.org, package_url, repository)


def run(configuration: Configuration) -> int:
    """Discover eligible packages and optionally apply Admin access."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RuntimeError(
            "Playwright is missing. Install requirements.txt and run "
            "'python -m playwright install chromium'."
        ) from error

    list_url = PACKAGE_LIST_URL.format(org=configuration.org)
    configuration.profile_dir.mkdir(parents=True, exist_ok=True)
    failures = 0

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(configuration.profile_dir),
            headless=False,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            page.goto(list_url, wait_until="domcontentloaded")
            _wait_for_sign_in(page, list_url)
            package_urls = extract_package_urls(configuration.org, _page_hrefs(page))
            if not package_urls:
                print(f"No container packages found for {configuration.org}.")
                return 0

            for package_url in package_urls:
                page.goto(package_url, wait_until="domcontentloaded")
                package_name = unquote(urlparse(package_url).path.rstrip("/").split("/")[-1])
                try:
                    repository = extract_associated_repository(
                        configuration.org, _page_hrefs(page)
                    )
                except ValueError as error:
                    failures += 1
                    print(f"Skipped {package_name}: {error}", file=sys.stderr)
                    continue

                try:
                    process_package(page, configuration, package_url, repository)
                except RuntimeError as error:
                    failures += 1
                    print(f"Skipped {package_name}: {error}", file=sys.stderr)

        finally:
            context.close()

    return 1 if failures else 0


def main(argv: Optional[Sequence[str]] = None) -> int:
    """Run the command-line application."""
    try:
        configuration = parse_configuration(argv)
        return run(configuration)
    except (ValueError, RuntimeError) as error:
        print(f"Error: {error}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
