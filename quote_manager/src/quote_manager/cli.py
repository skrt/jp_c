"""CLI interface for the quote management system."""

import click
from pathlib import Path

from quote_manager.models.base import init_db, get_session
from quote_manager.models import Project, Supplier, Quote


@click.group()
def main():
    """相見積もり管理システム - Quote Management System"""
    init_db()


# ===== Auth command =====

@main.command("auth")
def auth():
    """Gmail OAuth認証をセットアップ"""
    from quote_manager.config import get_settings
    settings = get_settings()

    creds_path = settings.gmail_credentials_path
    if not Path(creds_path).exists():
        click.echo("⚠ Gmail認証にはOAuth2の credentials.json が必要です。")
        click.echo("")
        click.echo("セットアップ手順:")
        click.echo("  1. Google Cloud Console (console.cloud.google.com) にアクセス")
        click.echo("  2. プロジェクトを作成（または既存を選択）")
        click.echo("  3. 「APIとサービス」→「ライブラリ」→ Gmail API を有効化")
        click.echo("  4. 「APIとサービス」→「認証情報」→「認証情報を作成」→「OAuthクライアントID」")
        click.echo("     - アプリケーションの種類: デスクトップアプリ")
        click.echo("  5. JSONをダウンロードして credentials.json としてこのディレクトリに配置")
        click.echo(f"     → {Path(creds_path).resolve()}")
        click.echo("")
        click.echo("配置後にもう一度 'quote-manager auth' を実行してください。")
        return

    click.echo("Gmail認証を開始します... ブラウザが開きます。")
    try:
        from quote_manager.gmail.auth import get_gmail_service
        service = get_gmail_service(creds_path, settings.gmail_token_path)
        # Verify by fetching profile
        profile = service.users().getProfile(userId="me").execute()
        click.echo(f"✓ 認証成功！ アカウント: {profile['emailAddress']}")
        click.echo(f"  メール数: {profile.get('messagesTotal', '不明')}")
    except Exception as e:
        click.echo(f"✗ 認証エラー: {e}")


# ===== Scan & Auto-group command =====

