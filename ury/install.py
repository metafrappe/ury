import click
import frappe

from ury.setup_customizations import after_install as setup


def after_install():
    print("Setting up URY...")
    setup()
    configure_fresh_site_pos_mode()
    click.secho("Thank you for installing URY App!", fg="green")


def configure_fresh_site_pos_mode():
    """Use URY's POS Invoice workflow before a new site's organization setup.

    ERPNext v16 defaults to Sales Invoice mode. Never switch an established
    site's accounting workflow just because URY was installed there.
    """
    if frappe.db.get_single_value("System Settings", "setup_complete") or frappe.db.exists("Company"):
        return

    settings = frappe.get_doc("POS Settings")
    if settings.invoice_type != "POS Invoice":
        settings.invoice_type = "POS Invoice"
        settings.save()
