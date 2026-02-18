# VERSION: FINAL-FULL-FIX-V3 (KeyError 'date' 完全回避・DF正規化・空データ耐性・CI/Headless対応)

import os
import json
import pandas as pd
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
import matplotlib
matplotlib.use("Agg")  # GitHub Actions / headless 環境で必須
import matplotlib.pyplot as plt

# 日本語フォント（無ければスルー）
try:
    plt.rcParams["font.family"] = "Noto Sans CJK JP"
except Exception:
    pass


# =========================
# 1) GSC Client
# =========================
def get_service_client():
    sa_json_str = os.environ.get("GOOGLE_SA_JSON")
    if not sa_json_str:
        print("CRITICAL: GOOGLE_SA_JSON not found.")
        return None

    try:
        sa_info = json.loads(sa_json_str)
        creds = service_account.Credentials.from_service_account_info(sa_info)
        return build("webmasters", "v3", credentials=creds)
    except Exception as e:
        print(f"Auth Error: {e}")
        return None


# =========================
# 2) DF 正規化（最重要）
# =========================
def normalize_gsc_df(df: pd.DataFrame) -> pd.DataFrame:
    """
    GSCの返却（rows->DataFrame）がどんな形でも、
    必ず date/clicks/impressions/ctr/position のスキーマに揃えて返す。
    - dateが無い/keysしか無い/indexにdateがある/列が欠損 など全て吸収
    """
    schema = ["date", "clicks", "impressions", "ctr", "position"]
    empty = pd.DataFrame(columns=schema)

    if df is None or not isinstance(df, pd.DataFrame) or df.empty:
        return empty

    df = df.copy()

    # 列名の揺れ対策
    df.columns = [str(c).strip() for c in df.columns]

    # date が列に無い場合の救済
    if "date" not in df.columns:
        # 1) keys から date を作る（GSC標準）
        if "keys" in df.columns:
            df["date"] = df["keys"].apply(
                lambda x: x[0] if isinstance(x, list) and len(x) else None
            )
        # 2) index名がdateなら列に戻す
        elif getattr(df.index, "name", None) and str(df.index.name).strip().lower() == "date":
            df = df.reset_index()

    # それでも date が無いなら空で返す
    if "date" not in df.columns:
        return empty

    # date を安全に datetime 化（壊れてても落とさない）
    df["date"] = pd.to_datetime(df["date"], errors="coerce")
    df = df.dropna(subset=["date"])

    if df.empty:
        return empty

    # 必須数値列の穴埋め & 数値化
    for col in ["clicks", "impressions", "ctr", "position"]:
        if col not in df.columns:
            df[col] = 0
        df[col] = pd.to_numeric(df[col], errors="coerce").fillna(0)

    return df[["date", "clicks", "impressions", "ctr", "position"]]


# =========================
# 3) GSC Fetch
# =========================
def fetch_gsc_data(service, site_url: str, start_date: str, end_date: str) -> pd.DataFrame:
    """
    データ取得：0件でも必ず正規化済みDFを返す（KeyError完全回避）
    """
    print(f"DEBUG: Fetching data for {site_url} ({start_date} ~ {end_date})...")

    request = {
        "startDate": start_date,
        "endDate": end_date,
        "dimensions": ["date"],     # 必須：date軸
        "rowLimit": 25000,
    }

    try:
        response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
        rows = response.get("rows", [])

        if not rows:
            print(f"DEBUG: {start_date} の期間はデータが0件です。")
            return normalize_gsc_df(pd.DataFrame())

        df = pd.DataFrame(rows)

        # keys -> date（保険：dimensions指定しててもkeysで来る）
        if "keys" in df.columns and "date" not in df.columns:
            df["date"] = df["keys"].apply(lambda x: x[0] if isinstance(x, list) and len(x) else None)

        df = normalize_gsc_df(df)
        return df

    except Exception as e:
        print(f"DEBUG: API Error: {e}")
        return normalize_gsc_df(pd.DataFrame())


# =========================
# 4) Chart
# =========================
def create_chart(df: pd.DataFrame, out_path: str = "reports/weekly_chart.png") -> bool:
    """
    グラフ作成：空ならスキップ。成功したら True
    """
    df = normalize_gsc_df(df)

    if df.empty:
        print("WARNING: グラフ作成用データが空のため、グラフ作成をスキップします。")
        return False

    try:
        df = df.sort_values("date")

        plt.figure(figsize=(10, 5))
        plt.plot(df["date"], df["clicks"], label="Clicks", marker="o")
        plt.title("Weekly Clicks")
        plt.xlabel("Date")
        plt.ylabel("Clicks")
        plt.grid(True)
        plt.legend()

        os.makedirs(os.path.dirname(out_path), exist_ok=True)
        plt.savefig(out_path, bbox_inches="tight")
        plt.close()

        print(f"SUCCESS: グラフを保存しました ({out_path})")
        return True

    except Exception as e:
        print(f"ERROR: グラフ作成中にエラーが発生しました: {e}")
        return False


# =========================
# 5) Date helpers
# =========================
def parse_ymd(s: str):
    try:
        return datetime.strptime(s, "%Y-%m-%d")
    except Exception:
        return None