@main.command("scan")
@click.option("--query", "-q", default="見積", help="Gmail検索クエリ (デフォルト: 見積)")
@click.option("--max-results", "-m", default=50, help="取得件数上限")
@click.option("--auto-create", "-a", is_flag=True, help="確認なしで案件を自動作成")
def scan(query, max_results, auto_create):
    """Gmailを検索して見積メールを自動グルーピング → 案件作成"""
    click.echo(f"Gmailを検索中... クエリ: '{query}' (最大 {max_results}件)")

    try:
        from quote_manager.gmail.fetcher import fetch_emails
        from quote_manager.gmail.grouper import auto_group, summarize_group
    except Exception as e:
        click.echo(f"✗ Gmail接続エラー: {e}")
        click.echo("  'quote-manager auth' で認証をセットアップしてください。")
        return

    try:
        emails = fetch_emails(query, max_results=max_results)
    except Exception as e:
        click.echo(f"✗ メール取得エラー: {e}")
        return

    if not emails:
        click.echo("見積関連のメールが見つかりませんでした。")
        return

    click.echo(f"  {len(emails)}件のメールを取得しました。")
    click.echo("")

    # Auto-group
    groups = auto_group(emails)
    click.echo(f"  → {len(groups)}件の案件グループに分類しました。")
    click.echo("")

    # Display groups
    summaries = []
    for key, group_emails in groups.items():
        summary = summarize_group(key, group_emails)
        summaries.append(summary)

    for i, s in enumerate(summaries, 1):
        date_from, date_to = s["date_range"]
        date_str = ""
        if date_from and date_to:
            date_str = f"{date_from.strftime('%m/%d')}~{date_to.strftime('%m/%d')}"

        att_mark = " [添付あり]" if s["has_attachments"] else ""
        click.echo(f"  [{i}] {s['suggested_name']}")
        click.echo(f"      メール数: {s['email_count']}  送信元: {', '.join(s['senders'][:3])}{'...' if len(s['senders']) > 3 else ''}")
        click.echo(f"      期間: {date_str}{att_mark}")
        click.echo("")

    # Create projects
    if not auto_create:
        click.echo("---")
        click.echo("案件として登録するグループを選択してください。")
        click.echo("  番号をカンマ区切りで入力 (例: 1,3,5)  /  'all' で全て  /  'q' でキャンセル")
        selection = click.prompt("選択", default="all")

        if selection.strip().lower() == "q":
            click.echo("キャンセルしました。")
            return
        elif selection.strip().lower() == "all":
            selected_indices = list(range(len(summaries)))
        else:
            try:
                selected_indices = [int(x.strip()) - 1 for x in selection.split(",")]
            except ValueError:
                click.echo("無効な入力です。")
                return
    else:
        selected_indices = list(range(len(summaries)))

    session = get_session()
    try:
        created_count = 0
        for idx in selected_indices:
            if idx < 0 or idx >= len(summaries):
                click.echo(f"  スキップ: 無効な番号 {idx + 1}")
                continue

            s = summaries[idx]

            # Check for existing project with same name
            existing = session.query(Project).filter_by(name=s["suggested_name"]).first()
            if existing:
                click.echo(f"  スキップ: 「{s['suggested_name']}」は既に案件ID {existing.id} として登録済み")
                continue

            # Build Gmail query to re-fetch this group's emails
            senders = s["senders"]
            subjects = s["subjects"]
            # Use the first subject as query base
            gmail_query = f"subject:({subjects[0]})" if subjects else query

            project = Project(
                name=s["suggested_name"],
                gmail_query=gmail_query,
                description=f"送信元: {', '.join(senders[:5])}",
            )
            session.add(project)
            session.flush()

            click.echo(f"  ✓ 案件作成: [{project.id}] {project.name}")
            created_count += 1

            # Immediately ingest the already-fetched emails
            from quote_manager.services.ingestion import _try_parse_with_fallback, _parsed_to_quote, _get_or_create_supplier, _is_already_processed
            from quote_manager.models import EmailRecord
            from quote_manager.parsers.email_body import EmailBodyParser
            from quote_manager.parsers.pdf_parser import PdfParser
            from quote_manager.parsers.excel_parser import ExcelParser
            import json

            email_parser = EmailBodyParser()
            pdf_parser = PdfParser()
            excel_parser = ExcelParser()
            quote_count = 0

            for raw_email in s["emails"]:
                if _is_already_processed(session, raw_email.message_id):
                    continue

                metadata = {
                    "sender_name": raw_email.sender,
                    "sender_email": raw_email.sender_email,
                    "subject": raw_email.subject,
                }

                record = EmailRecord(
                    message_id=raw_email.message_id,
                    source="gmail",
                    project_id=project.id,
                    subject=raw_email.subject,
                    sender=raw_email.sender_email,
                    received_at=raw_email.date,
                    processed=True,
                    attachment_paths=json.dumps(raw_email.attachment_paths) if raw_email.attachment_paths else None,
                )
                session.add(record)

                # Parse email body
                if raw_email.body_text:
                    parsed = _try_parse_with_fallback(raw_email.body_text, email_parser, metadata)
                    if parsed:
                        _parsed_to_quote(session, parsed, project, "email_body")
                        quote_count += 1

                # Parse attachments
                for att_path in raw_email.attachment_paths:
                    lower_path = att_path.lower()
                    if lower_path.endswith(".pdf"):
                        parsed = _try_parse_with_fallback(att_path, pdf_parser, metadata)
                    elif lower_path.endswith((".xlsx", ".xls")):
                        parsed = _try_parse_with_fallback(att_path, excel_parser, metadata)
                    else:
                        parsed = None
                    if parsed:
                        source_type = "pdf" if lower_path.endswith(".pdf") else "excel"
                        _parsed_to_quote(session, parsed, project, source_type, att_path)
                        quote_count += 1

            if quote_count:
                click.echo(f"      → {quote_count}件の見積を抽出")

        session.commit()
        click.echo(f"\n✓ {created_count}件の案件を作成しました。")
        click.echo("  'quote-manager project list' で一覧を確認できます。")
        click.echo("  'quote-manager compare <ID>' で比較表を表示できます。")
    finally:
        session.close()


# ===== Project commands =====

@main.group()
def project():
    """案件（プロジェクト）管理"""
    pass


@project.command("create")
@click.option("--name", "-n", required=True, help="案件名")
@click.option("--gmail-query", "-g", default=None, help="Gmail検索クエリ (例: subject:見積 from:xxx)")
@click.option("--slack-channel", "-s", default=None, help="Slackチャンネル ID")
@click.option("--slack-thread", "-t", default=None, help="Slackスレッド timestamp")
@click.option("--description", "-d", default=None, help="案件の説明")
def project_create(name, gmail_query, slack_channel, slack_thread, description):
    """新しい案件を作成"""
    session = get_session()
    try:
        p = Project(
            name=name,
            description=description,
            gmail_query=gmail_query,
            slack_channel_id=slack_channel,
            slack_thread_ts=slack_thread,
        )
        session.add(p)
        session.commit()
        click.echo(f"✓ 案件を作成しました: [{p.id}] {p.name}")
    finally:
        session.close()


