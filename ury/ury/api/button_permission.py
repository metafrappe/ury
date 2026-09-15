import frappe


@frappe.whitelist()
def cancel_check():
    return bool(frappe.has_permission("POS Invoice", "cancel"))
