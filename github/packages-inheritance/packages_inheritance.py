#!/usr/bin/env python3
"""Manage repository access for GitHub Container Registry packages."""

import argparse
from dataclasses import dataclass
import os
from pathlib import Path
import re
import sys
from typing import Any, Mapping, Optional, Sequence
from urllib.parse import quote, unquote, urljoin, urlparse

from dotenv import dotenv_values
import requests


DEFAULT_PROFILE_DIR = "~/.cache/github-packages-inheritance"
DEFAULT_ENV_FILE = Path(__file__).with_name(".env")
PACKAGE_LIST_URL = "https://github.com/orgs/{org}/packages?ecosystem=container"


@dataclass(frozen=True)
class Configuration:
    """Resolved command-line and environment configuration."""

    org: str
    profile_dir: Path
    dry_run: bool
    github_token: str


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
    github_token = environment.get("GH_TOKEN")
    if github_token is None or not github_token.strip():
        raise ValueError("Set GH_TOKEN in .env or the shell environment.")

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
        github_token=github_token.strip(),
    )


def list_container_packages(org: str, token: str) -> list[dict[str, Any]]:
    """List all readable organization container packages through the REST API."""
    url = f"https://api.github.com/orgs/{quote(org, safe='')}/packages"
    params: Optional[dict[str, str | int]] = {
        "package_type": "container",
        "per_page": 100,
    }
    headers = {
        "Accept": "application/vnd.github+json",
        "Authorization": f"Bearer {token}",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    packages: list[dict[str, Any]] = []

    while url:
        try:
            response = requests.get(url, headers=headers, params=params, timeout=30)
            response.raise_for_status()
        except requests.HTTPError as error:
            status_code = error.response.status_code if error.response is not None else None
            if status_code == 401:
                raise RuntimeError("GH_TOKEN is invalid or lacks read:packages access.") from error
            if status_code == 403:
                raise RuntimeError(
                    "GH_TOKEN cannot list packages in this organization; check token scopes and org access."
                ) from error
            if status_code == 404:
                raise RuntimeError(
                    f"GitHub could not find or allow access to the package listing for "
                    f"organization {org!r}. Verify ORG is the organization slug and "
                    "GH_TOKEN has read:packages access to the organization, including "
                    "SSO authorization if required."
                ) from error
            raise RuntimeError(
                f"GitHub package listing failed with HTTP {status_code}."
            ) from error
        except requests.RequestException as error:
            raise RuntimeError("Could not connect to the GitHub Packages API.") from error

        page_packages = response.json()
        if not isinstance(page_packages, list):
            raise RuntimeError("GitHub returned an unexpected package-list response.")
        packages.extend(page_packages)
        url = response.links.get("next", {}).get("url")
        params = None

    return packages


def extract_package_repository(package: Mapping[str, Any], org: str) -> str:
    """Return the linked organization repository name from package metadata."""
    repository = package.get("repository")
    full_name = repository.get("full_name") if isinstance(repository, dict) else None
    if not isinstance(full_name, str) or "/" not in full_name:
        raise ValueError("Package has no linked repository in its metadata.")
    owner, repository_name = full_name.split("/", 1)
    if owner.casefold() != org.casefold() or not repository_name:
        raise ValueError(f"Linked repository {full_name!r} is not in {org}.")
    return repository_name


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


def _prepare_browser_session(page) -> None:
    """Let the user sign in and complete any organization SSO before processing."""
    page.goto("https://github.com/login", wait_until="domcontentloaded")
    print(
        "Sign in to GitHub in the opened browser and complete any organization SSO. "
        "If already signed in, confirm you are using the correct account.",
        file=sys.stderr,
    )
    try:
        input("Press Enter when the browser session is ready... ")
    except EOFError as error:
        raise RuntimeError("An interactive terminal is required for browser sign-in.") from error


def _wait_for_sign_in(page, destination: str) -> None:
    """Pause for interactive sign-in if GitHub redirected to its login page."""
    if "/login" not in urlparse(page.url).path:
        return
    print("Sign in to GitHub in the opened browser, then return here.", file=sys.stderr)
    input("Press Enter after sign-in is complete... ")
    page.goto(destination, wait_until="domcontentloaded")
    if "/login" in urlparse(page.url).path:
        raise RuntimeError("GitHub still requires sign-in; stopping without changes.")


def _actions_access_panel(page):
    """Locate the package's Manage Actions access section or fail closed."""
    heading = page.get_by_role(
        "heading", name=re.compile(r"manage actions access", re.IGNORECASE)
    )
    if heading.count() != 1:
        raise RuntimeError("Could not uniquely identify the Manage Actions access section.")
    panel = heading.locator(
        "xpath=ancestor::*[self::section or self::div]["
        ".//button[contains(translate(normalize-space(.), "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'add repository')] "
        "or .//a[contains(translate(normalize-space(.), "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'add repository')]][1]"
    )
    if not panel.count():
        raise RuntimeError("Could not find Add repository in Manage Actions access.")
    return panel