@project.command("list")
def project_list():
    """案件一覧を表示"""
    session = get_session()
    try:
        projects = session.query(Project).order_by(Project.created_at.desc()).all()
        if not projects:
            click.echo("案件がありません。'quote-manager project create' で作成してください。")
            return

        click.echo(f"{'ID':>4}  {'ステータス':^8}  {'見積数':>5}  {'案件名'}")
        click.echo("-" * 60)
        for p in projects:
            count = session.query(Quote).filter_by(project_id=p.id).count()
            click.echo(f"{p.id:>4}  {p.status:^8}  {count:>5}  {p.name}")
    finally:
        session.close()


@project.command("show")
@click.argument("project_id", type=int)
def project_show(project_id):
    """案件の詳細を表示"""
    session = get_session()
    try:
        p = session.query(Project).get(project_id)
        if not p:
            click.echo(f"案件 ID {project_id} が見つかりません。")
            return

        click.echo(f"案件: {p.name} (ID: {p.id})")
        click.echo(f"ステータス: {p.status}")
        if p.description:
            click.echo(f"説明: {p.description}")
        if p.gmail_query:
            click.echo(f"Gmail検索: {p.gmail_query}")
        if p.slack_channel_id:
            click.echo(f"Slackチャンネル: {p.slack_channel_id}")

        quotes = session.query(Quote).filter_by(project_id=p.id).all()
        if quotes:
            click.echo(f"\n--- 見積一覧 ({len(quotes)}件) ---")
            for q in quotes:
                supplier = session.query(Supplier).get(q.supplier_id)
                total = f"¥{q.total_amount:,.0f}" if q.total_amount else "未定"
                click.echo(f"  [{q.id}] {supplier.name}: {total} ({q.source_type})")
        else:
            click.echo("\nまだ見積がありません。")
    finally:
        session.close()


# ===== Fetch commands =====

@main.command("fetch")
@click.argument("project_id", type=int)
@click.option("--source", "-s", type=click.Choice(["all", "gmail", "slack"]), default="all", help="取得元")
def fetch(project_id, source):
    """メール/Slackから見積を取得してパース"""
    session = get_session()
    try:
        p = session.query(Project).get(project_id)
        if not p:
            click.echo(f"案件 ID {project_id} が見つかりません。")
            return

        click.echo(f"案件 [{p.id}] {p.name} の見積を取得中...")
        total_new = []

        if source in ("all", "gmail") and p.gmail_query:
            from quote_manager.services.ingestion import ingest_gmail
            click.echo("  Gmail取得中...")
            new_quotes = ingest_gmail(session, p)
            total_new.extend(new_quotes)
            click.echo(f"  Gmail: {len(new_quotes)}件の新規見積を取得")

        if source in ("all", "slack") and p.slack_channel_id:
            from quote_manager.services.ingestion import ingest_slack
            click.echo("  Slack取得中...")
            new_quotes = ingest_slack(session, p)
            total_new.extend(new_quotes)
            click.echo(f"  Slack: {len(new_quotes)}件の新規見積を取得")

        click.echo(f"\n✓ 合計 {len(total_new)}件の新規見積を取得しました。")
    finally:
        session.close()


# ===== Import command =====

@main.command("import")
@click.argument("project_id", type=int)
@click.argument("file_path", type=click.Path(exists=True))
@click.option("--supplier", "-s", default=None, help="サプライヤー名")
def import_file(project_id, file_path, supplier):
    """ファイル（PDF/Excel）を手動で取り込み"""
    session = get_session()
    try:
        p = session.query(Project).get(project_id)
        if not p:
            click.echo(f"案件 ID {project_id} が見つかりません。")
            return

        from quote_manager.services.ingestion import ingest_file
        quote = ingest_file(session, p, file_path, supplier)

        if quote:
            sup = session.query(Supplier).get(quote.supplier_id)
            total = f"¥{quote.total_amount:,.0f}" if quote.total_amount else "未定"
            click.echo(f"✓ 見積を取り込みました: {sup.name} - {total}")
            click.echo(f"  明細行数: {len(quote.line_items)}")
        else:
            click.echo("見積データを抽出できませんでした。AI抽出を試みるにはANTHROPIC_API_KEYを設定してください。")
    finally:
        session.close()


# ===== Compare command =====

