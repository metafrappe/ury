# URY on Frappe / ERPNext v16

This is the `version-16` branch of [metafrappe/ury](https://github.com/metafrappe/ury),
forked directly from [ury-erp/ury](https://github.com/ury-erp/ury).
The upstream base is commit `58e1cb8dcccc7bb093d8b9f7c843e0dc2432474d`.
The URY application version at that base is `3.0.0-beta.1`; this branch targets
stable Frappe v16 and does not change URY's upstream release designation.

## Requirements

- Python 3.14 or newer and Node.js 24 or newer.
- Frappe, ERPNext and HRMS on their `version-16` branches (major version 16).
- HRMS is required for URY's employee and payroll features.
- Keep the Frappe applications outside pip requirements; Bench manages them.

## Add the app to a Bench

From an existing Frappe v16 bench:

```sh
bench get-app --branch version-16 https://github.com/frappe/erpnext.git
bench get-app --branch version-16 https://github.com/frappe/hrms.git
bench get-app --branch version-16 https://github.com/metafrappe/ury.git
```

Skip `get-app` for apps already present on that bench. Use this fork's
`version-16` branch for the v16 changes; the fork's `develop` branch tracks the
original upstream code.

## Install on a site

Start with a dedicated test site. URY adds restaurant fields to ERPNext and
uses its own setup wizard.

```sh
bench new-site ury-test.localhost
bench --site ury-test.localhost install-app erpnext
bench --site ury-test.localhost install-app hrms
bench --site ury-test.localhost install-app ury
bench build --app ury
bench --site ury-test.localhost migrate
```

Open `/ury` and complete the organization and restaurant setup. `/pos` is the
cashier interface; `/mosaic` is the kitchen display. Frappe Desk uses `/desk`.

## Frappe Press

Add `metafrappe/ury`, branch `version-16`, to the existing v16 bench group and
deploy that group. When creating a site, select URY together with ERPNext and
HRMS. Adding source code to a bench group does not install the app on every site.

## Verification

Run the focused regression suite on a disposable site:

```sh
bench --site ury-test.localhost set-config allow_tests true
bench --site ury-test.localhost run-tests --module ury.tests.test_v16_compatibility
```

The [v16 CI workflow](https://github.com/metafrappe/ury/actions/workflows/v16-compatibility.yml)
installs Frappe 16.33.1, ERPNext 16.34.2 and HRMS 16.18.1, checks the exact
revisions, installs and migrates URY, builds all five frontends, runs the regression
tests and exercises a cash sale and cancellation on a disposable restaurant.
The smoke test is restricted to the `test_ury` CI site and must not run on customer sites.

Before using a new revision, also verify fresh installation, migration, all five
frontend builds, organization setup, restaurant setup, cashier opening, table
orders, KOT creation, payment, cancellation and closing on the intended Frappe,
ERPNext and HRMS versions. Configure and verify actual printers and payment
terminals separately for the restaurant's hardware.
