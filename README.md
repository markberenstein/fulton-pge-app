# Fulton PG&E Reimbursement App

Standalone Flask app to calculate and verify PG&E bill reimbursements for
sub-metered tenants at Fulton Place, using Leviton consumption data.

## Monthly workflow
1. Upload the Leviton consumption export (.xlsx/.csv) and the PG&E bill PDF.
2. Assign units to tenants (pre-filled from the prior month).
3. Review the dashboard (flags a variance if Leviton and PG&E totals disagree).
4. Download the PDF report.
5. Generate ready-to-copy reimbursement email drafts for Buildium.

## Environment variables
- `DATA_DIR` — where run history + settings are stored (mount a persistent volume here in production)
- `SECRET_KEY` — Flask session secret
- `APP_PASSWORD` — optional; if set, gates the whole app behind a password
