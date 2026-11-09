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
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    heading = page.get_by_role(
        "heading", name=re.compile(r"manage actions access", re.IGNORECASE)
    )
    add_control = page.get_by_role(
        "button", name=re.compile(r"add repository", re.IGNORECASE)
    ).or_(page.get_by_role("link", name=re.compile(r"add repository", re.IGNORECASE))).or_(
        page.locator("summary").filter(has_text=re.compile(r"add repository", re.IGNORECASE))
    )
    try:
        heading.first.wait_for(state="visible", timeout=10000)
        add_control.first.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeoutError as error:
        raise RuntimeError(
            "Could not find a visible Manage Actions access heading and Add repository control."
        ) from error
    if heading.count() != 1:
        raise RuntimeError("Could not uniquely identify the Manage Actions access section.")
    panel = heading.locator(
        "xpath=ancestor::*[self::section or self::div or self::main or self::article]["
        ".//*[self::button or self::a or self::summary or @role='button']["
        "contains(translate(normalize-space(.), "
        "'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz'), 'add repository')]][1]"
    )
    if not panel.count():
        raise RuntimeError("Could not associate Add repository with the Manage Actions access section.")
    return panel


def _repository_row(page, org: str, repository: str):
    """Find the added repository's role control in the Actions access section."""
    if not re.fullmatch(r"[A-Za-z0-9_.-]+", repository):
        raise RuntimeError("Invalid repository name in package metadata.")
    path = f"/{quote(org, safe='')}/{quote(repository, safe='')}".lower()
    lowercase_href = "translate(@href, 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', 'abcdefghijklmnopqrstuvwxyz')"
    heading = page.get_by_role(
        "heading", name=re.compile(r"manage actions access", re.IGNORECASE)
    )
    link = heading.locator(
        "xpath=following::a[@href][preceding::*[self::h1 or self::h2 or self::h3 "
        "or self::h4 or self::h5 or self::h6][1][contains("
        "translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
        "'abcdefghijklmnopqrstuvwxyz'), 'manage actions access')]]"
        f"[substring({lowercase_href}, string-length(@href) - {len(path) - 1}) = '{path}' "
        f"or substring({lowercase_href}, string-length(@href) - {len(path)}) = '{path}/' "
        "or translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
        f"'abcdefghijklmnopqrstuvwxyz') = '{repository.lower()}']"
    )
    link.first.wait_for(state="visible", timeout=10000)
    if link.count() != 1:
        raise RuntimeError(f"Could not uniquely identify the Actions access link for {org}/{repository}.")
    row = link.locator(
        "xpath=ancestor::*[self::tr or self::li or "
        "(self::div and .//*[self::button or self::summary or self::select or @role='button']["
        "contains(translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
        "'abcdefghijklmnopqrstuvwxyz'), 'role') or self::select])][1]"
    )
    if row.count() != 1:
        raise RuntimeError(f"Could not identify the Actions access row for {org}/{repository}.")
    return row


def _actions_access_repositories(page, org: str) -> list[str]:
    """Read visible repository links after the Actions heading and before the next heading."""
    repositories = []
    heading = page.get_by_role(
        "heading", name=re.compile(r"manage actions access", re.IGNORECASE)
    )
    links = heading.locator(
        "xpath=following::a[@href][preceding::*[self::h1 or self::h2 or self::h3 "
        "or self::h4 or self::h5 or self::h6][1][contains("
        "translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
        "'abcdefghijklmnopqrstuvwxyz'), 'manage actions access')]]"
    )
    for index in range(links.count()):
        link = links.nth(index)
        if not link.is_visible():
            continue
        try:
            repositories.append(
                extract_associated_repository(org, [link.get_attribute("href")])
            )
        except ValueError:
            name = link.inner_text().strip()
            if re.fullmatch(r"[A-Za-z0-9_.-]+", name):
                repositories.append(name)
    return repositories


def _actions_access_has_admin(page) -> bool:
        """Check visible Actions-section text and selected roles for Admin."""
        heading = page.get_by_role(
                "heading", name=re.compile(r"manage actions access", re.IGNORECASE)
        )
        elements = heading.locator(
                "xpath=following::*[preceding::*[self::h1 or self::h2 or self::h3 "
                "or self::h4 or self::h5 or self::h6][1][contains("
                "translate(normalize-space(.), 'ABCDEFGHIJKLMNOPQRSTUVWXYZ', "
                "'abcdefghijklmnopqrstuvwxyz'), 'manage actions access')]]"
                "[self::select or (not(*) and not(self::option))]"
        )
        return elements.evaluate_all(
                """elements => elements.some(element => {
                    const style = getComputedStyle(element);
                    if (!element.getClientRects().length || style.visibility !== 'visible') return false;
                    const text = element.tagName === 'SELECT'
                        ? element.selectedOptions[0]?.textContent || ''
                        : element.innerText || '';
                    return /\\badmin\\b/i.test(text);
                })"""
        )