def _repository_row(panel, org: str, repository: str):
    """Find a repository row only inside the Actions access section."""
    rows = panel.locator("tr")
    for index in range(rows.count()):
        row = rows.nth(index)
        try:
            row_repository = extract_associated_repository(org, _page_hrefs(row))
        except ValueError:
            continue
        if row_repository.casefold() == repository.casefold():
            return row
    return None


def _actions_access_repositories(panel, org: str) -> list[str]:
    """Read repository names from rows in the Actions access section only."""
    repositories = []
    rows = panel.locator("tr")
    for index in range(rows.count()):
        try:
            repositories.append(
                extract_associated_repository(org, _page_hrefs(rows.nth(index)))
            )
        except ValueError:
            continue
    return repositories


def should_add_actions_access(repository: str, existing_repositories: Sequence[str]) -> bool:
    """Return whether the linked repository is absent from Actions access."""
    return repository.casefold() not in {
        existing_repository.casefold() for existing_repository in existing_repositories
    }


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


def _ensure_actions_repository_access(
    page, org: str, package_name: str, repository: str, dry_run: bool
) -> None:
    """Add a missing Actions repository with Admin; leave existing access alone."""
    settings_url = (
        f"https://github.com/orgs/{quote(org, safe='')}/packages/container/"
        f"{quote(package_name, safe='')}/settings"
    )
    page.goto(settings_url, wait_until="domcontentloaded")
    _wait_for_sign_in(page, settings_url)

    panel = _actions_access_panel(page)
    existing_repositories = _actions_access_repositories(panel, org)
    if not should_add_actions_access(repository, existing_repositories):
        print(
            f"Unchanged {settings_url}: {org}/{repository} already has Actions access "
            "(existing role is not changed)."
        )
        return

    if dry_run:
        print(
            f"Would add {org}/{repository} to Actions access with Admin: {settings_url}"
        )
        return

    add_button = panel.get_by_role(
        "button", name=re.compile(r"add repository", re.IGNORECASE)
    )
    if not add_button.count():
        add_button = panel.get_by_role(
            "link", name=re.compile(r"add repository", re.IGNORECASE)
        )
    if not add_button.count():
        raise RuntimeError("Could not find Add repository in Manage Actions access.")
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

    verified_row = _repository_row(panel, org, repository)
    if verified_row is None or not re.search(
        r"\badmin\b", verified_row.inner_text(), re.IGNORECASE
    ):
        raise RuntimeError(f"Could not verify Admin Actions access for {org}/{repository}.")
    print(f"Added {org}/{repository} to Actions access with Admin: {settings_url}")


def process_package(
    page, configuration: Configuration, package_name: str, repository: str
) -> None:
    """Inspect Actions access and add only a missing linked repository."""
    _ensure_actions_repository_access(
        page,
        configuration.org,
        package_name,
        repository,
        configuration.dry_run,
    )


def run(configuration: Configuration) -> int:
    """Discover eligible packages and optionally apply Admin access."""
    try:
        from playwright.sync_api import sync_playwright
    except ImportError as error:
        raise RuntimeError(
            "Playwright is missing. Install requirements.txt and run "
            "'python -m playwright install chromium'."
        ) from error

    packages = list_container_packages(configuration.org, configuration.github_token)
    if not packages:
        print(f"No container packages found for {configuration.org}.")
        return 0

    configuration.profile_dir.mkdir(parents=True, exist_ok=True)
    failures = 0

    with sync_playwright() as playwright:
        context = playwright.chromium.launch_persistent_context(
            user_data_dir=str(configuration.profile_dir),
            headless=False,
        )
        try:
            page = context.pages[0] if context.pages else context.new_page()
            _prepare_browser_session(page)
            for package in packages:
                package_name = package.get("name")
                if not isinstance(package_name, str) or not package_name.strip():
                    failures += 1
                    print("Skipped <unnamed>: Package metadata has no valid name.", file=sys.stderr)
                    continue
                try:
                    repository = extract_package_repository(package, configuration.org)
                except ValueError as error:
                    failures += 1
                    print(f"Skipped {package_name}: {error}", file=sys.stderr)
                    continue

                try:
                    process_package(page, configuration, package_name, repository)
                except (RuntimeError, ValueError) as error:
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
