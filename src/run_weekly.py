# VERSION: FINAL-CHECK-2026
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
    print(f"DEBUG: Fetching data for {site_url} ({start_date} ~ {end_date})...")
    request = {'startDate': start_date, 'endDate': end_date, 'dimensions': ['date'], 'rowLimit': 25000}
    
    try:
        response = service.searchanalytics().query(siteUrl=site_url, body=request).execute()
        rows = response.get('rows', [])
        
        if not rows:
            print("DEBUG: データが0件でした")
            return pd.DataFrame()
        
        df = pd.DataFrame(rows)
        # 日付カラムの修正（ここが重要！）
        if 'keys' in df.columns:
            df['date'] = df['keys'].apply(lambda x: x if isinstance(x, list) else x)
        return df
    except Exception as e:
        # ここが最新版のメッセージです
        print(f"DEBUG: API Error: {e}")
        return pd.DataFrame()

def main():
    print("--- STARTING FINAL VERSION ---")
    site_url = os.environ.get("GSC_SITE_URL")
    service = get_service_client()
    
    # 日付取得
    start = os.environ.get("START_DATE")
    end = os.environ.get("END_DATE")
    
    # データ取得実行
    df = fetch_gsc_data(service, site_url, start, end)
    
    if not df.empty and 'date' in df.columns:
        print(f"SUCCESS: データ取得成功！ {len(df)}件")
        # グラフ作成などの処理へ続く（今回は省略してエラー確認を優先）
        # レポート用ダミー作成
        os.makedirs('reports', exist_ok=True)
        with open('reports/index.html', 'w', encoding='utf-8') as f:
            f.write("<html><body><h1>Success!</h1><p>Data retrieved.</p></body></html>")
    else:
        print("WARNING: データが空、またはエラーのためレポートは空です")
        os.makedirs('reports', exist_ok=True)
        with open('reports/index.html', 'w') as f: f.write("No Data")

if __name__ == "__main__":
    main()
