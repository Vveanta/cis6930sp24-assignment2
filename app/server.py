import csv
import io
import logging
import os
import sqlite3
import uuid
from datetime import date

import pandas as pd
import urllib.error
import urllib.parse
from flask import Blueprint, flash, jsonify, redirect, render_template, request, send_file, send_from_directory, url_for
from werkzeug.utils import secure_filename

from .forms import FeedbackForm, UploadForm
from .utils import (
    augment_data,
    create_db,
    create_feedback_tables,
    extract_incidents,
    fetch_incidents,
    populate_db,
)
from .utils.geocoding import GeocodingQuotaError
from .utils.norman_daily_reports import (
    is_allowed_report_date,
    iter_daily_incident_summary_urls,
    parse_iso_date,
    selectable_date_bounds,
)
from .utils.pdf_export import build_summary_pdf_bytes
from .utils.stats_helper import compute_anomaly_alerts, summary_counts

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)
main = Blueprint("main", __name__)


def _project_root() -> str:
    return os.path.abspath(os.path.join(os.path.dirname(__file__), ".."))


def _resources_dir() -> str:
    return os.path.join(_project_root(), "app", "resources")


def resolve_augmented_csv(requested: str | None) -> str:
    """Resolve CSV path safely under app/resources."""
    res = os.path.abspath(_resources_dir())
    default = os.path.join(res, "augmented_data.csv")
    if not requested:
        return default
    cand = os.path.abspath(os.path.join(_project_root(), requested))
    if not cand.startswith(res + os.sep) and cand != res:
        return default
    return cand if os.path.isfile(cand) else default


def use_async_worker() -> bool:
    return bool(os.environ.get("REDIS_URL"))


def _try_extract_and_populate(pdf_path: str, db_path: str) -> tuple[bool, str | None]:
    try:
        incidents = extract_incidents(pdf_path)
        populate_db(db_path, incidents)
        return True, None
    except ValueError as e:
        msg = str(e)
        logger.warning("Extract failed for %s: %s", pdf_path, e)
        if "No valid incidents" in msg:
            return False, "no_incidents"
        return False, "invalid_pdf"
    except Exception as e:
        logger.error("Error processing PDF %s: %s", pdf_path, e)
        return False, "invalid_pdf"


def process_pdf(pdf_filename: str, db_path: str) -> tuple[bool, str | None]:
    return _try_extract_and_populate(pdf_filename, db_path)


def process_urls(urls, db_path, success_count):
    failed_urls = []
    skipped_urls = []
    for url in urls:
        if success_count >= 3:
            skipped_urls.append(url)
            continue
        pdf_filename = fetch_pdf(url)
        if pdf_filename is None:
            logger.warning("Skipping URL: %s due to fetch failure.", url)
            failed_urls.append(url)
            continue

        ok, reason = _try_extract_and_populate(pdf_filename, db_path)
        if ok:
            success_count += 1
        else:
            if reason == "no_incidents":
                failed_urls.append(f"(no incidents) {url}")
            else:
                failed_urls.append(url)

    return failed_urls, skipped_urls, success_count


def process_csv(file_path, db_path, success_count):
    urls = pd.read_csv(file_path, header=None)
    return process_urls(urls[0], db_path, success_count)


def fetch_pdf(url: str) -> str | None:
    base = url.rstrip("/").split("/")[-1]
    if not base.endswith(".pdf"):
        base = f"{base}.pdf"
    local_filename = os.path.join("/tmp", secure_filename(base) or f"fetch_{uuid.uuid4().hex}.pdf")
    try:
        fetch_incidents(url, local_filename)
    except urllib.error.HTTPError as e:
        logger.error("HTTPError: %s - %s for URL: %s", e.code, e.reason, url)
        return None
    except urllib.error.URLError as e:
        logger.error("URLError: %s for URL: %s", e.reason, url)
        return None
    return local_filename


def fetch_norman_daily_for_date(d: date, db_path: str) -> tuple[bool, str | None]:
    """Try each candidate URL until download succeeds (Norman uses varying folder months)."""
    for url in iter_daily_incident_summary_urls(d):
        logger.info("Trying Norman daily PDF: %s", url)
        path = fetch_pdf(url)
        if path is None:
            continue
        ok, reason = process_pdf(path, db_path)
        if ok:
            return True, None
        logger.warning("Downloaded PDF but parse failed: %s reason=%s", url, reason)
        return False, reason or "invalid_pdf"
    return False, "fetch_failed"


