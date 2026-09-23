"""Static checks for root-only Admin credential management."""

from pathlib import Path
import unittest


ROOT = Path(__file__).resolve().parent
WEB_FILE = ROOT / "app_web.py"
if not WEB_FILE.exists():
    WEB_FILE = ROOT / "app.py"
WEB_SOURCE = WEB_FILE.read_text(encoding="utf-8")


class AdminManagementTests(unittest.TestCase):
    def test_only_root_account_can_open_the_editor(self):
        self.assertIn('if st.session_state["admin_user"] == "administrator":', WEB_SOURCE)
        self.assertIn('with st.form("edit_admin_form"):', WEB_SOURCE)

    def test_root_username_is_protected_but_password_can_be_updated(self):
        self.assertIn('is_root_admin = selected_admin["username"] == "administrator"', WEB_SOURCE)
        self.assertIn('disabled=is_root_admin', WEB_SOURCE)
        self.assertIn('updates["password"] = clean_password', WEB_SOURCE)

    def test_username_update_checks_for_duplicates_and_uses_existing_username(self):
        self.assertIn('and adm["username"] == clean_username', WEB_SOURCE)
        self.assertIn('.update(updates).eq("username", selected_admin["username"])', WEB_SOURCE)
        self.assertIn('admin_options = {adm["username"]: adm for adm in admins}', WEB_SOURCE)
        self.assertNotIn('selected_admin["id"]', WEB_SOURCE)


if __name__ == "__main__":
    unittest.main(verbosity=2)
