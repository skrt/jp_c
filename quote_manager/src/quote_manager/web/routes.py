"""Flask routes for the web UI."""

import os
import tempfile
from flask import Blueprint, render_template, request, redirect, url_for, flash, send_file

from quote_manager.models.base import get_session
from quote_manager.models import Project, Supplier, Quote, LineItem

bp = Blueprint("main", __name__)


@bp.route("/")
def index():
    """Project list page."""
    session = get_session()
    try:
        projects = session.query(Project).order_by(Project.created_at.desc()).all()
        project_data = []
        for p in projects:
            count = session.query(Quote).filter_by(project_id=p.id).count()
            project_data.append({"project": p, "quote_count": count})
        return render_template("projects.html", projects=project_data)
    finally:
        session.close()


@bp.route("/projects/create", methods=["GET", "POST"])
def project_create():
    """Create a new project."""
    if request.method == "POST":
        session = get_session()
        try:
            p = Project(
                name=request.form["name"],
                description=request.form.get("description"),
                gmail_query=request.form.get("gmail_query"),
                slack_channel_id=request.form.get("slack_channel_id"),
                slack_thread_ts=request.form.get("slack_thread_ts"),
            )
            session.add(p)
            session.commit()
            flash(f"案件「{p.name}」を作成しました。", "success")
            return redirect(url_for("main.project_detail", project_id=p.id))
        finally:
            session.close()

    return render_template("project_form.html")


@bp.route("/projects/<int:project_id>")
def project_detail(project_id):
    """Project detail page with quotes."""
    session = get_session()
    try:
        project = session.query(Project).get(project_id)
        if not project:
            flash("案件が見つかりません。", "error")
            return redirect(url_for("main.index"))

        quotes = session.query(Quote).filter_by(project_id=project_id).all()
        quote_data = []
        for q in quotes:
            supplier = session.query(Supplier).get(q.supplier_id)
            items = session.query(LineItem).filter_by(quote_id=q.id).all()
            quote_data.append({
                "quote": q,
                "supplier": supplier,
                "items": items,
            })

        return render_template("project_detail.html", project=project, quotes=quote_data)
    finally:
        session.close()


@bp.route("/projects/<int:project_id>/fetch", methods=["POST"])
def project_fetch(project_id):
    """Trigger email/Slack fetch for a project."""
    session = get_session()
    try:
        project = session.query(Project).get(project_id)
        if not project:
            flash("案件が見つかりません。", "error")
            return redirect(url_for("main.index"))

        source = request.form.get("source", "all")
        new_count = 0

        if source in ("all", "gmail") and project.gmail_query:
            from quote_manager.services.ingestion import ingest_gmail
            new_quotes = ingest_gmail(session, project)
            new_count += len(new_quotes)

        if source in ("all", "slack") and project.slack_channel_id:
            from quote_manager.services.ingestion import ingest_slack
            new_quotes = ingest_slack(session, project)
            new_count += len(new_quotes)

        flash(f"{new_count}件の新規見積を取得しました。", "success")
        return redirect(url_for("main.project_detail", project_id=project_id))
    finally:
        session.close()


@bp.route("/projects/<int:project_id>/import", methods=["POST"])
def project_import(project_id):
    """Import a file (PDF/Excel) into a project."""
    session = get_session()
    try:
        project = session.query(Project).get(project_id)
        if not project:
            flash("案件が見つかりません。", "error")
            return redirect(url_for("main.index"))

        file = request.files.get("file")
        if not file or not file.filename:
            flash("ファイルを選択してください。", "error")
            return redirect(url_for("main.project_detail", project_id=project_id))

        supplier_name = request.form.get("supplier_name")

        # Save uploaded file temporarily
        suffix = os.path.splitext(file.filename)[1]
        with tempfile.NamedTemporaryFile(delete=False, suffix=suffix) as tmp:
            file.save(tmp.name)
            tmp_path = tmp.name

        try:
            from quote_manager.services.ingestion import ingest_file
            quote = ingest_file(session, project, tmp_path, supplier_name)

            if quote:
                flash(f"見積を取り込みました（明細 {len(quote.line_items)}件）。", "success")
            else:
                flash("見積データを抽出できませんでした。", "error")
        finally:
            os.unlink(tmp_path)

        return redirect(url_for("main.project_detail", project_id=project_id))
    finally:
        session.close()


@bp.route("/projects/<int:project_id>/compare")
def project_compare(project_id):
    """Comparison view for a project."""
    session = get_session()
    try:
        from quote_manager.services.comparison import build_comparison

        project = session.query(Project).get(project_id)
        if not project:
            flash("案件が見つかりません。", "error")
            return redirect(url_for("main.index"))

        table = build_comparison(session, project_id)
        return render_template("comparison.html", project=project, table=table)
    finally:
        session.close()


@bp.route("/projects/<int:project_id>/export/excel")
def project_export_excel(project_id):
    """Export comparison to Excel."""
    session = get_session()
    try:
        from quote_manager.services.comparison import build_comparison
        from quote_manager.services.export import export_to_excel

        table = build_comparison(session, project_id)
        if not table:
            flash("比較する見積がありません。", "error")
            return redirect(url_for("main.project_detail", project_id=project_id))

        output_path = tempfile.mktemp(suffix=".xlsx")
        export_to_excel(table, output_path)

        return send_file(
            output_path,
            as_attachment=True,
            download_name=f"見積比較表_{table.project_name}.xlsx",
            mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        )
    finally:
        session.close()


@bp.route("/projects/<int:project_id>/export/pdf")
def project_export_pdf(project_id):
    """Export comparison to PDF."""
    session = get_session()
    try:
        from quote_manager.services.comparison import build_comparison
        from quote_manager.services.export import export_to_pdf

        table = build_comparison(session, project_id)
        if not table:
            flash("比較する見積がありません。", "error")
            return redirect(url_for("main.project_detail", project_id=project_id))

        output_path = tempfile.mktemp(suffix=".pdf")
        export_to_pdf(table, output_path)

        return send_file(
            output_path,
            as_attachment=True,
            download_name=f"見積比較表_{table.project_name}.pdf",
            mimetype="application/pdf",
        )
    finally:
        session.close()
