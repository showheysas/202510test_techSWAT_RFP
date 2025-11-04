"""
アプリケーション設定管理モジュール
環境変数の読み込み、クライアント初期化、ディレクトリパスの定義
"""
import os
from pathlib import Path
from dotenv import load_dotenv
from openai import OpenAI
from slack_sdk import WebClient

# 環境変数の読み込み
load_dotenv()

# =========================
# 環境変数から設定を読み込み
# =========================

# OpenAI設定
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")

# Slack設定
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
DEFAULT_SLACK_CHANNEL = os.getenv("SLACK_CHANNEL_ID", "")

# Gmail設定
GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_PASS = os.getenv("GMAIL_PASS", "")

# Google Drive設定
GOOGLE_DRIVE_FOLDER_ID = os.getenv("GOOGLE_DRIVE_FOLDER_ID", "")
# サービスアカウント認証情報（JSONファイルの内容を文字列として設定可能・推奨）
GOOGLE_SERVICE_ACCOUNT_JSON = os.getenv("GOOGLE_SERVICE_ACCOUNT_JSON", "")
# サービスアカウント認証情報（ファイルパス指定）
GOOGLE_SERVICE_ACCOUNT_PATH = os.getenv("GOOGLE_SERVICE_ACCOUNT_PATH", "")

# Notta Google Drive連携
NOTTA_DRIVE_FOLDER_ID = os.getenv("NOTTA_DRIVE_FOLDER_ID", "")
GOOGLE_DRIVE_WATCH_ENABLED = os.getenv("GOOGLE_DRIVE_WATCH_ENABLED", "false").lower() == "true"
# Google Drive Webhook検証用シークレット
GOOGLE_DRIVE_WEBHOOK_SECRET = os.getenv("GOOGLE_DRIVE_WEBHOOK_SECRET", "")
# Google Drive ポーリング間隔（秒、デフォルト1分）
GOOGLE_DRIVE_POLL_INTERVAL = int(os.getenv("GOOGLE_DRIVE_POLL_INTERVAL", "60"))

# Slack リマインド設定
SLACK_USER_MAP_JSON = os.getenv("SLACK_USER_MAP_JSON", "")  # 例: {"田中":"U0123...", "佐藤":"U0456..."}
DEFAULT_REMIND_HOUR = int(os.getenv("DEFAULT_REMIND_HOUR", "10"))  # 期限日に何時にリマインドするか(ローカル時間)

# =========================
# 設定の検証
# =========================
if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY が未設定です。")
if not SLACK_BOT_TOKEN:
    raise RuntimeError("SLACK_BOT_TOKEN が未設定です。")
if not GMAIL_USER or not GMAIL_PASS:
    print("⚠️ Gmail設定が未設定です。メール送信はスキップされます。")

# =========================
# クライアント初期化
# =========================
client_oa = OpenAI(api_key=OPENAI_API_KEY)
client_slack = WebClient(token=SLACK_BOT_TOKEN)

# =========================
# ディレクトリパスの定義
# =========================
BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
TRANS_DIR = DATA_DIR / "transcripts"
SUMM_DIR = DATA_DIR / "summaries"
PDF_DIR = DATA_DIR / "pdf"

# ディレクトリの作成
for d in (UPLOAD_DIR, TRANS_DIR, SUMM_DIR, PDF_DIR):
    d.mkdir(parents=True, exist_ok=True)

