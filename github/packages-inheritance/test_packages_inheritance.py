import unittest
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from packages_inheritance import (
    Configuration,
    extract_associated_repository,
    extract_package_urls,
    parse_configuration,
    process_package,
)


class ConfigurationTests(unittest.TestCase):
    def test_cli_values_override_environment(self):
        configuration = parse_configuration(
            ["--org", "cli-org", "--profile-dir", "/tmp/cli-profile", "--apply"],
            {"ORG": "env-org", "DIR": "/tmp/env-profile", "DRY_RUN": "true"},
            env_file=None,
        )

        self.assertEqual(configuration.org, "cli-org")
        self.assertEqual(configuration.profile_dir, Path("/tmp/cli-profile").resolve())
        self.assertFalse(configuration.dry_run)

    def test_environment_values_are_used(self):
        configuration = parse_configuration(
            [],
            {"ORG": "env-org", "DIR": "/tmp/env-profile", "DRY_RUN": "yes"},
            env_file=None,
        )

        self.assertEqual(configuration.org, "env-org")
        self.assertEqual(configuration.profile_dir, Path("/tmp/env-profile").resolve())
        self.assertTrue(configuration.dry_run)

    def test_cli_dry_run_overrides_false_environment_value(self):
        configuration = parse_configuration(
            ["--org", "acme", "--dry-run"], {"DRY_RUN": "false"}, env_file=None
        )

        self.assertTrue(configuration.dry_run)

    def test_missing_org_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "Set ORG"):
            parse_configuration([], {}, env_file=None)

    def test_invalid_dry_run_is_rejected(self):
        with self.assertRaisesRegex(ValueError, "DRY_RUN"):
            parse_configuration(
                [], {"ORG": "acme", "DRY_RUN": "sometimes"}, env_file=None
            )

    def test_dotenv_file_is_read_and_shell_environment_overrides_it(self):
        with TemporaryDirectory() as temporary_directory:
            env_file = Path(temporary_directory) / ".env"
            env_file.write_text(
                "ORG=file-org\nDIR=/tmp/file-profile\nDRY_RUN=true\n",
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
            env_file.write_text("ORG=file-org\n", encoding="utf-8")

            configuration = parse_configuration(
                ["--env-file", str(env_file)], {}, env_file=None
            )

        self.assertEqual(configuration.org, "file-org")


class PackageDiscoveryTests(unittest.TestCase):
    def test_extracts_unique_container_package_urls(self):
        package_urls = extract_package_urls(
            "acme",
            [
                "/orgs/acme/packages/container/api",
                "https://github.com/orgs/acme/packages/container/api?tag=latest",
                "/orgs/acme/packages/npm/library",
                "/orgs/other/packages/container/worker",
                "https://example.com/orgs/acme/packages/container/nope",
            ],
        )

        self.assertEqual(package_urls, ["https://github.com/orgs/acme/packages/container/api"])

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
    def test_dry_run_does_not_open_package_settings(self):
        configuration = Configuration("acme", Path("/tmp/profile"), True)

        with patch("packages_inheritance._ensure_repository_admin") as ensure_admin:
            process_package(
                None,
                configuration,
                "https://github.com/orgs/acme/packages/container/api",
                "api",
            )

        ensure_admin.assert_not_called()

    def test_apply_opens_package_settings(self):
        configuration = Configuration("acme", Path("/tmp/profile"), False)

        with patch("packages_inheritance._ensure_repository_admin") as ensure_admin:
            process_package(
                None,
                configuration,
                "https://github.com/orgs/acme/packages/container/api",
                "api",
            )

        ensure_admin.assert_called_once_with(
            None,
            "acme",
            "https://github.com/orgs/acme/packages/container/api",
            "api",
        )


if __name__ == "__main__":
    unittest.main()
