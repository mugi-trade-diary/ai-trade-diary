"""Offline drafts and evidence-aware accounting. No network or execution adapters."""
import argparse
import datetime as dt
import html
import json
import math
import shutil
from pathlib import Path
from urllib.parse import urlencode

ROOT = Path(__file__).resolve().parent
TOPICS = [
    "事実と気持ちを分ける", "空欄でも続ける", "一行だけ書く", "休んだ日も記録する",
    "書く時間を決める", "見返す日を決める", "一週間を振り返る", "数字を盛らない",
    "分からないと書く", "記録を短くする", "昨日と比べすぎない", "気持ちに名前をつける",
    "できたことを一つ探す", "二週間の変化を読む", "書き忘れた日の戻り方",
    "結果と過程を分ける", "人の記録と比べない", "自分の言葉に直す", "疲れを記録する",
    "記録する場所を整える", "三週間の空欄を見る", "見返す項目を減らす",
    "休憩を予定に入れる", "一行を読み返す", "気づきを分類する", "続いた理由を探す",
    "やめたい記録を選ぶ", "四週間を振り返る", "来月の一項目を決める", "三十日をねぎらう",
]


def amount(value):
    if type(value) is not int or value < 0:
        raise ValueError("金額・件数は0以上の整数が必要です")
    return value


def generation_cost(seconds, attempts=1, model="turbo"):
    if type(seconds) is not int or seconds not in (5, 10):
        raise ValueError("この見積りは5秒/10秒クリップ専用です")
    if type(attempts) is not int or attempts < 1:
        raise ValueError("試行回数は1以上の整数です")
    rate = {"turbo": 5, "gen45": 12}[model]
    return {"credits": seconds * attempts * rate,
            "api_usd": seconds * attempts * rate / 100}


def validate_draft(config):
    if (config.get("mode") != "draft_only" or
            type(config.get("approved_spend_jpy")) is not int or
            config.get("approved_spend_jpy") != 0):
        raise ValueError("このツールは承認前・追加支出0円の下書き専用です")
    for key in ("real_submit_allowed", "publish_allowed", "billing_allowed",
                "autopost_allowed", "merge_allowed"):
        if config.get(key) is not False:
            raise ValueError(f"{key} must be false")


def report(data):
    """All amounts are JPY, one reconciled period, no estimates accepted as actuals."""
    result = {"status": "UNKNOWN", "actual_net_profit_jpy": None}
    if data.get("evidence_type") != "actual" or data.get("reconciled") is not True:
        return result
    for key in ("period", "payment_evidence", "expense_evidence", "tax_evidence"):
        if not isinstance(data.get(key), str) or not data[key].strip():
            return result
    keys = ("gross_sales_jpy", "refunds_jpy", "chargebacks_jpy", "fees_jpy",
            "production_jpy", "advertising_jpy", "hosting_jpy", "other_costs_jpy",
            "taxes_jpy", "labor_minutes", "labor_rate_jpy_hour")
    if any(data.get(k) is None for k in keys):
        return result
    values = {k: amount(data[k]) for k in keys}
    # Refunds can relate to earlier periods; negative monthly revenue is valid.
    net_sales = values["gross_sales_jpy"] - values["refunds_jpy"] - values["chargebacks_jpy"]
    costs = sum(values[k] for k in ("fees_jpy", "production_jpy", "advertising_jpy",
                                   "hosting_jpy", "other_costs_jpy", "taxes_jpy"))
    profit = net_sales - costs
    result.update(status="RECONCILED_INPUT", net_sales_jpy=net_sales,
                  actual_net_profit_jpy=profit,
                  labor_adjusted_profit_jpy=profit - math.ceil(values["labor_minutes"] * values["labor_rate_jpy_hour"] / 60),
                  note="入力証憑の人手照合が前提。ツールは証憑の真正性を検証しません。")
    return result


def funnel(counts):
    stages = ("views", "profile_visits", "landing_sessions", "downloads", "paid_orders")
    clean = {k: None if counts.get(k) is None else amount(counts[k]) for k in stages}
    return {f"{b}_per_{a}": None if clean[a] in (None, 0) or clean[b] is None
            else clean[b] / clean[a] for a, b in zip(stages, stages[1:])}


