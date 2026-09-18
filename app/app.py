import io
import os
from datetime import datetime
from functools import wraps

from flask import (
    Flask, render_template, request, redirect, url_for, session, send_file, flash
)

from pge_parser import parse_pge_bill, PGEParseError
from leviton_parser import parse_leviton_export, LevitonParseError
from calculator import calculate_charges, group_by_tenant
from report_pdf import build_report_pdf, append_bill_snapshot
from email_templates import build_email_drafts
import storage

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

APP_PASSWORD = os.environ.get("APP_PASSWORD", "")  # if unset, no password gate


def login_required(view):
    @wraps(view)
    def wrapped(*args, **kwargs):
        if APP_PASSWORD and not session.get("authed"):
            return redirect(url_for("login", next=request.path))
        return view(*args, **kwargs)
    return wrapped


@app.route("/login", methods=["GET", "POST"])
def login():
    if not APP_PASSWORD:
        return redirect(url_for("index"))
    error = None
    if request.method == "POST":
        if request.form.get("password") == APP_PASSWORD:
            session["authed"] = True
            return redirect(request.args.get("next") or url_for("index"))
        error = "Incorrect password."
    return render_template("login.html", error=error)


@app.route("/logout")
def logout():
    session.pop("authed", None)
    return redirect(url_for("login"))


def _parse_mdy(value):
    try:
        return datetime.strptime(value, "%m/%d/%Y")
    except (TypeError, ValueError):
        return None


def _past_usage_dates(runs):
    """Prior PG&E billing periods (usage dates), most recent first, so it's
    easy to see at a glance which periods have already been run."""
    periods = []
    for r in runs:
        bp = r.get("billing_period") or {}
        start, end = bp.get("start"), bp.get("end")
        if not start or not end:
            continue
        periods.append({"start": start, "end": end, "_sort": _parse_mdy(start)})
    periods.sort(key=lambda p: p["_sort"] or datetime.min, reverse=True)
    return periods


def _sort_runs_by_billing_period(runs):
    """Past runs, ordered by billing period start date (most recent on top)
    rather than upload/created time, so the list reads in usage-period
    order. Runs with no billing period yet (still mid-mapping) sink to the
    bottom rather than being dropped."""
    def key(r):
        bp = r.get("billing_period") or {}
        return _parse_mdy(bp.get("start")) or datetime.min
    return sorted(runs, key=key, reverse=True)


@app.route("/")
@login_required
def index():
    runs = storage.list_runs()
    return render_template(
        "index.html", runs=_sort_runs_by_billing_period(runs),
        has_sop=storage.load_sop_pdf() is not None,
        sop_uploaded_at=storage.sop_uploaded_at(),
        past_usage_dates=_past_usage_dates(runs),
    )


@app.route("/runs/<run_id>/delete", methods=["POST"])
@login_required
def delete_run(run_id):
    storage.delete_run(run_id)
    flash("Run deleted (moved to an archive folder — let Mark know if it needs to come back).", "success")
    return redirect(url_for("index"))


@app.route("/sop")
@login_required
def sop_view():
    if storage.load_sop_pdf() is None:
        flash("No SOP uploaded yet.", "error")
        return redirect(url_for("index"))
    return render_template("sop_view.html")


@app.route("/sop.pdf")
@login_required
def sop_pdf():
    data = storage.load_sop_pdf()
    if data is None:
        flash("No SOP uploaded yet.", "error")
        return redirect(url_for("index"))
    return send_file(
        io.BytesIO(data),
        mimetype="application/pdf",
        as_attachment=False,
        download_name="Fulton_PGE_Reimbursement_SOP.pdf",
    )


@app.route("/sop.pdf/download")
@login_required
def sop_pdf_download():
    data = storage.load_sop_pdf()
    if data is None:
        flash("No SOP uploaded yet.", "error")
        return redirect(url_for("index"))
    return send_file(
        io.BytesIO(data),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="Fulton_PGE_Reimbursement_SOP.pdf",
    )


@app.route("/sop/upload", methods=["POST"])
@login_required
def upload_sop():
    sop_file = request.files.get("sop_file")
    if not sop_file or sop_file.filename == "":
        flash("Please choose a PDF file.", "error")
        return redirect(url_for("index"))
    storage.save_sop_pdf(sop_file.read())
    flash("SOP uploaded.", "success")
    return redirect(url_for("index"))


@app.route("/upload", methods=["POST"])
@login_required
def upload():
    leviton_file = request.files.get("leviton_file")
    pge_file = request.files.get("pge_file")

    if not leviton_file or leviton_file.filename == "":
        flash("Please choose a Leviton consumption export.", "error")
        return redirect(url_for("index"))
    if not pge_file or pge_file.filename == "":
        flash("Please choose the PG&E bill PDF.", "error")
        return redirect(url_for("index"))

    try:
        units = parse_leviton_export(leviton_file.stream, leviton_file.filename)
    except LevitonParseError as e:
        flash(f"Leviton file error: {e}", "error")
        return redirect(url_for("index"))

    pge_bytes = pge_file.read()
    try:
        pge = parse_pge_bill(io.BytesIO(pge_bytes))
    except PGEParseError as e:
        flash(f"PG&E PDF error: {e}", "error")
        return redirect(url_for("index"))

    run_id = storage.new_run_id()
    run = {
        "units_raw": units,
        "pge": pge,
        "billing_period": {"start": pge.get("billing_start"), "end": pge.get("billing_end")},
        "mapping": {},
    }
    storage.save_run(run_id, run)
    storage.save_bill_pdf(run_id, pge_bytes)
    return redirect(url_for("mapping", run_id=run_id))
