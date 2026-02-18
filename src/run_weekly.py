# VERSION: 2026-FIX
import os
import json
import pandas as pd
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
import matplotlib.pyplot as plt
import jinja2

# 日本語フォント設定
plt.rcParams['font.family'] = 'Noto Sans CJK JP' 

def get_service_client():
    sa_json_str = os.environ.get("GOOGLE_SA_JSON")
    if not sa_json_str:
        # 万が一キーがない場合の安全策
        print("CRITICAL: GOOGLE_SA_JSON not found.")
        return None
    
    try:
        sa_info = json.loads(sa_json_str)
        creds = service_account.Credentials.from_service_account_info(sa_info)
        return build('webmasters', 'v3', credentials=creds)
    except Exception as e:
        print(f"Auth Error: {e}")
        return None

def fetch_gsc_data(service, site_url, start_date, end_date):
    if service is None: return pd.DataFrame()
    print(f"DEBUG: Fetching data for {site_url} ({start_date} ~ {end_date})...")
    
    request = {
        'startDate': start_date,
        'endDate': end_date,
        'dimensions': ['date'], 
        'rowLimit': 25000
    }
    
    try:
        response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
        rows = response.get('rows', [])
        
        if not rows:
            print("DEBUG: データが0件でした (Rows is empty)")
            return pd.DataFrame()
        
        df = pd.DataFrame(rows)
        
        # 【重要】GSC APIの仕様: dimensions=['date'] の場合、結果は 'keys' というリストに入ってくる
        # 古いコードはここで df['date'] を探してエラーになっていました
        if 'keys' in df.columns:
            # keysリストから日付文字列を取り出す
            df['date'] = df['keys'].apply(lambda x: x if isinstance(x, list) and len(x) > 0 else x)
        elif 'date' not in df.columns:
            print(f"DEBUG: 想定外のデータ構造です: {df.columns}")
            return pd.DataFrame()
            
        return df
        
    except Exception as e:
        print(f"DEBUG: API Error: {e}")
        return pd.DataFrame()

def process_data(df_current, df_prev):
    # データなしの場合のデフォルト値
    if df_current.empty:
        return {'current_clicks': 0, 'prev_clicks': 0, 'diff': 0, 'growth_rate': 0, 'df_current': df_current}
    
    # 数値変換
    df_current['clicks'] = pd.to_numeric(df_current['clicks'], errors='coerce').fillna(0).astype(int)
    
    if not df_prev.empty:
        df_prev['clicks'] = pd.to_numeric(df_prev['clicks'], errors='coerce').fillna(0).astype(int)

    curr_clicks = df_current['clicks'].sum()
    prev_clicks = df_prev['clicks'].sum() if not df_prev.empty else 0
    
    diff = curr_clicks - prev_clicks
    growth_rate = (diff / prev_clicks * 100) if prev_clicks > 0 else 0.0
        
    return {
        'current_clicks': curr_clicks,
        'prev_clicks': prev_clicks,
        'diff': diff,
        'growth_rate': round(growth_rate, 1),
        'df_current': df_current
    }

def create_chart(df, output_path='reports/chart.png'):
    # データチェック：ここが古いコードでエラーになっていた箇所（Line 86付近）
    if df.empty or 'date' not in df.columns:
        print("DEBUG: グラフ作成をスキップ（有効なデータなし）")
        return

    try:
        plt.figure(figsize=(10, 5))
        df['date'] = pd.to_datetime(df['date'])
        df = df.sort_values('date')
        plt.plot(df['date'], df['clicks'], marker='o', label='Clicks')
        plt.title('Weekly Clicks')
        plt.grid(True)
        plt.legend()
        plt.savefig(output_path)
        plt.close()
    except Exception as e:
        print(f"Chart Error: {e}")

def generate_html(metrics):
    template_str = """
    <html>
    <head><title>SEO Weekly Report</title></head>
    <body>
    <h1>SEO Weekly Report</h1>
    <p>Period: {{ start_date }} - {{ end_date }}</p>
    <div style="border:1px solid #ccc; padding:20px; margin-bottom:20px;">
        <h2>Clicks: {{ metrics.current_clicks }} 
        <small>(Prev: {{ metrics.prev_clicks }})</small></h2>
        <p>WoW: {{ metrics.diff }} ({{ metrics.growth_rate }}%)</p>
    </div>
    {% if has_chart %}
    <div><img src="chart.png" style="max-width:100%;"></div>
    {% else %}
    <p>No chart available (Data empty)</p>
    {% endif %}
    </body></html>
    """
    
    t = jinja2.Template(template_str)
    has_chart = os.path.exists('reports/chart.png')
    
    html = t.render(
        metrics=metrics, 
        start_date=os.environ.get("START_DATE"), 
        end_date=os.environ.get("END_DATE"), 
        has_chart=has_chart
    )
    
    os.makedirs('reports', exist_ok=True)
    with open('reports/index.html', 'w', encoding='utf-8') as f:
        f.write(html)

def main():
    print("--- STARTING WEEKLY REPORT (2026 FIXED VERSION) ---")
    site_url = os.environ.get("GSC_SITE_URL")
    
    # URL形式の自動補正チェック
    if site_url and not (site_url.startswith("http") or site_url.startswith("sc-domain:")):
        print(f"WARNING: URL形式が不正の可能性があります: {site_url}")

    service = get_service_client()
    
    # 2026年の日付範囲（環境変数から取得）
    start_date = os.environ.get("START_DATE")
    end_date = os.environ.get("END_DATE")
    
    df_current = fetch_gsc_data(service, site_url, start_date, end_date)
    df_prev = fetch_gsc_data(service, site_url, os.environ.get("PREV_START_DATE"), os.environ.get("PREV_END_DATE"))
    
    metrics = process_data(df_current, df_prev)
    create_chart(metrics['df_current'])
    generate_html(metrics)
    
    print("SUCCESS: Report generated at reports/index.html")

if __name__ == "__main__":
    main()
