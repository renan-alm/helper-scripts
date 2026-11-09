import unittest
from contextlib import redirect_stderr, redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import MagicMock, patch

import requests

from packages_inheritance import (
    Configuration,
    _actions_access_panel,
    _ensure_actions_repository_access,
    _has_admin_role,
    _prepare_browser_session,
    _repository_checkbox,
    _select_admin_role,
    extract_associated_repository,
    extract_package_repository,
    list_container_packages,
    parse_configuration,
    process_package,
    run,
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


class ActionsPanelBrowserTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        from playwright.sync_api import sync_playwright

        cls.playwright = sync_playwright().start()
        if not Path(cls.playwright.chromium.executable_path).exists():
            cls.playwright.stop()
            raise unittest.SkipTest("Playwright Chromium is not installed")
        cls.browser = cls.playwright.chromium.launch(headless=True)

    @classmethod
    def tearDownClass(cls):
        cls.browser.close()
        cls.playwright.stop()

    def test_existing_read_role_is_changed_to_admin(self):
        page = self.browser.new_page()
        try:
            page.set_content("""
                <section><div><h2>Manage Actions access</h2><button>Add Repository</button></div>
                <div><a href="/orgs/SymriseAG/packages/access/123">kl-petfood-rnd-pipeline</a>
                <button onclick="document.querySelector('[role=menu]').hidden=false">Role: Read</button></div></section>
                <div role="menu" hidden><button role="menuitem" onclick="document.querySelector('section div:nth-child(2) button').textContent='Role: Admin'">Admin</button></div>
            """)
            output = StringIO()
            with patch.object(page, "goto"), patch.object(page, "reload"), patch(
                "packages_inheritance._wait_for_sign_in"
            ), redirect_stdout(output):
                _ensure_actions_repository_access(page, "SymriseAG", "image", "kl-petfood-rnd-pipeline", False)
            self.assertTrue(page.get_by_role("button", name="Role: Admin").is_visible())
            self.assertIn("Changed SymriseAG/kl-petfood-rnd-pipeline Actions access to Admin", output.getvalue())
        finally:
            page.close()

    def test_existing_read_role_is_only_reported_in_dry_run(self):
        page = self.browser.new_page()
        try:
            page.set_content("""
                <section><h2>Manage Actions access</h2><button>Add Repository</button>
                <div><a href="/orgs/acme/packages/access/123">api</a>
                <button onclick="this.textContent='clicked'">Role: Read</button></div></section>
            """)
            output = StringIO()
            with patch.object(page, "goto"), patch("packages_inheritance._wait_for_sign_in"), redirect_stdout(output):
                _ensure_actions_repository_access(page, "acme", "image", "api", True)
            self.assertIn("Would change acme/api Actions access to Admin", output.getvalue())
            self.assertTrue(page.get_by_role("button", name="Role: Read").is_visible())
        finally:
            page.close()

    def test_existing_admin_role_is_left_unchanged(self):
        page = self.browser.new_page()
        try:
            page.set_content("""
                <section><h2>Manage Actions access</h2><button>Add Repository</button>
                <div><a href="/orgs/acme/packages/access/123">api</a>
                <button onclick="this.textContent='clicked'">Role: Admin</button></div></section>
            """)
            output = StringIO()
            with patch.object(page, "goto"), patch("packages_inheritance._wait_for_sign_in"), redirect_stdout(output):
                _ensure_actions_repository_access(page, "acme", "image", "api", False)
            self.assertIn("acme/api already has Admin Actions access", output.getvalue())
            self.assertTrue(page.get_by_role("button", name="Role: Admin").is_visible())
        finally:
            page.close()

    def test_ambiguous_repository_checkboxes_are_not_selected(self):
        page = self.browser.new_page()
        try:
            page.set_content("""
                <div role="dialog">
                <label><input type="checkbox">api</label>
                <label><input type="checkbox">api</label></div>
            """)
            with self.assertRaisesRegex(RuntimeError, "uniquely identify"):
                _repository_checkbox(page.get_by_role("dialog"), "acme", "api")
            self.assertEqual(page.locator('input:checked').count(), 0)
        finally:
            page.close()

    def test_apply_selects_exact_checkbox_in_delayed_dialog(self):
        page = self.browser.new_page()
        try:
            page.set_content("""
                <main><h2>Repository source</h2><a href="/SymriseAG/atlas-usecase-research">atlas-usecase-research</a>
                <section><h2>Manage Actions access</h2>
                <button onclick="setTimeout(() => document.querySelector('[role=dialog]').hidden=false, 150)">Add Repository</button>
                <table id="access"></table></section></main>
                <div role="dialog" hidden><input type="search">
                <div><input id="exact" type="checkbox" aria-label="Select repository"><span>atlas-usecase-research</span></div>
                <div><input id="similar" type="checkbox" aria-label="Select repository"><span>atlas-usecase-research-api</span></div>
                <button id="submit" disabled onclick="addRepository()">Add repositories</button></div>
                <script>
                document.querySelector('#exact').onchange = event => {
                  document.querySelector('#submit').disabled = !event.target.checked;
                };
                function addRepository() {
                  document.querySelector('[role=dialog]').hidden = true;
                  document.querySelector('#access').innerHTML =
                    '<tr><td><a href="/SymriseAG/atlas-usecase-research">atlas-usecase-research</a></td>' +
                    '<td><select><option>Read</option><option>Admin</option></select></td></tr>';
                }
                </script>
            """)
            with patch.object(page, "goto"), patch.object(page, "reload"), patch(
                "packages_inheritance._wait_for_sign_in"
            ), redirect_stdout(StringIO()):
                _ensure_actions_repository_access(
                    page, "SymriseAG", "openpom", "atlas-usecase-research", False
                )
            self.assertTrue(page.locator("#exact").is_checked())
            self.assertFalse(page.locator("#similar").is_checked())
            self.assertEqual(page.locator("#access select").input_value(), "Admin")
        finally:
            page.close()

    def test_selects_checkbox_when_row_has_extra_hidden_text(self):
        page = self.browser.new_page()
        try:
            page.set_content("""
                <section><h2>Manage Actions access</h2>
                <button onclick="document.querySelector('[role=dialog]').hidden=false">Add Repository</button>
                <table id="access"></table></section>
                <div role="dialog" hidden><input type="search">
                <div><input id="target" type="checkbox"><span hidden>Private repository</span><strong>gcp-app-symsearch</strong></div>
                <div><input id="other" type="checkbox"><strong>gcp-app-symsearch-api</strong></div>
                <button onclick="document.querySelector('#access').innerHTML =
                  '<tr><td><a href=/SymriseAG/gcp-app-symsearch>gcp-app-symsearch</a></td><td><select><option>Read</option><option>Admin</option></select></td></tr>'">Add repositories</button></div>
            """)
            with patch.object(page, "goto"), patch.object(page, "reload"), patch(
                "packages_inheritance._wait_for_sign_in"
            ), redirect_stdout(StringIO()):
                _ensure_actions_repository_access(page, "SymriseAG", "image", "gcp-app-symsearch", False)
            self.assertTrue(page.locator("#target").is_checked())
            self.assertFalse(page.locator("#other").is_checked())
        finally:
            page.close()

    def test_selects_admin_from_summary_role_control(self):
        page = self.browser.new_page()
        try:
            page.set_content("""
                <div id="row"><details><summary>Role: Read</summary>
                <button role="menuitem" onclick="document.querySelector('summary').textContent='Role: Admin'">
                Admin<span> Can manage this package.</span></button></details></div>
            """)
            row = page.locator("#row")
            _select_admin_role(row, page)
            self.assertTrue(_has_admin_role(row))
        finally:
            page.close()

    def test_selects_admin_from_menu_without_menuitem_role(self):
        page = self.browser.new_page()
        try:
            page.set_content("""
                <div id="row"><details><summary>Role: Read</summary>
                <div onclick="document.querySelector('summary').textContent='Role: Admin'">
                <span>Admin</span><p>Can upload, download, and manage this package.</p></div>
                </details></div>
            """)
            row = page.locator("#row")
            _select_admin_role(row, page)
            self.assertTrue(_has_admin_role(row))
        finally:
            page.close()

    def test_apply_sets_admin_on_non_table_row_with_descriptive_menu(self):
        page = self.browser.new_page()
        try:
            page.set_content("""
                <main><section><div><h2>Manage Actions access</h2>
                <button onclick="document.querySelector('[role=dialog]').hidden=false">Add Repository</button>
                </div><div id="access"></div></section><h2>Manage Codespaces access</h2></main>
                <div role="dialog" hidden><input type="search">
                <label><input type="checkbox">harbour-app-myembassy</label>
                <button onclick="addRepository()">Add repositories</button></div>
                <div role="menu" id="roles" hidden>
                <button role="menuitem" onclick="setAdmin()">Admin<span> Can upload, download, and manage this package.</span></button>
                </div><script>
                function addRepository() {
                  document.querySelector('[role=dialog]').hidden = true;
                  setTimeout(() => document.querySelector('#access').innerHTML =
                    '<div><input type="checkbox"><a href="/SymriseAG/harbour-app-myembassy">harbour-app-myembassy</a>' +
                                        '<button onclick="showRoles()">Role: Read</button></div>', 100);
                }
                                function showRoles() { document.querySelector('#roles').hidden = false; }
                function setAdmin() {
                  document.querySelector('#access button').textContent = 'Role: Admin';
                  document.querySelector('#roles').hidden = true;
                }
                </script>
            """)
            output = StringIO()
            with patch.object(page, "goto"), patch.object(page, "reload") as reload_page, patch(
                "packages_inheritance._wait_for_sign_in"
            ), redirect_stdout(output):
                _ensure_actions_repository_access(
                    page, "SymriseAG", "myembassy-strapi", "harbour-app-myembassy", False
                )
            self.assertTrue(page.get_by_role("button", name="Role: Admin").is_visible())
            self.assertIn("Added SymriseAG/harbour-app-myembassy", output.getvalue())
            reload_page.assert_called_once_with(wait_until="domcontentloaded")
        finally:
            page.close()

    def test_apply_reports_failure_when_admin_does_not_persist(self):
        page = self.browser.new_page()
        try:
            page.set_content("""
                <section><h2>Manage Actions access</h2>
                <button onclick="document.querySelector('[role=dialog]').hidden=false">Add Repository</button>
                <table id="access"></table></section>
                <div role="dialog" hidden><input type="text">
                <label><input type="checkbox">api</label>
                <button onclick="document.querySelector('#access').innerHTML =
                '<tr><td><a href=/acme/api>api</a></td><td><select><option>Read</option><option>Admin</option></select></td></tr>'">Add repositories</button></div>
            """)
            def reset_role(**kwargs):
                page.locator("#access select").select_option(label="Read")

            with patch.object(page, "goto"), patch.object(page, "reload", side_effect=reset_role), patch(
                "packages_inheritance._wait_for_sign_in"
            ):
                with self.assertRaisesRegex(RuntimeError, "Admin role was not present after reloading"):
                    _ensure_actions_repository_access(page, "acme", "image", "api", False)
        finally:
            page.close()

    def test_existing_access_in_non_table_list_skips_without_clicking(self):
        page = self.browser.new_page()
        try:
            page.set_content("""
                <main>
                <h2>Repository source</h2><a href="/acme/source">source</a>
                <section><div><h2>Manage Actions access</h2>
                <button onclick="this.dataset.clicked = 'yes'">Add Repository</button></div>
                <div><input type="checkbox"><a href="/acme/other-repo">other-repo</a>
                <button>Role: Admin</button></div></section>
                <h2>Other settings</h2><a href="/acme/unrelated">unrelated</a>
                </main>
            """)
            output = StringIO()
            with patch.object(page, "goto"), patch.object(page, "reload"), patch(
                "packages_inheritance._wait_for_sign_in"
            ), redirect_stdout(output):
                _ensure_actions_repository_access(page, "acme", "image", "source", False)
            self.assertIn("Actions access is already configured for acme/other-repo", output.getvalue())
            self.assertNotIn("acme/source", output.getvalue())
            self.assertNotIn("acme/unrelated", output.getvalue())
            self.assertIsNone(page.get_by_role("button", name="Add Repository").get_attribute("data-clicked"))
        finally:
            page.close()

    def test_repository_source_does_not_count_as_actions_access(self):
        page = self.browser.new_page()
        try:
            page.set_content("""
                <main><h2>Repository source</h2><a href="/acme/source">source</a>
                <section><h2>Manage Actions access</h2>
                <button>Add Repository</button></section>
                <h2>Other settings</h2><a href="/acme/other">other</a></main>
            """)
            output = StringIO()
            with patch.object(page, "goto"), patch(
                "packages_inheritance._wait_for_sign_in"
            ), redirect_stdout(output):
                _ensure_actions_repository_access(page, "acme", "image", "source", True)
            self.assertIn("Would add acme/source to Actions access with Admin", output.getvalue())
        finally:
            page.close()

    def test_finds_summary_button_in_main_container(self):
        page = self.browser.new_page()
        try:
            page.set_content(
                "<main><h2>Manage Actions access</h2>"
                "<details><summary>Add Repository</summary></details></main>"
            )
            panel = _actions_access_panel(page)
            self.assertEqual(panel.locator("summary").inner_text(), "Add Repository")
        finally:
            page.close()

    def test_waits_for_delayed_add_button(self):
        page = self.browser.new_page()
        try:
            page.set_content(
                "<section><h2>Manage Actions access</h2></section>"
                "<script>setTimeout(() => document.querySelector('section').insertAdjacentHTML("
                "'beforeend', '<button>Add Repository</button>'), 100)</script>"
            )
            panel = _actions_access_panel(page)
            self.assertEqual(panel.get_by_role("button", name="Add Repository").count(), 1)
        finally:
            page.close()

    def test_apply_clicks_summary_add_control(self):
        page = self.browser.new_page()
        try:
            page.set_content(
                "<section><h2>Manage Actions access</h2>"
                "<details><summary>Add Repository</summary></details></section>"
            )
            with patch.object(page, "goto"), patch("packages_inheritance._wait_for_sign_in"):
                with self.assertRaisesRegex(RuntimeError, "Add repository dialog"):
                    _ensure_actions_repository_access(page, "acme", "image", "api", False)
            self.assertIsNotNone(page.locator("details").get_attribute("open"))
        finally:
            page.close()

    def test_apply_waits_selects_checkbox_and_sets_admin_after_add(self):
        page = self.browser.new_page()
        try:
            page.set_content("""
                <section><h2>Manage Actions access</h2>
                <button onclick="document.querySelector('[role=dialog]').hidden = false">Add Repository</button>
                <table id="access"></table></section>
                <div role="dialog" hidden><input type="search" id="search">
                <div id="results"></div>
                <button id="submit" disabled>Add repositories</button></div>
                <script>
                document.querySelector('#search').addEventListener('input', event => {
                  if (event.target.value === 'gcp-app-symsearch') setTimeout(() => {
                    document.querySelector('#results').innerHTML =
                      '<label><input type="checkbox">gcp-app-symsearch</label>';
                    document.querySelector('#results input').onchange = event => {
                      document.querySelector('#submit').disabled = !event.target.checked;
                    };
                  }, 150);
                });
                document.querySelector('#submit').onclick = () => {
                  document.querySelector('[role=dialog]').hidden = true;
                  setTimeout(() => document.querySelector('#access').innerHTML =
                    '<tr><td><a href="/SymriseAG/gcp-app-symsearch">gcp-app-symsearch</a></td>' +
                    '<td><select><option>Read</option><option>Admin</option></select></td></tr>', 150);
                };
                </script>
            """)
            output = StringIO()
            with patch.object(page, "goto"), patch.object(page, "reload"), patch(
                "packages_inheritance._wait_for_sign_in"
            ), redirect_stdout(output):
                _ensure_actions_repository_access(
                    page, "SymriseAG", "symsearch-backend", "gcp-app-symsearch", False
                )
            self.assertEqual(page.locator("#search").input_value(), "gcp-app-symsearch")
            self.assertEqual(page.locator("#access select").input_value(), "Admin")
            self.assertIn("Added SymriseAG/gcp-app-symsearch", output.getvalue())
        finally:
            page.close()

    def test_apply_reports_partial_change_when_role_control_is_missing(self):
        page = self.browser.new_page()
        try:
            page.set_content("""
                <section><h2>Manage Actions access</h2>
                <button onclick="document.querySelector('[role=dialog]').hidden = false">Add Repository</button>
                <table id="access"></table></section>
                <div role="dialog" hidden><input type="text">
                <label><input type="checkbox">api</label>
                <button onclick="document.querySelector('#access').innerHTML =
                '<tr><td><a href=/acme/api>api</a></td><td>Read</td></tr>'">Add repositories</button></div>
            """)
            with patch.object(page, "goto"), patch("packages_inheritance._wait_for_sign_in"):
                with self.assertRaisesRegex(RuntimeError, "Add was submitted.*Admin access could not be confirmed"):
                    _ensure_actions_repository_access(page, "acme", "image", "api", False)
            self.assertTrue(page.get_by_role("checkbox", name="api").is_checked())
            self.assertEqual(page.locator("#access tr").count(), 1)
        finally:
            page.close()


class PackageActionTests(unittest.TestCase):
    def test_run_uses_package_name_not_repository_scoped_html_url(self):
        packages = [
            {
                "name": "myembassy-strapi",
                "html_url": "https://github.com/SymriseAG/harbour-app-myembassy/pkgs/container/myembassy-strapi",
                "repository": {"full_name": "SymriseAG/harbour-app-myembassy"},
            },
            {"repository": {"full_name": "SymriseAG/harbour-app-myembassy"}},
        ]
        playwright = MagicMock()
        context = playwright.chromium.launch_persistent_context.return_value
        page = context.pages[0]
        errors = StringIO()
        with TemporaryDirectory() as profile_dir, patch(
            "packages_inheritance.list_container_packages", return_value=packages
        ), patch("playwright.sync_api.sync_playwright") as sync_playwright, patch(
            "packages_inheritance._prepare_browser_session"
        ), patch("packages_inheritance.process_package") as process, redirect_stderr(errors):
            sync_playwright.return_value.__enter__.return_value = playwright
            configuration = Configuration("SymriseAG", Path(profile_dir), True, "token")
            result = run(configuration)

        self.assertEqual(result, 1)
        process.assert_called_once_with(page, configuration, "myembassy-strapi", "harbour-app-myembassy")
        self.assertIn("Skipped <unnamed>", errors.getvalue())
        context.close.assert_called_once()

    def test_settings_url_uses_organization_and_package_name(self):
        page = MagicMock()
        with patch("packages_inheritance._wait_for_sign_in"), patch(
            "packages_inheritance._actions_access_panel"
        ), patch(
            "packages_inheritance._actions_access_repositories", return_value=[]
        ), redirect_stdout(StringIO()):
            _ensure_actions_repository_access(
                page, "SymriseAG", "myembassy-strapi", "harbour-app-myembassy", True
            )

        page.goto.assert_called_once_with(
            "https://github.com/orgs/SymriseAG/packages/container/myembassy-strapi/settings",
            wait_until="domcontentloaded",
        )

    def test_settings_url_encodes_package_name(self):
        page = MagicMock()
        with patch("packages_inheritance._wait_for_sign_in"), patch(
            "packages_inheritance._actions_access_panel"
        ), patch(
            "packages_inheritance._actions_access_repositories", return_value=[]
        ), redirect_stdout(StringIO()):
            _ensure_actions_repository_access(page, "acme", "group/image", "api", True)

        page.goto.assert_called_once_with(
            "https://github.com/orgs/acme/packages/container/group%2Fimage/settings",
            wait_until="domcontentloaded",
        )

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
            _ensure_actions_repository_access(page, "acme", "frontend", "api", True)

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
            "packages_inheritance._actions_access_repositories", return_value=["other"]
        ), redirect_stdout(output):
            _ensure_actions_repository_access(page, "acme", "frontend", "api", True)

        self.assertIn(f"Unchanged {package_url}/settings", output.getvalue())
        self.assertIn("Actions access is already configured for acme/other", output.getvalue())
        self.assertIn("existing access is not changed", output.getvalue())

    def test_dry_run_inspects_actions_access_without_mutating(self):
        configuration = Configuration("acme", Path("/tmp/profile"), True, "test-token")

        with patch("packages_inheritance._ensure_actions_repository_access") as ensure_access:
            process_package(
                None,
                configuration,
                "api",
                "api",
            )

        ensure_access.assert_called_once_with(
            None,
            "acme",
            "api",
            "api",
            True,
        )

    def test_apply_inspects_actions_access(self):
        configuration = Configuration("acme", Path("/tmp/profile"), False, "test-token")

        with patch("packages_inheritance._ensure_actions_repository_access") as ensure_access:
            process_package(
                None,
                configuration,
                "api",
                "api",
            )

        ensure_access.assert_called_once_with(
            None,
            "acme",
            "api",
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