def ensure_database_exists():
    db_path = os.path.join(_project_root(), "resources", "normanpd.db")
    res = os.path.join(_project_root(), "resources")
    if not os.path.exists(res):
        os.makedirs(res)
    create_db(db_path)
    return db_path


@main.route("/", methods=["GET"])
def index():
    return render_template("index.html")


@main.route("/errors/no-incidents")
def error_no_incidents():
    return render_template("errors/no_incidents.html")


@main.route("/errors/geocoding-quota")
def error_geocoding_quota():
    return render_template("errors/geocoding_quota.html")


@main.route("/errors/invalid-pdf")
def error_invalid_pdf():
    return render_template("errors/invalid_pdf.html")


@main.route("/upload", methods=["GET", "POST"])
def upload():
    default_pdf_files = [(filename, filename) for filename in os.listdir("defaultpdfs")]
    upload_form = UploadForm()
    upload_form.default_pdfs.choices = default_pdf_files
    nd_min, nd_max = selectable_date_bounds()

    if upload_form.validate_on_submit():
        success_count = 0
        failed_urls: list[str] = []
        skipped_urls: list[str] = []
        db_path = ensure_database_exists()
        file_type = request.form["file_type"]

        if file_type == "norman_daily":
            raw = request.form.get("norman_dates", "")
            parts = [p.strip() for p in raw.split(",") if p.strip()]
            if len(parts) > 3:
                flash(
                    "You can select at most three report dates per session. For more, contact the developer.",
                    "error",
                )
                return redirect(url_for("main.upload"))
            dates: list[date] = []
            for p in parts:
                d = parse_iso_date(p)
                if d is None or not is_allowed_report_date(d):
                    flash(f"Invalid or out-of-range date: {p}", "error")
                    return redirect(url_for("main.upload"))
                dates.append(d)
            if not dates:
                flash("Select at least one daily report date.", "error")
                return redirect(url_for("main.upload"))
            for d in dates:
                ok, reason = fetch_norman_daily_for_date(d, db_path)
                if ok:
                    success_count += 1
                else:
                    failed_urls.append(f"{d.isoformat()} ({reason or 'error'})")
            if success_count == 0:
                flash("Could not load any of the selected daily reports (missing or invalid).", "error")
                return redirect(url_for("main.upload"))

        elif file_type == "url":
            urls = request.form["urls"].splitlines()
            failed_urls, skipped_urls, success_count = process_urls(urls, db_path, success_count)
        elif file_type == "default_pdf":
            selected_pdf = upload_form.default_pdfs.data
            file_path = os.path.join("defaultpdfs", selected_pdf)
            ok, reason = process_pdf(file_path, db_path)
            if not ok:
                if reason == "no_incidents":
                    return redirect(url_for("main.error_no_incidents"))
                return redirect(url_for("main.error_invalid_pdf"))
        else:
            files = request.files.getlist("file")
            for file in files:
                filename = secure_filename(file.filename)
                file_path = os.path.join("/tmp", filename)
                file.save(file_path)

                if file_type == "csv" and filename.endswith(".csv"):
                    failed, skipped, success_count = process_csv(file_path, db_path, success_count)
                    failed_urls.extend(failed)
                    skipped_urls.extend(skipped)
                elif file_type == "pdf" and filename.endswith(".pdf"):
                    if success_count >= 3:
                        skipped_urls.append(filename)
                        continue
                    ok, reason = process_pdf(file_path, db_path)
                    if ok:
                        success_count += 1
                    else:
                        failed_urls.append(filename)
                        if reason == "no_incidents":
                            return redirect(url_for("main.error_no_incidents"))
                else:
                    flash("Unsupported file type", category="error")
                    return redirect(url_for("main.upload"))

        if success_count == 0 and file_type != "norman_daily":
            flash("No incident data was loaded.", "error")
            return redirect(url_for("main.upload"))

        if use_async_worker():
            from app.job_store import store_job_payload
            from app.tasks import run_augment_job

            job_id = str(uuid.uuid4())
            with open(db_path, "rb") as f:
                db_bytes = f.read()
            from app.job_store import set_job_progress

            store_job_payload(job_id, db_bytes, failed_urls, skipped_urls)
            set_job_progress(job_id, "Queued", 1, "Waiting for worker…")
            run_augment_job.apply_async(args=[job_id], task_id=job_id)
            return redirect(url_for("main.processing", job_id=job_id))

        try:
            csv_file_path = augment_data(db_path)
        except GeocodingQuotaError:
            return redirect(url_for("main.error_geocoding_quota"))

        return redirect(
            url_for(
                "main.results",
                csv_file_path=csv_file_path,
                failed_urls=urllib.parse.quote_plus(",".join(failed_urls)),
                skipped_urls=urllib.parse.quote_plus(",".join(skipped_urls)),
            )
        )

    return render_template(
        "upload.html",
        upload_form=upload_form,
        norman_date_min=nd_min.isoformat(),
        norman_date_max=nd_max.isoformat(),
        norman_docs_url="https://www.normanok.gov/public-safety/police-department/crime-prevention-data/department-activity-reports",
    )