def should_add_actions_access(repository: str, existing_repositories: Sequence[str]) -> bool:
    """Return whether the linked repository is absent from Actions access."""
    return repository.casefold() not in {
        existing_repository.casefold() for existing_repository in existing_repositories
    }


def _select_admin_role(container, page) -> None:
    """Choose Admin using a visible select or menu control."""
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    selects = container.get_by_role("combobox")
    if selects.count():
        selects.first.select_option(label="Admin")
        selected = selects.first.locator("option:checked")
        if selected.inner_text().strip().casefold() != "admin":
            raise RuntimeError("The repository role did not change to Admin.")
        return

    role_name = re.compile(r"^(?:role:\s*)?(read|write|admin)\b", re.IGNORECASE)
    role_buttons = container.get_by_role("button", name=role_name).or_(
        container.locator("summary").filter(has_text=role_name)
    )
    if role_buttons.count():
        if re.search(r"\badmin\b", role_buttons.first.inner_text(), re.IGNORECASE):
            return
        role_buttons.first.click()
        admin_name = re.compile(r"^admin\b", re.IGNORECASE)
        admin_option = page.get_by_role("menuitem", name=admin_name).or_(
            page.get_by_role("menuitemradio", name=admin_name)
        ).or_(page.get_by_role("option", name=admin_name)).or_(
            page.get_by_role("button", name=admin_name)
        ).locator("visible=true")
        admin_text = page.get_by_text("Admin", exact=True).locator("visible=true")
        try:
            admin_option.or_(admin_text).first.wait_for(state="visible", timeout=10000)
            if admin_option.count() == 1:
                admin_option.first.click()
            elif admin_option.count() == 0 and admin_text.count() == 1:
                admin_text.first.click()
            else:
                raise RuntimeError("Could not uniquely identify the Admin role option.")
            admin_role = re.compile(r"^(?:role:\s*)?admin\b", re.IGNORECASE)
            container.get_by_role("button", name=admin_role).or_(
                container.locator("summary").filter(has_text=admin_role)
            ).first.wait_for(state="visible", timeout=10000)
            return
        except PlaywrightTimeoutError as error:
            raise RuntimeError("Could not select or verify the Admin role.") from error
    raise RuntimeError("Could not identify the repository role control in GitHub UI.")


def _has_admin_role(container) -> bool:
    selects = container.get_by_role("combobox")
    if selects.count():
        return selects.first.locator("option:checked").inner_text().strip().casefold() == "admin"
    admin_role = re.compile(r"^(?:role:\s*)?admin\b", re.IGNORECASE)
    return bool(container.get_by_role("button", name=admin_role).or_(
        container.locator("summary").filter(has_text=admin_role)
    ).count())


