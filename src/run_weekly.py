# VERSION: FINAL-FULL-FIX-V2
import os
import json
import pandas as pd
from datetime import datetime, timedelta
from google.oauth2 import service_account
from googleapiclient.discovery import build
import matplotlib.pyplot as plt
import jinja2

# 日本語フォント設定（環境に合わせて回避設定も追加）
try:
    plt.rcParams['font.family'] = 'Noto Sans CJK JP'
except:
    pass

def get_service_client():
    sa_json_str = os.environ.get("GOOGLE_SA_JSON")
    if not sa_json_str:
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
    """
    データ取得関数：データが0件でも必ずカラム付きの空DFを返す安全仕様
    """
    print(f"DEBUG: Fetching data for {site_url} ({start_date} ~ {end_date})...")
    
    # 必須: dimensionsにdateを入れる
    request = {
        'startDate': start_date, 
        'endDate': end_date, 
        'dimensions': ['date'], 
        'rowLimit': 25000
    }
    
    # 空の場合のデフォルト値（これがないとKeyErrorになる）
    empty_df = pd.DataFrame(columns=['date', 'clicks', 'impressions', 'ctr', 'position'])
    
    try:
        response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
        rows = response.get('rows', [])
        
        if not rows:
            print(f"DEBUG: {start_date} の期間はデータが0件です。")
            return empty_df
        
        df = pd.DataFrame(rows)
        
        # 'keys' カラム処理（API仕様対応）
        if 'keys' in df.columns:
            df['date'] = df['keys'].apply(lambda x: x[0] if isinstance(x, list) and len(x) > 0 else x)
        
        # ここで日付型変換とカラム整理
        if 'date' in df.columns:
            df['date'] = pd.to_datetime(df['date'])
            # 必要なカラムだけ返す
            cols = [c for c in ['date', 'clicks', 'impressions', 'ctr', 'position'] if c in df.columns]
            return df[cols]
        else:
            return empty_df

    except Exception as e:
        print(f"DEBUG: API Error: {e}")
        return empty_df

def create_chart(df):
    """
    グラフ作成関数：ここがエラーの発生源でした。
    データが空の場合は即座に終了するガードを追加しています。
    """
    # 【最重要ガード】データが空、またはdate列がない場合は何もしない
    if df is None or df.empty or 'date' not in df.columns:
        print("WARNING: グラフ作成用データが空のため、グラフ作成をスキップします。")
        return

    print("DEBUG: グラフ作成を開始します...")
    try:
        # 日付変換（念のため再確認）
        df = df.copy()
        df['date'] = pd.to_datetime(df['date'])
        
        plt.figure(figsize=(10, 5))
        plt.plot(df['date'], df['clicks'], label='Clicks', marker='o')
        plt.title('Weekly Clicks')
        plt.xlabel('Date')
        plt.ylabel('Clicks')
        plt.grid(True)
        plt.legend()
        
        # 保存
        os.makedirs('reports', exist_ok=True)
        plt.savefig('reports/weekly_chart.png')
        plt.close()
        print("SUCCESS: グラフを保存しました (reports/weekly_chart.png)")
    except Exception as e:
        print(f"ERROR: グラフ作成中にエラーが発生しました: {e}")

def main():
    print("--- STARTING WEEKLY REPORT (FULL FIX) ---")
    site_url = os.environ.get("GSC_SITE_URL")
    service = get_service_client()
    
    if not service:
        return

    # 今週（環境変数）
    start = os.environ.get("START_DATE")
    end = os.environ.get("END_DATE")
    
    # 先週（自動計算）
    try:
        start_dt = datetime.strptime(start, '%Y-%m-%d')
        end_dt = datetime.strptime(end, '%Y-%m-%d')
        prev_start = (start_dt - timedelta(days=7)).strftime('%Y-%m-%d')
        prev_end = (end_dt - timedelta(days=7)).strftime('%Y-%m-%d')
    except:
        # 日付が入っていない場合のダミー
        prev_start, prev_end = "2000-01-01", "2000-01-01"

    # 1. データ取得
    df_current = fetch_gsc_data(service, site_url, start, end)
    df_prev = fetch_gsc_data(service, site_url, prev_start, prev_end)
    
    # 2. メトリクス計算用辞書（元のコードの構造に合わせる）
    metrics = {
        'df_current': df_current,
        'df_prev': df_prev
    }

    # 3. レポート分岐
    os.makedirs('reports', exist_ok=True)
    
    # データが空の場合のハンドリング
    if df_current.empty:
        print("RESULT: データが取得できませんでした（集計待ちの可能性があります）。")
        with open('reports/index.html', 'w', encoding='utf-8') as f:
            f.write("<html><body><h1>No Data Available</h1><p>GSC data not ready yet.</p></body></html>")
    else:
        print(f"SUCCESS: データ取得成功 ({len(df_current)} records)")
        # グラフ作成（ガード付き関数を呼び出し）
        create_chart(df_current)
        
        # レポート出力
        total_clicks = df_current['clicks'].sum()
        with open('reports/index.html', 'w', encoding='utf-8') as f:
            html = f"""
            <html>
            <body>
                <h1>Weekly Report ({start} ~ {end})</h1>
                <p>Total Clicks: {total_clicks}</p>
                <img src='weekly_chart.png' style='max-width:100%;'>
            </body>
            </html>
            """
            f.write(html)
        print("SUCCESS: レポート生成完了")

if __name__ == "__main__":
    main()
