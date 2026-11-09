import unittest
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import requests

from packages_inheritance import (
    Configuration,
    _ensure_actions_repository_access,
    _prepare_browser_session,
    extract_associated_repository,
    extract_package_repository,
    list_container_packages,
    parse_configuration,
    process_package,
    should_add_actions_access,
)


class ConfigurationTests(unittest.TestCase):
    def test_cli_values_override_environment(self):
        configuration = parse_configuration(
            ["--org", "cli-org", "--profile-dir", "/tmp/cli-profile", "--apply"],
            {
                "ORG": "env-org",
                "GH_TOKEN": "env-token",
                "DIR": "/tmp/env-profile",
                "DRY_RUN": "true",
            },
            env_file=None,
        )

        self.assertEqual(configuration.org, "cli-org")
        self.assertEqual(configuration.profile_dir, Path("/tmp/cli-profile").resolve())
        self.assertFalse(configuration.dry_run)

    def test_environment_values_are_used(self):
        configuration = parse_configuration(
            [],
            {
                "ORG": "env-org",
                "GH_TOKEN": "env-token",
                "DIR": "/tmp/env-profile",
                "DRY_RUN": "yes",
            },
            env_file=None,
        )

        self.assertEqual(configuration.org, "env-org")
        self.assertEqual(configuration.profile_dir, Path("/tmp/env-profile").resolve())
        self.assertTrue(configuration.dry_run)

    def test_cli_dry_run_overrides_false_environment_value(self):
        configuration = parse_configuration(
            ["--org", "acme", "--dry-run"],
            {"GH_TOKEN": "test-token", "DRY_RUN": "false"},
            env_file=None,
        )

        self.assertTrue(configuration.dry_run)

    def test_missing_org_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Set ORG"):
            parse_configuration([], {}, env_file=None)

    def test_invalid_dry_run_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "DRY_RUN"):
            parse_configuration(
                [],
                {"ORG": "acme", "GH_TOKEN": "test-token", "DRY_RUN": "sometimes"},
                env_file=None,
            )

    def test_dotenv_file_is_read_and_shell_environment_overrides_it(self):
        with TemporaryDirectory() as temporary_directory:
            env_file = Path(temporary_directory) / ".env"
            env_file.write_text(
                "ORG=file-org\nGH_TOKEN=file-token\nDIR=/tmp/file-profile\nDRY_RUN=true\n",
                encoding="utf-8",
            )

            configuration = parse_configuration(
                [],
                {"ORG": "shell-org"},
                env_file=env_file,
            )

        self.assertEqual(configuration.org, "shell-org")
        self.assertEqual(configuration.profile_dir, Path("/tmp/file-profile").resolve())
        self.assertTrue(configuration.dry_run)

    def test_env_file_can_be_selected_from_cli(self):
        with TemporaryDirectory() as temporary_directory:
            env_file = Path(temporary_directory) / "custom.env"
            env_file.write_text("ORG=file-org\nGH_TOKEN=file-token\n", encoding="utf-8")

            configuration = parse_configuration(
                ["--env-file", str(env_file)], {}, env_file=None
            )

        self.assertEqual(configuration.org, "file-org")
        self.assertEqual(configuration.github_token, "file-token")

    def test_missing_token_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "GH_TOKEN"):
            parse_configuration([], {"ORG": "acme"}, env_file=None)


class PackageDiscoveryTests(unittest.TestCase):
    def test_extracts_linked_repository_from_package_api_response(self):
        repository = extract_package_repository(
            {"repository": {"full_name": "acme/api"}}, "acme"
        )

        self.assertEqual(repository, "api")

    def test_lists_packages_across_api_pages_with_token(self):
        class FakeResponse:
            def __init__(self, data, next_url=None):
                self.data = data
                self.links = {"next": {"url": next_url}} if next_url else {}

            def raise_for_status(self):
                return None

            def json(self):
                return self.data

        first_page = FakeResponse([{"name": "first"}], "https://api.github.com/page/2")
        second_page = FakeResponse([{"name": "second"}])
        with patch(
            "packages_inheritance.requests.get", side_effect=[first_page, second_page]
        ) as get:
            packages = list_container_packages("acme", "test-token")

        self.assertEqual([package["name"] for package in packages], ["first", "second"])
        self.assertEqual(get.call_args_list[0].kwargs["headers"]["Authorization"], "Bearer test-token")
        self.assertIsNone(get.call_args_list[1].kwargs["params"])

    def test_package_listing_404_explains_org_and_token_access(self):
        response = requests.Response()
        response.status_code = 404
        error = requests.HTTPError(response=response)

        with patch("packages_inheritance.requests.get", side_effect=error):
            with self.assertRaisesRegex(
                RuntimeError,
                "organization 'acme'.*ORG is the organization slug.*read:packages",
            ):
                list_container_packages("acme", "test-token")

    def test_finds_single_linked_repository(self):
        repository = extract_associated_repository(
            "acme", ["https://github.com/acme/api", "/orgs/acme/packages/container/api"]
        )

        self.assertEqual(repository, "api")

    def test_rejects_missing_or_ambiguous_repository_links(self):
        with self.assertRaisesRegex(ValueError, "found none"):
            extract_associated_repository("acme", ["/orgs/acme/packages/container/api"])
        with self.assertRaisesRegex(ValueError, "found multiple"):
            extract_associated_repository(
                "acme", ["/acme/api", "/acme/worker"]
            )


