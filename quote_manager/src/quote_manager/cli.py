"""CLI interface for the quote management system."""

import click
from pathlib import Path

from quote_manager.models.base import init_db, get_session
from quote_manager.models import Project, Supplier, Quote


@click.group()
def main():
    """相見積もり管理システム - Quote Management System"""
    init_db()


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
