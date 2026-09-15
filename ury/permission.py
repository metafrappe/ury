import frappe


def check_app_permission():
	if frappe.session.user == "Guest":
		return False
	if frappe.session.user == "Administrator":
		return True
	return bool(
		{"System Manager", "URY Admin", "URY Manager", "URY Captain", "URY Cashier"}.intersection(
			frappe.get_roles()
		)
	)