class PackageActionTests(unittest.TestCase):
    def test_browser_session_opens_login_and_waits_for_user(self):
        page = MagicMock()
        with patch("builtins.input", return_value="") as prompt:
            _prepare_browser_session(page)

        page.goto.assert_called_once_with(
            "https://github.com/login", wait_until="domcontentloaded"
        )
        prompt.assert_called_once()

    def test_browser_session_requires_interactive_input(self):
        with patch("builtins.input", side_effect=EOFError):
            with self.assertRaisesRegex(RuntimeError, "interactive terminal"):
                _prepare_browser_session(MagicMock())

    def test_dry_run_reports_package_repository_and_role_without_changes(self):
        page = MagicMock()
        panel = MagicMock()
        output = StringIO()
        package_url = "https://github.com/orgs/acme/packages/container/frontend"

        with patch("packages_inheritance._wait_for_sign_in"), patch(
            "packages_inheritance._actions_access_panel", return_value=panel
        ), patch(
            "packages_inheritance._actions_access_repositories", return_value=[]
        ), redirect_stdout(output):
            _ensure_actions_repository_access(page, "acme", package_url, "api", True)

        self.assertIn("Would add acme/api to Actions access with Admin", output.getvalue())
        self.assertIn(f"{package_url}/settings", output.getvalue())
        panel.get_by_role.assert_not_called()

    def test_existing_access_reports_package_and_preserves_role(self):
        page = MagicMock()
        output = StringIO()
        package_url = "https://github.com/orgs/acme/packages/container/frontend"

        with patch("packages_inheritance._wait_for_sign_in"), patch(
            "packages_inheritance._actions_access_panel"
        ), patch(
            "packages_inheritance._actions_access_repositories", return_value=["api"]
        ), redirect_stdout(output):
            _ensure_actions_repository_access(page, "acme", package_url, "api", True)

        self.assertIn(f"Unchanged {package_url}/settings", output.getvalue())
        self.assertIn("acme/api already has Actions access", output.getvalue())
        self.assertIn("existing role is not changed", output.getvalue())

    def test_dry_run_inspects_actions_access_without_mutating(self):
        configuration = Configuration("acme", Path("/tmp/profile"), True, "test-token")

        with patch("packages_inheritance._ensure_actions_repository_access") as ensure_access:
            process_package(
                None,
                configuration,
                "https://github.com/orgs/acme/packages/container/api",
                "api",
            )

        ensure_access.assert_called_once_with(
            None,
            "acme",
            "https://github.com/orgs/acme/packages/container/api",
            "api",
            True,
        )

    def test_apply_inspects_actions_access(self):
        configuration = Configuration("acme", Path("/tmp/profile"), False, "test-token")

        with patch("packages_inheritance._ensure_actions_repository_access") as ensure_access:
            process_package(
                None,
                configuration,
                "https://github.com/orgs/acme/packages/container/api",
                "api",
            )

        ensure_access.assert_called_once_with(
            None,
            "acme",
            "https://github.com/orgs/acme/packages/container/api",
            "api",
            False,
        )

    def test_existing_actions_access_is_not_selected_for_add(self):
        self.assertFalse(should_add_actions_access("api", ["api"]))
        self.assertFalse(should_add_actions_access("api", ["API"]))

    def test_missing_actions_access_is_selected_for_add(self):
        self.assertTrue(should_add_actions_access("api", []))


if __name__ == "__main__":
    unittest.main()
