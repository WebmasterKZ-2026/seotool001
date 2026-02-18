import os
import json
import pandas as pd
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
import matplotlib.pyplot as plt
import jinja2

# 日本語フォント設定（文字化け対策）
plt.rcParams['font.family'] = 'Noto Sans CJK JP' 

def get_service_client():
    sa_json_str = os.environ.get("GOOGLE_SA_JSON")
    if not sa_json_str:
        raise ValueError("Critical: 環境変数 GOOGLE_SA_JSON が設定されていません。")
    
    sa_info = json.loads(sa_json_str)
    creds = service_account.Credentials.from_service_account_info(sa_info)
    service = build('webmasters', 'v3', credentials=creds)
    return service

def fetch_gsc_data(service, site_url, start_date, end_date):
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
        
        # 【修正】日付データの取り出しを強化
        # GSC APIは ['2024-01-01'] のようなリスト形式で返してくるため、中身を取り出す
        if 'keys' in df.columns:
            df['date'] = df['keys'].apply(lambda x: x if isinstance(x, list) and len(x) > 0 else x)
        else:
            print("DEBUG: 'keys' カラムが見つかりません。カラム一覧:", df.columns)
            
        return df
        
    except Exception as e:
        print(f"DEBUG: APIリクエストでエラー発生: {e}")
        return pd.DataFrame()

def process_data(df_current, df_prev):
    # データが空の場合の安全策
    if df_current.empty:
        return {'current_clicks': 0, 'prev_clicks': 0, 'diff': 0, 'growth_rate': 0, 'df_current': df_current}

    # 数値変換
    df_current['clicks'] = pd.to_numeric(df_current['clicks'], errors='coerce').fillna(0).astype(int)
    
    if not df_prev.empty:
        df_prev['clicks'] = pd.to_numeric(df_prev['clicks'], errors='coerce').fillna(0).astype(int)

    curr_clicks = df_current['clicks'].sum()
    prev_clicks = df_prev['clicks'].sum() if not df_prev.empty else 0
    
    diff = curr_clicks - prev_clicks
    if prev_clicks > 0:
        growth_rate = (diff / prev_clicks) * 100
    else:
        growth_rate = 0.0
        
    return {
        'current_clicks': curr_clicks,
        'prev_clicks': prev_clicks,
        'diff': diff,
        'growth_rate': round(growth_rate, 1),
        'df_current': df_current
    }

def create_chart(df, output_path='reports/chart.png'):
    # データが無い、または日付カラムが無い場合はスキップ（エラー回避）
    if df.empty or 'date' not in df.columns:
        print("DEBUG: グラフ作成をスキップします（データ不足）")
        return
        
    plt.figure(figsize=(10, 5))
    
    # 日付変換とソート
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    
    plt.plot(df['date'], df['clicks'], marker='o', label='クリック数')
    plt.title('クリック数推移 (Last 7 Days)')
    plt.grid(True)
    plt.legend()
    plt.savefig(output_path)
    plt.close()

def generate_html(metrics):
    template_str = """
    <html>
    <head>
        <title>Weekly SEO Report</title>
        <style>
            body { font-family: sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            .card { border: 1px solid #ddd; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
            .metric { font-size: 2em; font-weight: bold; }
            .positive { color: green; }
            .negative { color: red; }
        </style>
    </head>
    <body>
        <h1>SEO週間レポート</h1>
        <p>集計期間: {{ start_date }} 〜 {{ end_date }}</p>
        
        <div class="card">
            <h2>クリック数 (WoW)</h2>
            <div class="metric">
                {{ metrics.current_clicks }} 
                <span style="font-size: 0.5em; color: gray;">(前週: {{ metrics.prev_clicks }})</span>
            </div>
            <p class="{{ 'positive' if metrics.diff >= 0 else 'negative' }}">
                {{ '+' if metrics.diff >= 0 else '' }}{{ metrics.diff }} 
                ({{ '+' if metrics.growth_rate >= 0 else '' }}{{ metrics.growth_rate }}%)
            </p>
        </div>
        
        <div class="card">
            <h2>推移グラフ</h2>
            {% if has_chart %}
            <img src="chart.png" style="max-width: 100%;">
            {% else %}
            <p>データ不足のためグラフを表示できません</p>
            {% endif %}
        </div>
        
        <p><small>Generated at: {{ timestamp }}</small></p>
    </body>
    </html>
    """
    
    template = jinja2.Template(template_str)
    
    has_chart = os.path.exists('reports/chart.png')
    
    html = template.render(
        metrics=metrics,
        start_date=os.environ.get("START_DATE"),
        end_date=os.environ.get("END_DATE"),
        has_chart=has_chart,
        timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )
    
    os.makedirs('reports', exist_ok=True)
    with open('reports/index.html', 'w', encoding='utf-8') as f:
        f.write(html)

def main():
    site_url = os.environ.get("GSC_SITE_URL")
    # ドメインプロパティ対応：sc-domain: がついていればそのまま、なければ確認
    if not site_url.startswith("http") and not site_url.startswith("sc-domain:"):
        print(f"WARNING: URLの形式を確認してください: {site_url}")

    start_date = os.environ.get("START_DATE")
    end_date = os.environ.get("END_DATE")
    prev_start_date = os.environ.get("PREV_START_DATE")
    prev_end_date = os.environ.get("PREV_END_DATE")

    print(f"Target Site: {site_url}")
    
    try:
        service = get_service_client()
        
        df_current = fetch_gsc_data(service, site_url, start_date, end_date)
        df_prev = fetch_gsc_data(service, site_url, prev_start_date, prev_end_date)
        
        metrics = process_data(df_current, df_prev)
        
        create_chart(metrics['df_current'])
        generate_html(metrics)
        
        print("レポート生成完了: reports/index.html")
        
    except Exception as e:
        print(f"Main Loop Error: {e}")
        raise

if __name__ == "__main__":
    main()