def build(output, start):
    config = json.loads((ROOT / "config.json").read_text(encoding="utf-8"))
    validate_draft(config)
    # Never silently overwrite an earlier approval/review package.
    output.mkdir(parents=True, exist_ok=False)
    (output / "images").mkdir()
    for character in ("mugi", "kuu", "meru", "hamu"):
        shutil.copyfile(ROOT.parent / "images" / f"icon-{character}.jpg",
                        output / "images" / f"icon-{character}.jpg")
    (output / "free-sheet.md").write_text((ROOT / "free-sheet.md").read_text(encoding="utf-8"), encoding="utf-8")
    scripts = []
    for n, topic in enumerate(TOPICS):
        day = start + dt.timedelta(days=n)
        content_id = f"diary-{day:%Y%m%d}"
        scripts.append({"date_jst": str(day), "content_id": content_id,
            "status": "DRAFT_REQUIRES_REVIEW", "duration_seconds": 30,
            "topic": topic, "ai_label_review": "required", "rights_status": "UNKNOWN",
            "commercial_disclosure": "自社商品の宣伝として投稿前に設定を確認",
            "utm_query": urlencode({"utm_source": "tiktok", "utm_medium": "organic_social",
                                     "utm_campaign": "diary_pilot", "utm_content": content_id}),
            "scenes": [
                {"seconds": [0, 3], "character": "ムギ", "line": f"今日のテーマは「{topic}」。一緒に一行、残そう。"},
                {"seconds": [3, 12], "character": "メル", "line": "シートの一段目に、今日あった事実を一つ。気持ちは二段目に分けて書こう。"},
                {"seconds": [12, 22], "character": "クウ", "line": f"「{topic}」なら、自分はどう書く？ 銘柄や口座情報は書かなくて大丈夫。"},
                {"seconds": [22, 26], "character": "ハム", "line": "書けたところまでで大丈夫。今日はここまで、ひと休み。"},
                {"seconds": [26, 30], "character": "メル", "line": "無料のふりかえりシートはプロフィールから。"}],
            "editor_note": "各回に独自の架空記入例を追加して読み上げ時間を確認。プロフィールリンク未開通時はCTA差替え。利益・勝率・銘柄推奨は入れない。"})
    (output / "calendar.json").write_text(json.dumps(scripts, ensure_ascii=False, indent=2), encoding="utf-8")
    cards = "".join(f'<article><h2>{html.escape(p["name"])}</h2><p>{p["price_jpy"]:,}円'
                    + ('／月（案）' if p["id"] == "membership" else '（案）')
                    + '</p><p>販売準備中</p><button disabled>まだ購入できません</button></article>'
                    for p in config["products"] if p["price_jpy"])
    page = '''<!doctype html><html lang="ja"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="robots" content="noindex,nofollow"><title>AIトレード日記｜ふりかえりシート</title>
<style>body{font:18px/1.8 system-ui,sans-serif;margin:0;background:#fff4f8;color:#28202a}main{max-width:840px;margin:auto;padding:28px}h1{line-height:1.4}article{background:white;border:1px solid #e0cbd6;border-radius:16px;padding:20px;margin:18px 0}a{color:#92134c}button{padding:12px;font:inherit}aside{padding:12px;background:#ffe0ed}footer{font-size:14px}</style>
<main><aside>確認用の下書きです。販売・申込みは開始していません。</aside>
<h1>今日の気持ちを、<br>3行の記録に。</h1><p>ムギ・クウ・メル・ハムと、無理なくふりかえる。</p>
<div><img src="images/icon-mugi.jpg" alt="ムギ" width="64" height="64"> <img src="images/icon-kuu.jpg" alt="クウ" width="64" height="64"> <img src="images/icon-meru.jpg" alt="メル" width="64" height="64"> <img src="images/icon-hamu.jpg" alt="ハム" width="64" height="64"></div>
<article><h2>まずは無料で、一週間。</h2><p>事実・気持ち・明日の記録。この3つだけ。メール登録は不要です。</p>
<a href="free-sheet.md" download>無料のふりかえりシートを保存</a></article>''' + cards + '''
<footer><p>売買の推奨、銘柄診断、利益の保証は行いません。記録はご自身の端末に保管してください。</p>
<p>この確認用ページは個人情報を収集せず、外部への計測送信も行いません。</p></footer></main></html>'''
    (output / "index.html").write_text(page, encoding="utf-8")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    draft = sub.add_parser("build")
    draft.add_argument("--output", type=Path, required=True)
    draft.add_argument("--start", type=dt.date.fromisoformat, required=True)
    accounting = sub.add_parser("report")
    accounting.add_argument("input", type=Path)
    args = parser.parse_args()
    if args.command == "build":
        build(args.output, args.start)
    else:
        data = json.loads(args.input.read_text(encoding="utf-8"))
        print(json.dumps({"financials": report(data), "funnel": funnel(data.get("counts", {}))}, ensure_ascii=False, indent=2))


if __name__ == "__main__":
    main()