@main.command("compare")
@click.argument("project_id", type=int)
def compare(project_id):
    """見積比較表をターミナルに表示"""
    session = get_session()
    try:
        from quote_manager.services.comparison import build_comparison
        table = build_comparison(session, project_id)

        if not table:
            click.echo("比較する見積がありません。")
            return

        # Print comparison table
        click.echo(f"\n{'='*80}")
        click.echo(f"  見積比較表: {table.project_name}")
        click.echo(f"{'='*80}\n")

        # Header
        header = f"{'No.':>4}  {'品名':<30}"
        for sup in table.suppliers:
            header += f"  {sup['name']:>15}"
        click.echo(header)
        click.echo("-" * len(header))

        # Rows
        for row in table.rows:
            line = f"{row.item_number:>4}  {row.description[:30]:<30}"
            for cell in row.cells:
                if cell.amount is not None:
                    val = f"¥{cell.amount:,.0f}"
                    if cell.is_lowest:
                        val = f"*{val}"
                else:
                    val = "-"
                line += f"  {val:>15}"
            click.echo(line)

        # Summary
        click.echo("-" * len(header))
        total_line = f"{'':>4}  {'合計':<30}"
        for summary in table.summaries:
            if summary.total_amount is not None:
                val = f"¥{summary.total_amount:,.0f}"
                if summary.is_lowest_total:
                    val = f"*{val}"
            else:
                val = "-"
            total_line += f"  {val:>15}"
        click.echo(total_line)

        # Delivery info
        delivery_line = f"{'':>4}  {'納期':<30}"
        for summary in table.summaries:
            val = summary.delivery_date or "-"
            delivery_line += f"  {val:>15}"
        click.echo(delivery_line)

        click.echo(f"\n* = 最安値")
    finally:
        session.close()


# ===== Export commands =====

@main.group()
def export():
    """見積比較表をエクスポート"""
    pass


@export.command("excel")
@click.argument("project_id", type=int)
@click.option("--output", "-o", default=None, help="出力ファイルパス")
def export_excel(project_id, output):
    """見積比較表をExcelファイルに出力"""
    session = get_session()
    try:
        from quote_manager.services.comparison import build_comparison
        from quote_manager.services.export import export_to_excel

        table = build_comparison(session, project_id)
        if not table:
            click.echo("比較する見積がありません。")
            return

        if not output:
            output = f"data/見積比較表_{table.project_name}.xlsx"

        path = export_to_excel(table, output)
        click.echo(f"✓ Excelファイルを出力しました: {path}")
    finally:
        session.close()


@export.command("pdf")
@click.argument("project_id", type=int)
@click.option("--output", "-o", default=None, help="出力ファイルパス")
def export_pdf(project_id, output):
    """見積比較表をPDFファイルに出力"""
    session = get_session()
    try:
        from quote_manager.services.comparison import build_comparison
        from quote_manager.services.export import export_to_pdf

        table = build_comparison(session, project_id)
        if not table:
            click.echo("比較する見積がありません。")
            return

        if not output:
            output = f"data/見積比較表_{table.project_name}.pdf"

        path = export_to_pdf(table, output)
        click.echo(f"✓ PDFファイルを出力しました: {path}")
    finally:
        session.close()


# ===== Supplier commands =====

@main.group()
def supplier():
    """サプライヤー管理"""
    pass


@supplier.command("list")
def supplier_list():
    """サプライヤー一覧を表示"""
    session = get_session()
    try:
        suppliers = session.query(Supplier).order_by(Supplier.name).all()
        if not suppliers:
            click.echo("サプライヤーがありません。")
            return

        click.echo(f"{'ID':>4}  {'名前':<30}  {'メール':<30}  {'見積数':>5}")
        click.echo("-" * 75)
        for s in suppliers:
            count = session.query(Quote).filter_by(supplier_id=s.id).count()
            click.echo(f"{s.id:>4}  {s.name:<30}  {s.email or '-':<30}  {count:>5}")
    finally:
        session.close()


@supplier.command("merge")
@click.argument("source_id", type=int)
@click.argument("target_id", type=int)
def supplier_merge(source_id, target_id):
    """サプライヤーを統合（sourceをtargetにマージ）"""
    session = get_session()
    try:
        source = session.query(Supplier).get(source_id)
        target = session.query(Supplier).get(target_id)

        if not source or not target:
            click.echo("指定されたサプライヤーが見つかりません。")
            return

        # Move all quotes from source to target
        quotes = session.query(Quote).filter_by(supplier_id=source.id).all()
        for q in quotes:
            q.supplier_id = target.id

        session.delete(source)
        session.commit()

        click.echo(f"✓ {source.name} を {target.name} に統合しました ({len(quotes)}件の見積を移行)")
    finally:
        session.close()


# ===== Web UI command =====

@main.command("web")
@click.option("--port", "-p", default=5000, help="ポート番号")
@click.option("--debug", is_flag=True, help="デバッグモード")
def web(port, debug):
    """Web UIを起動"""
    from quote_manager.web.app import create_app
    app = create_app()
    click.echo(f"Web UIを起動中... http://localhost:{port}")
    app.run(port=port, debug=debug)


if __name__ == "__main__":
    main()
