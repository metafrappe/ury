"""Regressions for the Frappe APIs changed in version 16."""

from unittest.mock import MagicMock, patch

import frappe
from frappe.tests import UnitTestCase

from ury import install, permission
from ury.ury.api.button_permission import cancel_check
from ury.ury.api.minimal import setup_organization
from ury.ury.doctype.ury_order import ury_order
from ury.ury.doctype.ury_order.ury_order import release_merge_cluster_tables


class TestV16Compatibility(UnitTestCase):
	def test_setup_defaults_use_configured_country_and_iana_timezones(self):
		with (
			patch.object(frappe, "session", frappe._dict(user="Administrator")),
			patch.object(frappe.db, "get_single_value", return_value="India"),
			patch.object(setup_organization, "load_languages", return_value=[]),
		):
			defaults = setup_organization.get_setup_defaults()

		self.assertEqual(defaults["detected_country"], "India")
		self.assertIn("India", defaults["countries"])
		self.assertIn("Europe/Istanbul", defaults["timezones"])
		self.assertTrue(any(row["value"] == "INR" for row in defaults["currencies"]))

	def test_cancel_permission_uses_current_public_api(self):
		for allowed in (False, True):
			with (
				self.subTest(allowed=allowed),
				patch.object(frappe, "has_permission", autospec=True, return_value=allowed),
			):
				self.assertIs(cancel_check(), allowed)

	def test_apps_screen_checks_roles_instead_of_username(self):
		for roles, allowed in [
			(["System Manager"], True),
			(["URY Manager"], True),
			(["URY Cashier"], True),
			(["All"], False),
		]:
			with (
				self.subTest(roles=roles),
				patch.object(frappe, "session", frappe._dict(user="cashier@example.com")),
				patch.object(frappe, "get_roles", return_value=roles),
			):
				self.assertIs(permission.check_app_permission(), allowed)

		with patch.object(frappe, "session", frappe._dict(user="Guest")):
			self.assertIs(permission.check_app_permission(), False)

	def test_installation_error_is_reported_to_bench(self):
		with patch.object(install, "setup", side_effect=RuntimeError("custom fields failed")):
			with self.assertRaisesRegex(RuntimeError, "custom fields failed"):
				install.after_install()

	def test_fresh_installation_selects_pos_invoice_mode(self):
		settings = MagicMock(invoice_type="Sales Invoice")
		with (
			patch.object(frappe.db, "get_single_value", return_value=0),
			patch.object(frappe.db, "exists", return_value=False),
			patch.object(frappe, "get_doc", return_value=settings),
		):
			install.configure_fresh_site_pos_mode()
		self.assertEqual(settings.invoice_type, "POS Invoice")
		settings.save.assert_called_once_with()

	def test_installation_preserves_existing_sites_pos_mode(self):
		for setup_complete, company_exists in [(1, False), (0, True)]:
			with (
				self.subTest(setup_complete=setup_complete, company_exists=company_exists),
				patch.object(frappe.db, "get_single_value", return_value=setup_complete),
				patch.object(frappe.db, "exists", return_value=company_exists),
				patch.object(frappe, "get_doc") as get_doc,
			):
				install.configure_fresh_site_pos_mode()
			get_doc.assert_not_called()

	def test_table_release_does_not_commit_the_callers_transaction(self):
		# POS Invoice cancellation calls this helper from a document hook.
		# Frappe v16 forbids committing there; a rollback must still work.
		with (
			patch.object(frappe.db, "set_value"),
			patch.object(frappe.db, "commit", side_effect=AssertionError("Premature commit")),
		):
			release_merge_cluster_tables(["_Test V16 Table"])

	def test_dine_in_payment_keeps_restaurant_link_scalar(self):
		invoice = MagicMock()
		invoice.custom_merged_pos_invoice = None
		invoice.restaurant_table = "Table 1"
		with (
			patch.object(frappe, "get_value", return_value="Dine In"),
			patch.object(ury_order, "get_order_invoice", return_value=invoice),
			patch.object(
				ury_order,
				"get_restaurant_and_menu_name",
				return_value=("Branch 1", "Menu 1", "Restaurant 1"),
			),
			patch.object(ury_order, "_free_tables_if_no_open_invoices"),
		):
			ury_order.make_invoice(
				customer="Customer 1",
				payments=[{"mode_of_payment": "Cash", "amount": 100}],
				cashier="cashier@example.com",
				owner="cashier@example.com",
				pos_profile="Profile 1",
				table="Table 1",
				invoice="Invoice 1",
			)
		self.assertEqual(invoice.restaurant, "Restaurant 1")
		invoice.submit.assert_called_once()

	def test_restaurant_item_search_accepts_branch_menu_restaurant_result(self):
		with (
			patch.object(
				ury_order,
				"get_restaurant_and_menu_name",
				return_value=("Branch 1", "Menu 1", "Restaurant 1"),
			),
			patch.object(frappe.db, "get_all", return_value=[frappe._dict(item="Coffee")]),
			patch.object(ury_order, "item_query", autospec=True, return_value=[["Coffee"]]),
		):
			items = ury_order.item_query_restaurant(filters={"table": "Table 1"})
		self.assertEqual(items, [["Coffee"]])

	def test_draft_order_cancellation_does_not_use_submitted_document_workflow(self):
		invoice = MagicMock(docstatus=0, restaurant_table="Table 1")
		invoice.cancel.side_effect = AssertionError("Frappe cannot cancel a draft document")
		with (
			patch.object(frappe, "session", frappe._dict(user="Administrator")),
			patch.object(frappe, "get_doc", return_value=invoice),
			patch.object(frappe, "has_permission", return_value=True),
			patch.object(frappe.db, "sql"),
			patch.object(frappe.db, "set_value") as set_value,
			patch.object(ury_order, "release_merge_cluster_tables"),
			patch.object(ury_order, "cancel_kot"),
		):
			ury_order.cancel_order("Invoice 1", "Customer changed their order")
		set_value.assert_any_call("POS Invoice", "Invoice 1", "status", "Cancelled")