def calc_prev_week(start: str, end: str):
    s = parse_ymd(start)
    e = parse_ymd(end)
    if not s or not e:
        return None, None
    return (s - timedelta(days=7)).strftime("%Y-%m-%d"), (e - timedelta(days=7)).strftime("%Y-%m-%d")


# =========================
# 6) HTML Report
# =========================
def write_report_html(
    out_path: str,
    start: str,
    end: str,
    df_current: pd.DataFrame,
    df_prev: pd.DataFrame,
    chart_created: bool,
):
    df_current = normalize_gsc_df(df_current)
    df_prev = normalize_gsc_df(df_prev)

    # 集計（空でもOK）
    total_clicks = float(df_current["clicks"].sum()) if not df_current.empty else 0.0
    total_impr = float(df_current["impressions"].sum()) if not df_current.empty else 0.0

    prev_clicks = float(df_prev["clicks"].sum()) if not df_prev.empty else 0.0
    prev_impr = float(df_prev["impressions"].sum()) if not df_prev.empty else 0.0

    def pct_change(cur, prev):
        if prev == 0:
            return None
        return (cur - prev) / prev * 100.0

    clicks_chg = pct_change(total_clicks, prev_clicks)
    impr_chg = pct_change(total_impr, prev_impr)

    def fmt_pct(v):
        if v is None:
            return "N/A"
        return f"{v:+.1f}%"

    chart_html = "<p><em>Chart not available.</em></p>"
    if chart_created:
        chart_html = "<img src='weekly_chart.png' style='max-width:100%;height:auto;'>"

    html = f"""<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <title>Weekly Report</title>
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <style>
    body {{ font-family: -apple-system,BlinkMacSystemFont,"Segoe UI",Roboto,Helvetica,Arial,"Noto Sans JP","Hiragino Sans","Yu Gothic",sans-serif; padding: 16px; }}
    .card {{ border: 1px solid #ddd; border-radius: 10px; padding: 16px; margin: 12px 0; }}
    .muted {{ color: #666; }}
    table {{ border-collapse: collapse; width: 100%; }}
    th, td {{ border-bottom: 1px solid #eee; padding: 8px; text-align: left; }}
  </style>
</head>
<body>
  <h1>Weekly Report ({start} ~ {end})</h1>

  <div class="card">
    <h2>Summary</h2>
    <table>
      <tr><th>Metric</th><th>This Week</th><th>Prev Week</th><th>Change</th></tr>
      <tr><td>Clicks</td><td>{total_clicks:.0f}</td><td>{prev_clicks:.0f}</td><td>{fmt_pct(clicks_chg)}</td></tr>
      <tr><td>Impressions</td><td>{total_impr:.0f}</td><td>{prev_impr:.0f}</td><td>{fmt_pct(impr_chg)}</td></tr>
    </table>
    <p class="muted">※ Prev Week = 7日前の同期間</p>
  </div>

  <div class="card">
    <h2>Chart</h2>
    {chart_html}
  </div>

  <div class="card">
    <h2>Data Status</h2>
    <p>Current rows: {len(df_current)}</p>
    <p>Prev rows: {len(df_prev)}</p>
    <p class="muted">データが0件の週は、GSCの集計遅延・アクセス権限・プロパティURL不一致などが原因のことがあります。</p>
  </div>
</body>
</html>
"""
    os.makedirs(os.path.dirname(out_path), exist_ok=True)
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)
    print(f"SUCCESS: レポートHTMLを保存しました ({out_path})")


# =========================
# 7) Main
# =========================
def main():
    print("--- STARTING WEEKLY REPORT (FULL FIX V3) ---")

    site_url = os.environ.get("GSC_SITE_URL")
    if not site_url:
        print("CRITICAL: GSC_SITE_URL not found.")
        return

    start = os.environ.get("START_DATE")
    end = os.environ.get("END_DATE")
    if not start or not end:
        print("CRITICAL: START_DATE / END_DATE not found.")
        return

    # 日付形式チェック（変なら落とさず終了）
    if not parse_ymd(start) or not parse_ymd(end):
        print("CRITICAL: START_DATE / END_DATE format must be YYYY-MM-DD.")
        return

    service = get_service_client()
    if not service:
        return

    prev_start, prev_end = calc_prev_week(start, end)
    if not prev_start or not prev_end:
        prev_start, prev_end = "2000-01-01", "2000-01-01"

    # 1) Fetch
    df_current = fetch_gsc_data(service, site_url, start, end)
    df_prev = fetch_gsc_data(service, site_url, prev_start, prev_end)

    # 念のため正規化（二重防御）
    df_current = normalize_gsc_df(df_current)
    df_prev = normalize_gsc_df(df_prev)

    os.makedirs("reports", exist_ok=True)

    # 2) Chart（空なら作らない）
    chart_created = create_chart(df_current, out_path="reports/weekly_chart.png")

    # 3) HTML（空でも必ず出す）
    write_report_html(
        out_path="reports/index.html",
        start=start,
        end=end,
        df_current=df_current,
        df_prev=df_prev,
        chart_created=chart_created,
    )

    # 4) Console summary
    if df_current.empty:
        print("RESULT: 今週データが0件でした（GSC集計待ち/プロパティURL不一致/権限などの可能性）。")
    else:
        print(f"RESULT: 今週データ {len(df_current)} 件 / Clicks={df_current['clicks'].sum():.0f}")

    print("--- DONE ---")


if __name__ == "__main__":
    main()