@main.route("/processing/<job_id>")
def processing(job_id: str):
    if not use_async_worker():
        return redirect(url_for("main.upload"))
    return render_template("processing.html", job_id=job_id)


@main.route("/api/job-status/<job_id>")
def job_status(job_id: str):
    if not use_async_worker():
        return jsonify(error="async pipeline disabled"), 400
    from celery.result import AsyncResult

    from app.celery_app import celery_app
    from app.job_store import get_job_error_code, get_job_progress

    result = AsyncResult(job_id, app=celery_app)
    state = result.state
    payload: dict = {"state": state, "stage": None, "percent": None, "detail": None}
    prog = get_job_progress(job_id)
    if prog:
        payload.update(prog)
        if "percent" in prog and prog["percent"] is not None:
            try:
                payload["percent"] = int(prog["percent"])
            except (TypeError, ValueError):
                pass
    err_meta = get_job_error_code(job_id)
    if err_meta:
        payload["error_code"] = err_meta["code"]
        payload["error_detail"] = err_meta.get("message")
    if state == "FAILURE":
        err = result.result
        payload["error"] = str(err) if err is not None else "Unknown error"
        if err_meta and err_meta.get("code") == "geocoding_quota":
            payload["error_code"] = "geocoding_quota"
    return jsonify(payload)


@main.route("/api/job-finalize/<job_id>", methods=["POST"])
def job_finalize(job_id: str):
    if not use_async_worker():
        return jsonify(error="async pipeline disabled"), 400
    from celery.result import AsyncResult

    from app.celery_app import celery_app
    from app.job_store import get_job_meta, pop_job_results_for_finalize

    result = AsyncResult(job_id, app=celery_app)
    if not result.successful():
        return jsonify(error="Job not finished successfully"), 400

    meta = get_job_meta(job_id)
    try:
        db_bytes, csv_bytes = pop_job_results_for_finalize(job_id)
    except ValueError as e:
        return jsonify(error=str(e)), 500

    os.makedirs(os.path.join(_project_root(), "resources"), exist_ok=True)
    with open(os.path.join(_project_root(), "resources", "normanpd.db"), "wb") as f:
        f.write(db_bytes)

    app_res = _resources_dir()
    os.makedirs(app_res, exist_ok=True)
    csv_rel = os.path.join("app", "resources", "augmented_data.csv")
    with open(os.path.join(_project_root(), csv_rel), "wb") as f:
        f.write(csv_bytes)

    failed_q = urllib.parse.quote_plus(",".join(meta.get("failed_urls", [])))
    skipped_q = urllib.parse.quote_plus(",".join(meta.get("skipped_urls", [])))
    next_url = url_for(
        "main.results",
        csv_file_path=csv_rel,
        failed_urls=failed_q,
        skipped_urls=skipped_q,
        _external=True,
    )
    return jsonify(redirect=next_url)


