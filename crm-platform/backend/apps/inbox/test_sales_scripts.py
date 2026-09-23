from django.contrib.auth import get_user_model
from django.test import SimpleTestCase
from rest_framework.test import APIRequestFactory, force_authenticate
from .sales_scripts import SalesScripts, script_library

class SalesScriptsTests(SimpleTestCase):
    def response(self, user=None, method="get"):
        request = getattr(APIRequestFactory(), method)("/api/inbox/sales-scripts/")
        if user is not None:
            force_authenticate(request, user=user)
        return SalesScripts.as_view()(request)

    def user(self, **kwargs):
        return get_user_model()(username="script-test", account_kind="staff", is_active=True, extra_permissions=["inbox.view"], **kwargs)

    def test_permission_and_read_only(self):
        self.assertIn(self.response().status_code, (401, 403))
        inactive = self.user(); inactive.is_active = False
        self.assertEqual(self.response(inactive).status_code, 403)
        client = self.user(); client.account_kind = "client"; client.is_superuser = True
        self.assertEqual(self.response(client).status_code, 403)
        denied = self.user(); denied.extra_permissions = []
        self.assertEqual(self.response(denied).status_code, 403)
        self.assertEqual(self.response(self.user()).status_code, 200)
        self.assertEqual(self.response(self.user(), "post").status_code, 405)

    def test_unique_canonical_scripts_and_separate_internal_text(self):
        data = script_library()
        self.assertEqual(len(data["scripts"]), 4)
        self.assertEqual(len({s["id"] for s in data["scripts"]}), 4)
        self.assertNotIn("sources", data)
        self.assertNotIn("source_registry_rows", data["scripts"][0])
        for script in data["scripts"]:
            for step in script["steps"]:
                self.assertEqual(set(step["customer_text"]), {"uk", "ru"})
                self.assertEqual(set(step["manager_only"]), {"uk", "ru"})
                self.assertNotIn(step["manager_only"]["uk"], step["customer_text"]["uk"])
        self.assertIn("no-store", self.response(self.user())["Cache-Control"])
