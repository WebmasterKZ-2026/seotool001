# VERSION: FINAL-FIX-COMPLETE
import os
import json
import pandas as pd
from datetime import datetime
from google.oauth2 import service_account
from googleapiclient.discovery import build
import matplotlib.pyplot as plt
import jinja2

# 日本語フォント設定
plt.rcParams['font.family'] = 'Noto Sans CJK JP' 

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
    GSCからデータを取得し、必ず正しいカラムを持つDataFrameを返す関数
    """
    print(f"DEBUG: Fetching data for {site_url} ({start_date} ~ {end_date})...")
    
    # dimensionsに 'date' を指定
    request = {
        'startDate': start_date, 
        'endDate': end_date, 
        'dimensions': ['date'], 
        'rowLimit': 25000
    }
    
    # 空のときに返す基本の形（これがないとKeyErrorになります）
    empty_df = pd.DataFrame(columns=['date', 'clicks', 'impressions', 'ctr', 'position'])
    
    try:
        response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
        rows = response.get('rows', [])
        
        if not rows:
            print("DEBUG: 取得データが0件です。空のテーブルを返します。")
            return empty_df
        
        df = pd.DataFrame(rows)
        
        # 'keys' カラムが存在するかチェック
        if 'keys' not in df.columns:
            return empty_df

        # APIの仕様上 keys はリスト(['2024-01-01'])なので、中身を取り出す
        df['date'] = df['keys'].apply(lambda x: x[0] if isinstance(x, list) and len(x) > 0 else x)
        
        # 日付型に変換
        df['date'] = pd.to_datetime(df['date'])
        
        # 不要な keys 列を削除して整理
        output_df = df[['date', 'clicks', 'impressions', 'ctr', 'position']].copy()
        return output_df

    except Exception as e:
        print(f"DEBUG: API Error: {e}")
        return empty_df

def create_chart(df):
    """
    グラフ作成関数（データが空の場合はスキップするガード付き）
    """
    if df.empty:
        print("WARNING: グラフ作成用データが空のため、作成をスキップします。")
        return

    print("DEBUG: グラフ作成を開始します...")
    try:
        plt.figure(figsize=(10, 5))
        plt.plot(df['date'], df['clicks'], label='Clicks', marker='o')
        plt.title('Weekly Clicks')
        plt.xlabel('Date')
        plt.ylabel('Clicks')
        plt.grid(True)
        plt.legend()
        
        # 保存ディレクトリ作成
        os.makedirs('reports', exist_ok=True)
        plt.savefig('reports/weekly_chart.png')
        plt.close()
        print("SUCCESS: グラフを保存しました (reports/weekly_chart.png)")
    except Exception as e:
        print(f"ERROR: グラフ作成中にエラーが発生しました: {e}")

def main():
    print("--- STARTING WEEKLY REPORT (SAFE MODE) ---")
    site_url = os.environ.get("GSC_SITE_URL")
    service = get_service_client()
    
    if not service:
        return

    # 環境変数から日付取得
    start = os.environ.get("START_DATE")
    end = os.environ.get("END_DATE")
    
    # 1. データ取得
    df = fetch_gsc_data(service, site_url, start, end)
    
    # 2. データチェック
    if df.empty:
        print("RESULT: データが存在しませんでした。レポートは空になります。")
        # 空レポートの作成処理
        os.makedirs('reports', exist_ok=True)
        with open('reports/index.html', 'w', encoding='utf-8') as f:
            f.write("<html><body><h1>No Data Available</h1><p>指定期間のデータはありませんでした。</p></body></html>")
    else:
        print(f"SUCCESS: {len(df)} 件のデータを取得しました。")
        
        # 3. グラフ作成（ここでエラーが起きないよう関数側でガード済み）
        create_chart(df)
        
        # 4. レポート作成（簡易版）
        os.makedirs('reports', exist_ok=True)
        with open('reports/index.html', 'w', encoding='utf-8') as f:
            total_clicks = df['clicks'].sum()
            f.write(f"<html><body><h1>Weekly Report</h1><p>Total Clicks: {total_clicks}</p><img src='weekly_chart.png'></body></html>")
        print("SUCCESS: レポート生成完了")

if __name__ == "__main__":
    main()