def _repository_checkbox(dialog, org: str, repository: str):
        """Find one checkbox whose associated visible row names the exact repository."""
        from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

        handle = dialog.element_handle()
        try:
                result = dialog.page.wait_for_function(
                        """({dialog, names}) => {
                            const checkboxes = [...dialog.querySelectorAll('input[type="checkbox"], [role="checkbox"]')];
                            const matching = [];
                              for (const checkbox of checkboxes) {
                                const candidates = [checkbox.getAttribute('aria-label') || ''];
                                for (const label of checkbox.labels || []) candidates.push(label.innerText);
                                let parent = checkbox.parentElement;
                                while (parent && parent !== dialog &&
                                             parent.querySelectorAll('input[type="checkbox"], [role="checkbox"]').length === 1) {
                                    candidates.push(parent.innerText);
                                    for (const leaf of parent.querySelectorAll('*')) {
                                        if (!leaf.children.length) candidates.push(leaf.innerText || '');
                                    }
                                    parent = parent.parentElement;
                                }
                                const matched = candidates.some(text => text.split(/\\n/).some(
                                    line => names.includes(line.trim().toLowerCase())
                                ));
                                if (matched) matching.push(checkbox);
                            }
                            return matching.length ? matching : false;
                        }""",
                        arg={"dialog": handle, "names": [repository.lower(), f"{org}/{repository}".lower()]},
                        timeout=10000,
                )
        except PlaywrightTimeoutError as error:
                raise RuntimeError(
                        f"Could not match a repository checkbox for {org}/{repository} within 10 seconds."
                ) from error
        finally:
                handle.dispose()
        try:
            if result.evaluate("matches => matches.length") != 1:
                raise RuntimeError(f"Could not uniquely identify the checkbox for {org}/{repository}.")
            return result.get_property("0").as_element()
        finally:
            result.dispose()


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
    if _actions_access_has_admin(page):
        print(f"Unchanged {settings_url}: Admin is already visible in Manage Actions access.")
        return
    existing_repositories = _actions_access_repositories(page, org)
    if not should_add_actions_access(repository, existing_repositories):
        from playwright.sync_api import Error as PlaywrightError

        try:
            row = _repository_row(page, org, repository)
            if _has_admin_role(row):
                print(f"Unchanged {settings_url}: {org}/{repository} already has Admin Actions access.")
                return
            if dry_run:
                print(f"Would change {org}/{repository} Actions access to Admin: {settings_url}")
                return
            _select_admin_role(row, page)
            page.wait_for_load_state("networkidle", timeout=10000)
            page.reload(wait_until="domcontentloaded")
            _wait_for_sign_in(page, settings_url)
            if not _has_admin_role(_repository_row(page, org, repository)):
                raise RuntimeError("Admin role was not present after reloading the package settings.")
        except (RuntimeError, PlaywrightError) as error:
            raise RuntimeError(
                f"Could not confirm Admin Actions access for {org}/{repository}; "
                f"check the package settings: {error}"
            ) from error
        print(f"Changed {org}/{repository} Actions access to Admin: {settings_url}")
        return
    if existing_repositories:
        print(
            f"Unchanged {settings_url}: Actions access is already configured for "
            f"{', '.join(f'{org}/{name}' for name in existing_repositories)} "
            "(existing access is not changed)."
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
        add_button = panel.locator("summary").filter(
            has_text=re.compile(r"add repository", re.IGNORECASE)
        )
    if not add_button.count():
        raise RuntimeError("Could not find Add repository in Manage Actions access.")
    add_button.first.click()

    from playwright.sync_api import Error as PlaywrightError
    from playwright.sync_api import TimeoutError as PlaywrightTimeoutError

    dialog = page.get_by_role("dialog").first
    try:
        dialog.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeoutError as error:
        raise RuntimeError("Could not find the Add repository dialog.") from error

    search_fields = dialog.locator('input:not([type]), input[type="text"], input[type="search"]')
    try:
        search_fields.first.wait_for(state="visible", timeout=10000)
    except PlaywrightTimeoutError as error:
        raise RuntimeError("Could not find the repository search field.") from error
    search_fields.first.fill(repository)

    checkbox = _repository_checkbox(dialog, org, repository)
    try:
        checkbox.check(timeout=10000)
    except PlaywrightError as error:
        raise RuntimeError(f"Could not select the checkbox for {org}/{repository}.") from error
    finally:
        checkbox.dispose()

    submit = dialog.get_by_role(
        "button", name=re.compile(r"^add repositor(?:y|ies)$", re.IGNORECASE)
    )
    try:
        submit.first.wait_for(state="visible", timeout=10000)
        if submit.count() != 1:
            raise RuntimeError("Could not uniquely identify the Add repositories button.")
        submit.first.click(timeout=10000)
    except PlaywrightError as error:
        raise RuntimeError(
            f"Could not confirm submission for {org}/{repository}; "
            "check the package settings before retrying."
        ) from error

    try:
        verified_row = _repository_row(page, org, repository)
        _select_admin_role(verified_row, page)
        page.wait_for_load_state("networkidle", timeout=10000)
        page.reload(wait_until="domcontentloaded")
        _wait_for_sign_in(page, settings_url)
        verified_row = _repository_row(page, org, repository)
        if not _has_admin_role(verified_row):
            raise RuntimeError("Admin role was not present after reloading the package settings.")
    except (RuntimeError, PlaywrightError) as error:
        raise RuntimeError(
            f"Add was submitted for {org}/{repository}, but Admin access could not be "
            f"confirmed; check and correct the package settings manually: {error}"
        ) from error
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