@main.route("/results")
def results():
    csv_file_path = request.args.get("csv_file_path")
    failed_urls = urllib.parse.unquote_plus(request.args.get("failed_urls", "")).split(",")
    skipped_urls = urllib.parse.unquote_plus(request.args.get("skipped_urls", "")).split(",")

    path = resolve_augmented_csv(csv_file_path)
    data = get_augmented_data(path)
    alerts = compute_anomaly_alerts(data)
    stats = summary_counts(data)

    conn = sqlite3.connect(os.path.join(_project_root(), "resources", "normanpd.db"))
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT location, latitude, longitude, COUNT(*) as count
        FROM incidents
        JOIN geocodes ON incidents.incident_location = geocodes.location
        GROUP BY location
        """
    )
    locations = cursor.fetchall()
    conn.close()
    locations_data = [
        {"location": loc[0], "latitude": loc[1], "longitude": loc[2], "count": loc[3]}
        for loc in locations
    ]

    rel_csv = os.path.relpath(path, _project_root())
    if rel_csv.startswith(".."):
        rel_csv = os.path.join("app", "resources", "augmented_data.csv")

    return render_template(
        "results.html",
        data=data,
        csv_url=rel_csv.replace("\\", "/"),
        failed_urls=failed_urls,
        skipped_urls=skipped_urls,
        locations=locations_data,
        anomaly_alerts=alerts,
        summary_stats=stats,
        norman_docs_url="https://www.normanok.gov/public-safety/police-department/crime-prevention-data/department-activity-reports",
    )


@main.route("/export/geojson")
def export_geojson():
    csv_file_path = request.args.get("csv_file_path")
    path = resolve_augmented_csv(csv_file_path)
    rows = get_augmented_data(path)
    features = []
    for i, row in enumerate(rows):
        try:
            lat = float(row.get("Latitude") or "")
            lng = float(row.get("Longitude") or "")
        except (TypeError, ValueError):
            continue
        features.append(
            {
                "type": "Feature",
                "geometry": {"type": "Point", "coordinates": [lng, lat]},
                "properties": {
                    "id": i,
                    "nature": row.get("Nature"),
                    "location": row.get("Location"),
                    "time": row.get("Incident Time"),
                },
            }
        )
    payload = {"type": "FeatureCollection", "features": features}
    return jsonify(payload)


@main.route("/export/summary.pdf")
def export_summary_pdf():
    csv_file_path = request.args.get("csv_file_path")
    path = resolve_augmented_csv(csv_file_path)
    rows = get_augmented_data(path)
    stats = summary_counts(rows)
    pdf_bytes = build_summary_pdf_bytes(stats, rows)
    return send_file(
        io.BytesIO(pdf_bytes),
        mimetype="application/pdf",
        as_attachment=True,
        download_name="norman_incident_summary.pdf",
    )


@main.route("/download/<path:filename>")
def download_file(filename):
    directory = os.path.join(main.root_path, "resources")
    logger.info("Attempting to send file from directory: %s, filename: %s", directory, filename)
    return send_from_directory(directory, filename, as_attachment=True)


@main.route("/feedback", methods=["GET", "POST"])
def feedback():
    feedback_form = FeedbackForm()
    logger.info("Entered feedback route")

    if request.method == "POST" and feedback_form.validate_on_submit():
        _fdb = os.path.join(_project_root(), "resources", "normanpd.db")
        create_feedback_tables(_fdb)
        logger.info("Handling POST request and form validation")
        user_type = feedback_form.user_type.data
        logger.info("Received user type from form: %s", user_type)
        conn = sqlite3.connect(_fdb)
        cur = conn.cursor()
        cur.execute("SELECT id FROM user_types WHERE type = ?", (user_type,))
        user_type_id = cur.fetchone()

        if user_type_id:
            feedback_data = (
                feedback_form.name.data,
                feedback_form.email.data,
                user_type_id[0],
                feedback_form.rating.data,
                feedback_form.feedback.data,
            )
            logger.info("Feedback data: %s", feedback_data)

            cur.execute(
                """
                INSERT INTO feedback (name, email, user_type_id, rating, feedback)
                VALUES (?, ?, ?, ?, ?)
                """,
                feedback_data,
            )
            conn.commit()
            cur.close()
            conn.close()
            return jsonify(status="success")
        else:
            return jsonify(status="failure", message="Invalid user type")

    return render_template("feedback.html", feedback_form=feedback_form)


@main.route("/thankyou")
def thankyou():
    return render_template("thankyou.html")


def get_augmented_data(csv_file_path: str) -> list:
    data = []
    if not os.path.isfile(csv_file_path):
        return data
    with open(csv_file_path, newline="") as csvfile:
        reader = csv.DictReader(csvfile)
        for row in reader:
            data.append(row)
    return data
