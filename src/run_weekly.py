import os
import json
import pandas as pd
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
import matplotlib.pyplot as plt
import jinja2

# ---------------------------------------------------------
# 1. 環境設定と認証
# ---------------------------------------------------------
def get_service_client():
    sa_json_str = os.environ.get("GOOGLE_SA_JSON")
    if not sa_json_str:
        raise ValueError("環境変数 GOOGLE_SA_JSON が設定されていません。")
    
    sa_info = json.loads(sa_json_str)
    creds = service_account.Credentials.from_service_account_info(sa_info)
    service = build('webmasters', 'v3', credentials=creds)
    return service

# ---------------------------------------------------------
# 2. データの取得 (ここを修正しました！)
# ---------------------------------------------------------
def fetch_gsc_data(service, site_url, start_date, end_date):
    print(f"Fetching data for {site_url} from {start_date} to {end_date}...")
    
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
            print("データが見つかりませんでした (Rows is empty)")
            return pd.DataFrame()
        
        df = pd.DataFrame(rows)
        
        # 【修正ポイント】GSCから返ってくる 'keys' リストから日付を取り出す
        if 'keys' in df.columns:
            df['date'] = df['keys'].apply(lambda x: x)
            
        return df
        
    except Exception as e:
        print(f"APIリクエスト中にエラーが発生しました: {e}")
        # エラーの詳細を知るために空のDFではなくエラーを再送出しても良いが、
        # ここでは空を返して処理を止めないようにする
        return pd.DataFrame()

# ---------------------------------------------------------
# 3. データの加工・計算
# ---------------------------------------------------------
def process_data(df_current, df_prev):
    if not df_current.empty:
        df_current['clicks'] = df_current['clicks'].astype(int)
        df_current['impressions'] = df_current['impressions'].astype(int)
    
    if not df_prev.empty:
        df_prev['clicks'] = df_prev['clicks'].astype(int)

    curr_clicks = df_current['clicks'].sum() if not df_current.empty else 0
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

# ---------------------------------------------------------
# 4. グラフ作成
# ---------------------------------------------------------
def create_chart(df, output_path='reports/chart.png'):
    if df.empty or 'date' not in df.columns:
        print("グラフ作成用のデータがありません。")
        return
        
    plt.figure(figsize=(10, 5))
    plt.rcParams['font.family'] = 'Noto Sans CJK JP' 
    
    df['date'] = pd.to_datetime(df['date'])
    df = df.sort_values('date')
    
    plt.plot(df['date'], df['clicks'], marker='o', label='クリック数')
    plt.title('過去7日間のクリック数推移')
    plt.grid(True)
    plt.legend()
    plt.savefig(output_path)
    plt.close()

# ---------------------------------------------------------
# 5. HTMLレポート生成
# ---------------------------------------------------------
def generate_html(metrics):
    template_str = """
    <html>
    <head>
        <title>Weekly SEO Report</title>
        <style>
            body { font-family: "Noto Sans CJK JP", sans-serif; max-width: 800px; margin: 0 auto; padding: 20px; }
            .card { border: 1px solid #ddd; padding: 20px; border-radius: 8px; margin-bottom: 20px; }
            .metric { font-size: 2em; font-weight: bold; }
            .positive { color: green; }
            .negative { color: red; }
        </style>
    </head>
    <body>
        <h1>SEO週間レポート</h1>
        <p>集計期間: {{ metrics.start_date }} 〜 {{ metrics.end_date }}</p>
        
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
            <img src="chart.png" style="max-width: 100%;">
        </div>
        
        <p><small>Generated at: {{ timestamp }}</small></p>
    </body>
    </html>
    """
    
    template = jinja2.Template(template_str)
    
    # metrics辞書に日付情報を追加
    metrics['start_date'] = os.environ.get("START_DATE")
    metrics['end_date'] = os.environ.get("END_DATE")
    
    html = template.render(
        metrics=metrics,
        timestamp=datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    )
    
    os.makedirs('reports', exist_ok=True)
    with open('reports/index.html', 'w', encoding='utf-8') as f:
        f.write(html)

# ---------------------------------------------------------
# メイン処理
# ---------------------------------------------------------
def main():
    site_url = os.environ.get("GSC_SITE_URL")
    start_date = os.environ.get("START_DATE")
    end_date = os.environ.get("END_DATE")
    prev_start_date = os.environ.get("PREV_START_DATE")
    prev_end_date = os.environ.get("PREV_END_DATE")

    print(f"Target Site: {site_url}")
    
    try:
        service = get_service_client()
        
        # データ取得
        df_current = fetch_gsc_data(service, site_url, start_date, end_date)
        df_prev = fetch_gsc_data(service, site_url, prev_start_date, prev_end_date)
        
        # データ処理
        metrics = process_data(df_current, df_prev)
        
        # グラフ作成
        create_chart(metrics['df_current'])
        
        # レポート作成
        generate_html(metrics)
        
        print("レポート生成完了: reports/index.html")
        
    except Exception as e:
        print(f"エラーが発生しました: {e}")
        raise

if __name__ == "__main__":
    main()
