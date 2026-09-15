"""Real restaurant workflow on the disposable CI site; no external printers or payments."""

import os

import frappe
from frappe.utils import getdate, now_datetime

from ury.ury.api.minimal.business_setup import submit_configure_data
from ury.ury.api.minimal.setup_organization import get_setup_defaults, submit_setup
from ury.ury.api.ury_print import qz_print_update
from ury.ury.doctype.ury_order.ury_order import (
	cancel_order,
	make_invoice,
	release_merge_cluster_tables,
	sync_order,
)


def run():
	if not os.environ.get("CI") or frappe.local.site != "test_ury":
		raise RuntimeError("This smoke test may only run on the disposable test_ury CI site")
	if frappe.db.count("Company"):
		raise RuntimeError("The smoke test requires a fresh installation without companies")

	frappe.set_user("Administrator")
	assert "Europe/Istanbul" in get_setup_defaults()["timezones"]
	company = "URY V16 Test"
	cashier = "cashier@example.invalid"
	year = getdate().year
	submit_setup(
		{
			"company_name": company,
			"company_abbr": "UVT",
			"country": "India",
			"currency": "INR",
			"language": "English",
			"lang": "en",
			"timezone": "Asia/Kolkata",
			"time_zone": "Asia/Kolkata",
			"fy_start_date": f"{year}-01-01",
			"chart_of_accounts": "Standard",
			"setup_ury_demo": 0,
		}
	)
	assert frappe.db.exists("Company", company), "Organization setup did not create the company"
	print("PASS organization setup", flush=True)

	customer = frappe.get_doc(
		{
			"doctype": "Customer",
			"customer_name": "V16 Test Customer",
			"customer_type": "Individual",
			"customer_group": "Individual",
			"territory": "All Territories",
			"mobile_number": "9999999999",
		}
	).insert()
	cash_account = frappe.db.get_value(
		"Account", {"company": company, "account_type": "Cash", "is_group": 0}, "name"
	)
	assert cash_account, "Company setup must create a cash account"
	cash = frappe.get_doc("Mode of Payment", "Cash")
	company_account = next((row for row in cash.accounts if row.company == company), None)
	if company_account:
		company_account.default_account = cash_account
	else:
		cash.append("accounts", {"company": company, "default_account": cash_account})
	cash.save()

	configured = submit_configure_data(
		{
			"branch": {"branchName": "V16 Branch", "invoicePrefix": "V16-.YYYY.-"},
			"rooms": [{"name": "V16 Dining", "type": "AC"}],
			"tables": [{"name": "V16 Table", "room": "V16 Dining", "seats": 4}],
			"menuItems": [{"name": "V16 Coffee", "price": 100, "course": "Drinks"}],
			"paymentMethods": [{"name": "Cash"}],
			"users": [{"email": cashier, "name": "V16 Cashier", "role": "URY Cashier"}],
		}
	)
	assert configured["status"] == "success", configured
	results = configured["results"]
	assert not results.get("pos_profile_error"), results
	for key in ("restaurant", "branch", "pos_profile", "production_unit", "menu"):
		assert results.get(key), (key, results)
	profile = results["pos_profile"]
	assert frappe.db.exists("Item Price", {"item_code": "V16 Coffee"})
	print("PASS restaurant, menu, table, cashier and POS profile setup", flush=True)

	frappe.set_user(cashier)
	opening = frappe.get_doc(
		{
			"doctype": "POS Opening Entry",
			"period_start_date": now_datetime(),
			"posting_date": getdate(),
			"company": company,
			"pos_profile": profile,
			"user": cashier,
			"restaurant": results["restaurant"],
			"branch": results["branch"],
			"balance_details": [{"mode_of_payment": "Cash", "opening_amount": 0}],
		}
	).insert()
	opening.submit()
	assert opening.docstatus == 1
	print("PASS cashier opening", flush=True)

	def place_order():
		order = sync_order(
			items=[{"item": "V16 Coffee", "item_name": "V16 Coffee", "qty": 2}],
			cashier=cashier,
			owner=cashier,
			mode_of_payment="Cash",
			customer=customer.name,
			no_of_pax=2,
			last_invoice=None,
			waiter=cashier,
			pos_profile=profile,
			table="V16 Table",
			order_type="Dine In",
			room="V16 Dining",
		)
		assert order.get("name"), order
		assert frappe.db.exists("URY KOT", {"invoice": order["name"], "docstatus": 1}), "KOT missing"
		assert frappe.db.get_value("URY Table", "V16 Table", "occupied") == 1
		return frappe.get_doc("POS Invoice", order["name"])

	invoice = place_order()
	assert invoice.grand_total == 200, invoice.grand_total
	print("PASS table order, price calculation and submitted kitchen ticket", flush=True)

	frappe.db.savepoint("before_table_release")
	release_merge_cluster_tables("V16 Table")
	assert frappe.db.get_value("URY Table", "V16 Table", "occupied") == 0
	frappe.db.rollback(save_point="before_table_release")
	assert frappe.db.get_value("URY Table", "V16 Table", "occupied") == 1
	print("PASS table release participates in transaction rollback", flush=True)

	assert qz_print_update(invoice.name)["status"] == "Success"
	make_invoice(
		customer=customer.name,
		payments=[{"mode_of_payment": "Cash", "amount": 200}],
		cashier=cashier,
		owner=cashier,
		pos_profile=profile,
		table="V16 Table",
		invoice=invoice.name,
	)
	invoice.reload()
	assert invoice.docstatus == 1 and invoice.paid_amount == 200
	assert invoice.restaurant == results["restaurant"]
	assert frappe.db.get_value("URY Table", "V16 Table", "occupied") == 0
	print("PASS dine-in payment, submitted invoice and table release", flush=True)

	cancelled = place_order()
	cancel_order(cancelled.name, "CI cancellation")
	cancelled.reload()
	assert cancelled.status == "Cancelled"
	assert cancelled.docstatus == 2
	assert frappe.db.get_value("URY Table", "V16 Table", "occupied") == 0
	print("PASS draft order cancellation", flush=True)

	from erpnext.accounts.doctype.pos_closing_entry.pos_closing_entry import make_closing_entry_from_opening

	closing = make_closing_entry_from_opening(opening)
	for payment in closing.payment_reconciliation:
		payment.closing_amount = payment.expected_amount
	closing.insert()
	closing.submit()
	opening.reload()
	assert closing.docstatus == 1 and opening.status == "Closed"
	frappe.db.commit()
	print("PASS cashier closing", flush=True)
	return {"status": "passed", "invoice": invoice.name, "opening": opening.name, "closing": closing.name}
