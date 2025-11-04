import os
import sys
import json
import uuid
import shutil
import time
import hmac
import hashlib
import re
import asyncio
from pathlib import Path
from typing import Optional
from datetime import datetime, timedelta
try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:
    ZoneInfo = None

from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException, Request, Header
from fastapi.responses import JSONResponse
# 注: dotenv.load_dotenv() は config.py で実行済み

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ---- Gmail, Drive ----
import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.application import MIMEApplication
from google.oauth2 import service_account
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from googleapiclient.errors import HttpError

# =========================
# リファクタリングされたモジュールのインポート
# =========================
# Phase 1: 基盤構築
# Azure App Serviceでは app.main:app で起動するため、app. プレフィックスが必要
try:
    # Azure App Service環境（プロジェクトルートから実行）
    from app.config import (
        OPENAI_API_KEY, SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, DEFAULT_SLACK_CHANNEL,
        GMAIL_USER, GMAIL_PASS,
        GOOGLE_DRIVE_FOLDER_ID, GOOGLE_SERVICE_ACCOUNT_JSON, GOOGLE_SERVICE_ACCOUNT_PATH,
        NOTTA_DRIVE_FOLDER_ID, GOOGLE_DRIVE_WATCH_ENABLED, GOOGLE_DRIVE_WEBHOOK_SECRET,
        GOOGLE_DRIVE_POLL_INTERVAL,
        SLACK_USER_MAP_JSON, DEFAULT_REMIND_HOUR,
        client_oa, client_slack,
        BASE_DIR, DATA_DIR, UPLOAD_DIR, TRANS_DIR, SUMM_DIR, PDF_DIR
    )
    from app.models import Draft
    from app.utils.storage import save_json
    from app.services.openai_service import transcribe_audio, summarize_to_structured
    from app.services.slack_service import (
        verify_slack_signature,
        build_minutes_preview_blocks,
        build_edit_modal,
        build_tasks_blocks,
        parse_tasks_from_actions,
        post_slack_draft
    )
except ImportError:
    # ローカル開発環境（appディレクトリから直接実行）
    from config import (
        OPENAI_API_KEY, SLACK_BOT_TOKEN, SLACK_SIGNING_SECRET, DEFAULT_SLACK_CHANNEL,
        GMAIL_USER, GMAIL_PASS,
        GOOGLE_DRIVE_FOLDER_ID, GOOGLE_SERVICE_ACCOUNT_JSON, GOOGLE_SERVICE_ACCOUNT_PATH,
        NOTTA_DRIVE_FOLDER_ID, GOOGLE_DRIVE_WATCH_ENABLED, GOOGLE_DRIVE_WEBHOOK_SECRET,
        GOOGLE_DRIVE_POLL_INTERVAL,
        SLACK_USER_MAP_JSON, DEFAULT_REMIND_HOUR,
        client_oa, client_slack,
        BASE_DIR, DATA_DIR, UPLOAD_DIR, TRANS_DIR, SUMM_DIR, PDF_DIR
    )
    from models import Draft
    from utils.storage import save_json
    from services.openai_service import transcribe_audio, summarize_to_structured
    from services.slack_service import (
        verify_slack_signature,
        build_minutes_preview_blocks,
        build_edit_modal,
        build_tasks_blocks,
        parse_tasks_from_actions,
        post_slack_draft
    )

# =========================
# グローバル変数（メモリ管理）
# =========================
DRAFT_META = {}
# Drive Push通知チャンネル情報の保存（メモリ）
DRIVE_WATCH_CHANNEL_INFO = {}
# ポーリングタスクの停止フラグ
_polling_task = None

app = FastAPI(title="Minutes Ingest + PDF(ReportLab) + Gmail + Drive")

# =========================
# 内部ヘルパ
# =========================
# 注: transcribe_audio と summarize_to_structured は services/openai_service.py からインポート済み
# 注: save_json は utils/storage.py からインポート済み
# 注: Slack関連の関数は services/slack_service.py からインポート済み

# リマインド機能用ヘルパー関数
def _tz():
    """JST固定（必要なら環境変数で切替）"""
    if ZoneInfo:
        return ZoneInfo("Asia/Tokyo")
    # フォールバック：naive扱い
    return None

def _parse_due_to_dt(due_str: Optional[str]) -> Optional[datetime]:
    """
    '10/25' '2025/10/25' '2025-10-25 15:00' などをJST日付に解釈。
    時刻未指定なら DEFAULT_REMIND_HOUR:00 を設定。
    """
    if not due_str:
        return None
    s = due_str.strip()
    # よくある表記を順にトライ
    fmt_candidates = [
        "%Y-%m-%d %H:%M", "%Y/%m/%d %H:%M",
        "%Y-%m-%d", "%Y/%m/%d",
        "%m/%d",  # 年なし（今年扱い）
    ]
    now = datetime.now(_tz())
    for fmt in fmt_candidates:
        try:
            dt = datetime.strptime(s, fmt)
            # 年なし → 今年
            if fmt == "%m/%d":
                dt = dt.replace(year=now.year)
            # 時刻なければデフォ時刻
            if fmt in ("%Y-%m-%d", "%Y/%m/%d", "%m/%d"):
                dt = dt.replace(hour=DEFAULT_REMIND_HOUR, minute=0)
            # タイムゾーン付与
            if _tz():
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=_tz())
            return dt
        except ValueError:
            continue
    return None

def _epoch(dt: datetime) -> Optional[int]:
    """datetimeをUTC epoch（秒）に変換"""
    if not dt:
        return None
    # SlackはUTC epoch（秒）
    if dt.tzinfo is None and _tz():
        dt = dt.replace(tzinfo=_tz())
    return int(dt.timestamp())

def _load_user_map() -> dict:
    """環境変数からSlackユーザーマップを読み込み"""
    try:
        return json.loads(SLACK_USER_MAP_JSON) if SLACK_USER_MAP_JSON else {}
    except Exception:
        return {}

def _resolve_slack_user_id(name: Optional[str]) -> Optional[str]:
    """
    '田中(PM)' → '田中' 抜き出し → 環境変数マップで Slack ID に解決。
    """
    if not name:
        return None
    base = re.sub(r"\(.*?\)", "", name).strip()
    m = _load_user_map()
    return m.get(base)

def schedule_task_reminders(channel: str, thread_ts: str, d: Draft):
    """
    各タスクについてリマインドをスケジュール。
    - 期日の前日 10:00
    - 期日 1時間前
    投稿先：同スレッド。担当者Slack IDが分かればメンション付与。
    """
    tasks = parse_tasks_from_actions(d.actions)
    if not tasks: 
        return

    for t in tasks:
        due_dt = _parse_due_to_dt(t.get("due"))
        if not due_dt:
            continue

        # 2回分の候補
        dt_prev_day = (due_dt - timedelta(days=1)).replace(hour=DEFAULT_REMIND_HOUR, minute=0)
        dt_one_hour = due_dt - timedelta(hours=1)

        for when_dt in [dt_prev_day, dt_one_hour]:
            post_at = _epoch(when_dt)
            if not post_at: 
                continue
            # 過去はスキップ
            now_epoch = int(datetime.now(_tz()).timestamp()) if _tz() else int(time.time())
            if post_at <= now_epoch:
                continue

            mention = ""
            uid = _resolve_slack_user_id(t.get("assignee"))
            if uid:
                mention = f"<@{uid}> "
            text = (f"{mention}リマインド：*{t['title']}* "
                    f"（担当: {t.get('assignee') or '未定'} / 期限: {t.get('due') or '未定'}）")

            try:
                client_slack.chat_scheduleMessage(
                    channel=channel,
                    text=text,
                    post_at=post_at,
                    thread_ts=thread_ts
                )
            except SlackApiError as e:
                print(f"[Slack] scheduleMessage failed: {e}")

# 注: post_slack_draft と build_edit_modal は services/slack_service.py からインポート済み

# 注: save_json は utils/storage.py からインポート済み

def _escape_html(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# =========================
# PDF生成（リッチ版）: 議事録
# =========================
async def create_pdf_async(d: Draft, out_path: Path):
    """
    リッチレイアウト版（1カラム、メタ情報カード、セクション見出しバー、箇条書き）
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.lib.units import mm

    # ---- ページとスタイル
    PAGE_W, PAGE_H = A4
    MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B = 20*mm, 20*mm, 18*mm, 18*mm
    TITLE_SIZE, H_SIZE, BODY_SIZE, META_SIZE, SMALL = 16, 12, 10.5, 10, 9
    LINE_GAP, PARA_GAP, SEC_GAP = 5.2*mm, 3.2*mm, 6.5*mm

    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    c = canvas.Canvas(str(out_path), pagesize=A4)

    # 共通色
    C_PRIMARY = colors.HexColor("#1f2937")   # 見出し文字
    C_ACCENT  = colors.HexColor("#2563eb")   # 青アクセント
    C_BORDER  = colors.HexColor("#e5e7eb")   # 薄い罫線
    C_MUTED   = colors.HexColor("#6b7280")   # 補助文字
    C_BAR     = colors.HexColor("#f3f4f6")   # セクション見出しバー

    # 文字幅ラップ（CJK向け、既存のロジックを簡潔化）
    def wrap_cjk(text: str, font_name: str, font_size: int, max_width: float):
        from reportlab.pdfbase import pdfmetrics
        if not text:
            return ["-"]
        lines = []
        for raw in (text or "").splitlines():
            if raw == "":
                lines.append("")
                continue
            buf = ""
            for ch in raw:
                nb = buf + ch
                if pdfmetrics.stringWidth(nb, font_name, font_size) <= max_width:
                    buf = nb
                else:
                    if buf:
                        lines.append(buf); buf = ch
                    else:
                        lines.append(ch); buf = ""
            if buf or raw == "":
                lines.append(buf)
        return lines

    # 余白計算
    X0, X1 = MARGIN_L, PAGE_W - MARGIN_R
    CONTENT_W = X1 - X0
    y = PAGE_H - MARGIN_T

    # ヘッダ（タイトル）
    c.setFont("HeiseiKakuGo-W5", TITLE_SIZE)
    c.setFillColor(C_PRIMARY)
    c.drawString(X0, y, "議事録")
    c.setFont("HeiseiKakuGo-W5", SMALL)
    c.setFillColor(C_MUTED)
    c.drawRightString(X1, y, d.datetime_str or "")
    y -= 8*mm

    # メタ情報カード（薄い枠＋フィールド2列）
    def meta_row(label: str, value: str, y):
        c.setFont("HeiseiKakuGo-W5", META_SIZE)
        c.setFillColor(C_MUTED)
        c.drawString(X0+6*mm, y, f"{label}")
        c.setFillColor(colors.black)
        c.drawString(X0+30*mm, y, value or "-")
        return y - 6*mm

    # カード枠
    card_top = y
    card_h = 28*mm
    c.setStrokeColor(C_BORDER); c.setLineWidth(0.6)
    # ReportLabにはroundRectがないため、通常のrectを使用
    c.rect(X0, card_top - card_h, CONTENT_W, card_h, stroke=1, fill=0)

    y = card_top - 7*mm
    y = meta_row("会議名",  d.meeting_name or d.title or "（無題）", y)
    y = meta_row("日時",    d.datetime_str or "-", y)
    y = meta_row("参加者",  d.participants or "-", y)
    y = meta_row("目的",    d.purpose or "-", y)

    y -= 3*mm

    # ページ残量チェック
    def new_page():
        nonlocal y
        c.showPage()
        c.setFont("HeiseiKakuGo-W5", BODY_SIZE)
        y = PAGE_H - MARGIN_T

    # セクション見出しバー
    def section_bar(title: str):
        nonlocal y
        if y - 10*mm < MARGIN_B:
            new_page()
        c.setFillColor(C_BAR)
        c.rect(X0, y-7*mm, CONTENT_W, 9*mm, stroke=0, fill=1)
        c.setFont("HeiseiKakuGo-W5", H_SIZE)
        c.setFillColor(C_PRIMARY)
        c.drawString(X0+6*mm, y-5*mm, title)
        y -= 12*mm

    # 箇条書き描画
    def draw_paragraph(label: str, text: str):
        nonlocal y
        section_bar(label)
        c.setFont("HeiseiKakuGo-W5", BODY_SIZE)
        c.setFillColor(colors.black)
        maxw = CONTENT_W - 6*mm
        for ln in wrap_cjk(text, "HeiseiKakuGo-W5", BODY_SIZE, maxw):
            if y - 6*mm < MARGIN_B:
                new_page()
            # 行頭マーカー（丸）
            if ln.strip().startswith("・"):
                marker_y = y - 1.2*mm
                c.setFillColor(C_ACCENT)
                c.circle(X0+4*mm, marker_y, 1.4*mm, stroke=0, fill=1)
                c.setFillColor(colors.black)
                c.drawString(X0+8*mm, y, ln.lstrip("・"))
            else:
                c.drawString(X0+6*mm, y, ln)
            y -= 4.8*mm
        y -= SEC_GAP

    # 本文セクション
    c.setFont("HeiseiKakuGo-W5", BODY_SIZE)
    for label, val in [
        ("サマリー", d.summary),
        ("決定事項", d.decisions),
        ("未決定事項", d.issues),
        ("アクション", d.actions),
        ("リスク", d.risks),
    ]:
        draw_paragraph(label, val or "-")

    # フッター（ページ番号）
    c.setFont("HeiseiKakuGo-W5", SMALL)
    c.setFillColor(C_MUTED)
    c.drawCentredString(PAGE_W/2, MARGIN_B-6*mm, "Generated by Minutes Bot")
    c.showPage()
    c.save()

# =========================
# PDF生成（リッチ版）: 設計チェックリスト
# =========================
def create_design_checklist_pdf(out_path: Path, d: Draft):
    """
    リッチレイアウト版（カラー見出し・チェックボックス群・署名欄）
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.lib import colors
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont
    from reportlab.lib.units import mm

    PAGE_W, PAGE_H = A4
    MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B = 20*mm, 20*mm, 18*mm, 18*mm
    TITLE_SIZE, H_SIZE, BODY, SMALL = 16, 12, 10.5, 9
    GAP, LINE = 5*mm, 5.2*mm

    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    c = canvas.Canvas(str(out_path), pagesize=A4)

    # 色
    C_TITLE   = colors.HexColor("#111827")
    C_BORDER  = colors.HexColor("#e5e7eb")
    C_MUTED   = colors.HexColor("#6b7280")
    C_H1      = colors.HexColor("#10b981")  # 緑
    C_H2      = colors.HexColor("#f59e0b")  # 橙
    C_H3      = colors.HexColor("#3b82f6")  # 青
    C_BAR     = colors.HexColor("#f9fafb")

    def hbar(y, label, color):
        c.setFillColor(C_BAR)
        c.rect(MARGIN_L, y-7*mm, PAGE_W - MARGIN_L - MARGIN_R, 9*mm, stroke=0, fill=1)
        c.setFillColor(color)
        c.circle(MARGIN_L+4*mm, y-2.5*mm, 2*mm, stroke=0, fill=1)
        c.setFillColor(C_TITLE)
        c.setFont("HeiseiKakuGo-W5", H_SIZE)
        c.drawString(MARGIN_L+9*mm, y-5*mm, label)
        return y - 11*mm

    def checkbox(y, text):
        c.setStrokeColor(C_BORDER); c.setLineWidth(1)
        c.rect(MARGIN_L, y-4.2*mm, 4*mm, 4*mm, stroke=1, fill=0)
        c.setFillColor(C_TITLE)
        c.setFont("HeiseiKakuGo-W5", BODY)
        c.drawString(MARGIN_L+6*mm, y-1*mm, text)
        return y - LINE

    # タイトル
    c.setFont("HeiseiKakuGo-W5", TITLE_SIZE)
    c.setFillColor(C_TITLE)
    c.drawString(MARGIN_L, PAGE_H - MARGIN_T, "設計チェックリスト")
    c.setFont("HeiseiKakuGo-W5", SMALL)
    c.setFillColor(C_MUTED)
    c.drawRightString(PAGE_W - MARGIN_R, PAGE_H - MARGIN_T, "各フェーズで使用")

    y = PAGE_H - MARGIN_T - 10*mm

    # メタ情報
    c.setFont("HeiseiKakuGo-W5", BODY)
    c.setFillColor(C_TITLE)
    metas = [
        ("会議名", d.meeting_name or d.title or "（無題）"),
        ("日時",   d.datetime_str or "-"),
        ("目的",   d.purpose or "-"),
    ]
    for k,v in metas:
        c.setFillColor(C_MUTED); c.drawString(MARGIN_L, y, f"{k}")
        c.setFillColor(C_TITLE); c.drawString(MARGIN_L+18*mm, y, v)
        y -= 6*mm
    y -= 2*mm

    # DoR
    y = hbar(y, "作業を始める前の準備（DoR: Definition of Ready）", C_H1)
    for item in [
        "要件定義書ができている",
        "ユーザーストーリーが明確に定義されている",
        "技術的制約が共有されている",
        "デザインシステム／ガイドライン等設定済み",
    ]:
        y = checkbox(y, item)

    y -= GAP

    # ハンドオフ
    y = hbar(y, "デザイン引き渡し（ハンドオフ）", C_H2)
    for item in [
        "画面フロー・経路図",
        "ワイヤーフレーム（全画面）",
        "UIコンポーネント仕様",
        "インタラクション／アニメーション定義",
        "レスポンシブ対応仕様",
        "アクセシビリティ対応（WCAG AA相当）",
    ]:
        y = checkbox(y, item)

    y -= GAP

    # DoD
    y = hbar(y, "作業完了の確認（DoD: Definition of Done）", C_H3)
    for item in [
        "デザインレビューが完了している",
        "関係者の最終合意が完了している",
        "アセット（画像・アイコン）が共有されている",
        "デザインファイルが最新版でマージ済みである",
        "エンジニアへの巻き書き／仕様書が完了している",
    ]:
        y = checkbox(y, item)

    # 署名欄
    y -= 8*mm
    c.setFillColor(C_TITLE)
    c.setFont("HeiseiKakuGo-W5", BODY)
    labels = ["デザイナー", "エンジニア", "PM", "確認日"]
    col_w = (PAGE_W - MARGIN_L - MARGIN_R) / 2
    for i, lab in enumerate(labels):
        x = MARGIN_L + (i%2)*col_w
        c.drawString(x, y, f"{lab}")
        c.setStrokeColor(C_BORDER); c.setLineWidth(0.8)
        c.line(x, y-3*mm, x + col_w - 10*mm, y-3*mm)
        if i%2==1: y -= 10*mm

    # フッター
    c.setFont("HeiseiKakuGo-W5", SMALL)
    c.setFillColor(C_MUTED)
    c.drawString(MARGIN_L, MARGIN_B-6*mm, "このチェックリストは設計移管者と各関係者で確認するためのツールです。")
    c.showPage()
    c.save()

# --- Gmail送信 ---
def send_via_gmail(sender, password, to, subject, body, attach_path: Path):
    msg = MIMEMultipart()
    msg["From"], msg["To"], msg["Subject"] = sender, to, subject
    msg.attach(MIMEText(body, "plain", "utf-8"))
    with open(attach_path, "rb") as f:
        part = MIMEApplication(f.read(), Name=attach_path.name)
        part["Content-Disposition"] = f'attachment; filename="{attach_path.name}"'
        msg.attach(part)
    with smtplib.SMTP_SSL("smtp.gmail.com", 465) as s:
        s.login(sender, password)
        s.send_message(msg)

# --- Google Drive API共通関数 ---
def get_drive_service(scope: str = "drive.file"):
    """
    Google Drive APIクライアントを取得（サービスアカウント認証）
    scope: "drive.file" (作成したファイルのみ) または "drive.readonly" (読み取り専用) または "drive" (読み書き)
    """
    if scope == "drive.file":
        SCOPES = ["https://www.googleapis.com/auth/drive.file"]
    elif scope == "drive.readonly":
        SCOPES = ["https://www.googleapis.com/auth/drive.readonly"]
    else:
        SCOPES = ["https://www.googleapis.com/auth/drive"]
    
    try:
        print("[Drive] Initializing service account credentials...")
        sys.stdout.flush()
        
        # 方法1: 環境変数からJSONを読み込む（推奨）
        if GOOGLE_SERVICE_ACCOUNT_JSON:
            print("[Drive] Using credentials from GOOGLE_SERVICE_ACCOUNT_JSON environment variable")
            sys.stdout.flush()
            try:
                service_account_info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
                creds = service_account.Credentials.from_service_account_info(
                    service_account_info,
                    scopes=SCOPES
                )
                service_account_email = service_account_info.get("client_email", "unknown")
                print(f"[Drive] Service account credentials loaded from JSON string")
                print(f"[Drive] Service account email: {service_account_email}")
                sys.stdout.flush()
            except json.JSONDecodeError as e:
                print(f"[Drive] Failed to parse GOOGLE_SERVICE_ACCOUNT_JSON: {e}")
                sys.stdout.flush()
                raise ValueError(f"Invalid JSON in GOOGLE_SERVICE_ACCOUNT_JSON: {e}")
        # 方法2: ファイルパスから読み込む
        elif GOOGLE_SERVICE_ACCOUNT_PATH:
            print(f"[Drive] Using credentials from file: {GOOGLE_SERVICE_ACCOUNT_PATH}")
            sys.stdout.flush()
            if not os.path.exists(GOOGLE_SERVICE_ACCOUNT_PATH):
                raise FileNotFoundError(f"Service account file not found: {GOOGLE_SERVICE_ACCOUNT_PATH}")
            creds = service_account.Credentials.from_service_account_file(
                GOOGLE_SERVICE_ACCOUNT_PATH,
                scopes=SCOPES
            )
            print("[Drive] Service account credentials loaded from file")
            sys.stdout.flush()
        else:
            raise RuntimeError("GOOGLE_SERVICE_ACCOUNT_JSON or GOOGLE_SERVICE_ACCOUNT_PATH must be set")
        
        print("[Drive] Building Drive service...")
        sys.stdout.flush()
        service = build("drive", "v3", credentials=creds)
        print("[Drive] Drive service initialized successfully")
        sys.stdout.flush()
        return service
    except Exception as e:
        print(f"[Drive] Failed to initialize Drive service: {e}")
        sys.stdout.flush()
        raise
        
# --- Google Drive保存（リンク返却 & 共有ドライブ対応） ---
def upload_to_drive(file_path: Path):
    # 共有フォルダにアクセスするため、"drive"スコープ（フルアクセス）を使用
    service = get_drive_service("drive")
    try:
        # サービスアカウントのメールアドレスを取得
        if GOOGLE_SERVICE_ACCOUNT_JSON:
            try:
                service_account_info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
                service_account_email = service_account_info.get("client_email", "unknown")
            except:
                service_account_email = "unknown"
        else:
            service_account_email = "unknown"
        
        meta = {"name": file_path.name}
        folder_accessible = False
        
        if GOOGLE_DRIVE_FOLDER_ID:
            print(f"[Drive] Checking folder access: {GOOGLE_DRIVE_FOLDER_ID}")
            sys.stdout.flush()
            
            # フォルダが存在するか確認
            try:
                folder = service.files().get(fileId=GOOGLE_DRIVE_FOLDER_ID, supportsAllDrives=True, fields="id, name, mimeType").execute()
                print(f"[Drive] Folder found: {folder.get('name', 'unknown')} (ID: {folder.get('id')}, Type: {folder.get('mimeType')})")
                sys.stdout.flush()
                folder_accessible = True
                meta["parents"] = [GOOGLE_DRIVE_FOLDER_ID]
            except HttpError as folder_error:
                if folder_error.resp.status == 404:
                    print(f"[Drive] ERROR: Folder not found or service account doesn't have access")
                    print(f"[Drive] Folder ID: {GOOGLE_DRIVE_FOLDER_ID}")
                    print(f"[Drive] Service account email: {service_account_email}")
                    print(f"[Drive] Please share the folder with the service account email above")
                    print(f"[Drive] Falling back to root folder upload...")
                    sys.stdout.flush()
                    # フォルダが見つからない場合は、ルートフォルダにアップロード
                    folder_accessible = False
                else:
                    print(f"[Drive] Error checking folder: {folder_error}")
                    sys.stdout.flush()
                    raise
        else:
            print("[Drive] Uploading to root folder (no folder ID specified)")
            sys.stdout.flush()
        
        if folder_accessible:
            print(f"[Drive] Uploading to folder: {GOOGLE_DRIVE_FOLDER_ID}")
        else:
            print("[Drive] Uploading to root folder")
            # ルートフォルダにアップロードする場合はparentsを指定しない
            if "parents" in meta:
                del meta["parents"]
        sys.stdout.flush()
        
        print(f"[Drive] Creating file in Drive...")
        sys.stdout.flush()
        
        try:
            media = MediaFileUpload(str(file_path), mimetype="application/pdf")
            f = service.files().create(
                body=meta,
                media_body=media,
                fields="id, webViewLink",
                supportsAllDrives=True
            ).execute()
            print(f"[Drive] Upload successful: {f}")
            print(f"[Drive] File ID: {f.get('id')}")
            print(f"[Drive] File URL: {f.get('webViewLink')}")
            sys.stdout.flush()
            return f  # {"id": "...", "webViewLink": "..."}
        except HttpError as create_error:
            # 404エラーで、フォルダIDが指定されている場合は、ルートフォルダに再試行
            if create_error.resp.status == 404 and GOOGLE_DRIVE_FOLDER_ID and folder_accessible:
                print(f"[Drive] Upload to folder failed (404), trying root folder...")
                sys.stdout.flush()
                # ルートフォルダにアップロード（MediaFileUploadを再作成）
                meta_no_parents = {"name": file_path.name}
                media = MediaFileUpload(str(file_path), mimetype="application/pdf")
                f = service.files().create(
                    body=meta_no_parents,
                    media_body=media,
                    fields="id, webViewLink",
                    supportsAllDrives=True
                ).execute()
                print(f"[Drive] Upload to root folder successful: {f}")
                print(f"[Drive] File ID: {f.get('id')}")
                print(f"[Drive] File URL: {f.get('webViewLink')}")
                sys.stdout.flush()
                return f
            else:
                raise
    except HttpError as e:
        if e.resp.status == 404:
            print(f"[Drive] Upload failed: Folder not found or access denied")
            print(f"[Drive] Please share the folder '{GOOGLE_DRIVE_FOLDER_ID}' with the service account email: {service_account_email}")
            print(f"[Drive] Service account email: {service_account_email}")
            sys.stdout.flush()
        print(f"[Drive] Upload failed: {e}")
        sys.stdout.flush()
        raise

# --- Google Driveからのファイル取得機能 ---
def get_file_metadata(file_id: str) -> dict:
    """
    Google Driveからファイルのメタデータを取得
    """
    service = get_drive_service("drive.readonly")
    try:
        file = service.files().get(
            fileId=file_id,
            fields="id, name, createdTime, modifiedTime, mimeType, size, parents",
            supportsAllDrives=True
        ).execute()
        print(f"[Drive] File metadata retrieved: {file.get('name')}")
        return file
    except HttpError as e:
        error_details = e.error_details if hasattr(e, 'error_details') else str(e)
        if e.resp.status == 404:
            print(f"[Drive] File not found: {file_id}")
            print(f"[Drive] サービスアカウントにファイルへのアクセス権限がない可能性があります。")
            # サービスアカウントのメールアドレスを取得して表示
            try:
                if GOOGLE_SERVICE_ACCOUNT_JSON:
                    service_account_info = json.loads(GOOGLE_SERVICE_ACCOUNT_JSON)
                    service_account_email = service_account_info.get("client_email", "")
                    print(f"[Drive] ファイルをサービスアカウント ({service_account_email}) に共有してください。")
                elif GOOGLE_SERVICE_ACCOUNT_PATH and os.path.exists(GOOGLE_SERVICE_ACCOUNT_PATH):
                    with open(GOOGLE_SERVICE_ACCOUNT_PATH, 'r', encoding='utf-8') as f:
                        service_account_info = json.load(f)
                        service_account_email = service_account_info.get("client_email", "")
                        print(f"[Drive] ファイルをサービスアカウント ({service_account_email}) に共有してください。")
                else:
                    print(f"[Drive] ファイルをサービスアカウントに共有してください。")
            except Exception:
                print(f"[Drive] ファイルをサービスアカウントに共有してください。")
        else:
            print(f"[Drive] Failed to get file metadata: {e}")
            print(f"[Drive] Error details: {error_details}")
        raise

def download_text_from_drive(file_id: str) -> str:
    """
    Google Driveからテキストファイルの内容をダウンロード
    """
    service = get_drive_service("drive.readonly")
    try:
        # テキストファイルの内容を取得
        request = service.files().get_media(fileId=file_id)
        from io import BytesIO
        from googleapiclient.http import MediaIoBaseDownload
        
        fh = BytesIO()
        downloader = MediaIoBaseDownload(fh, request)
        done = False
        while done is False:
            status, done = downloader.next_chunk()
        
        fh.seek(0)
        content = fh.read().decode('utf-8')
        print(f"[Drive] Text file downloaded: {len(content)} characters")
        return content
    except HttpError as e:
        print(f"[Drive] Failed to download text file: {e}")
        raise

def is_file_processed(file_name: str) -> bool:
    """
    ファイル名から処理済みかどうかを判定
    「_processed_」プレフィックスが含まれている場合は処理済みと判定
    """
    if not file_name:
        return False
    return file_name.startswith("_processed_")

def mark_file_as_processed(file_id: str, original_name: str) -> bool:
    """
    ファイル名に「_processed_」プレフィックスを追加して処理済みをマーク
    """
    if is_file_processed(original_name):
        print(f"[Drive] File already processed: {original_name}")
        return True
    
    new_name = f"_processed_{original_name}"
    service = get_drive_service("drive")
    try:
        file = service.files().update(
            fileId=file_id,
            body={"name": new_name},
            fields="id, name",
            supportsAllDrives=True
        ).execute()
        print(f"[Drive] File renamed to: {file.get('name')}")
        return True
    except HttpError as e:
        print(f"[Drive] Failed to rename file: {e}")
        return False

# --- Google Drive Push Notifications（Webhook）機能 ---
def watch_drive_folder(folder_id: str) -> dict:
    """
    Google Driveフォルダの変更を監視するチャンネルを開始
    戻り値: {"id": channel_id, "resourceId": resource_id, "expiration": expiration}
    """
    if not folder_id:
        raise ValueError("Folder ID is required")
    
    service = get_drive_service("drive")
    
    # WebhookエンドポイントURL
    webhook_url = os.getenv("WEBHOOK_URL", "")
    if not webhook_url:
        # Azure App ServiceのURLを自動検出（環境変数から）
        app_name = os.getenv("WEBSITE_SITE_NAME", "")
        if app_name:
            webhook_url = f"https://{app_name}.azurewebsites.net/webhook/drive"
        else:
            raise ValueError("WEBHOOK_URL or WEBSITE_SITE_NAME must be set")
    
    # チャンネルの有効期限（最大7日、ここでは6日に設定）
    expiration = int((time.time() + 6 * 24 * 60 * 60) * 1000)  # ミリ秒
    
    channel_id = str(uuid.uuid4())
    
    try:
        request_body = {
            "id": channel_id,
            "type": "web_hook",
            "address": webhook_url,
            "token": GOOGLE_DRIVE_WEBHOOK_SECRET or channel_id  # トークンとしてシークレットを使用
        }
        
        channel = service.files().watch(
            fileId=folder_id,
            body=request_body,
            supportsAllDrives=True
        ).execute()
        
        channel_info = {
            "id": channel.get("id"),
            "resourceId": channel.get("resourceId"),
            "expiration": channel.get("expiration"),
            "address": webhook_url,
            "folder_id": folder_id
        }
        
        DRIVE_WATCH_CHANNEL_INFO[folder_id] = channel_info
        
        print(f"[Drive] Watch channel started for folder: {folder_id}")
        print(f"[Drive] Channel ID: {channel_info['id']}")
        print(f"[Drive] Resource ID: {channel_info['resourceId']}")
        print(f"[Drive] Expiration: {channel_info['expiration']}")
        print(f"[Drive] Webhook URL: {webhook_url}")
        
        return channel_info
    except HttpError as e:
        print(f"[Drive] Failed to start watch channel: {e}")
        raise

def stop_watch_drive_folder(channel_id: str, resource_id: str) -> bool:
    """
    Google Driveフォルダの監視チャンネルを停止
    """
    service = get_drive_service("drive")
    
    try:
        service.channels().stop(
            body={
                "id": channel_id,
                "resourceId": resource_id
            }
        ).execute()
        
        print(f"[Drive] Watch channel stopped: {channel_id}")
        return True
    except HttpError as e:
        print(f"[Drive] Failed to stop watch channel: {e}")
        return False

def process_drive_file_notification(file_id: str, channel_id: str = None):
    """
    Google Driveからの通知でファイルを処理（バックグラウンドタスク）
    """
    try:
        # ファイルメタデータを取得
        file_meta = get_file_metadata(file_id)
        file_name = file_meta.get("name", "")
        
        # 既に処理済みか確認
        if is_file_processed(file_name):
            print(f"[Drive] File already processed: {file_name}")
            return
        
        # テキストファイルか確認
        mime_type = file_meta.get("mimeType", "")
        if mime_type not in ["text/plain", "text/plain; charset=utf-8"]:
            print(f"[Drive] Not a text file: {mime_type}")
            return
        
        # テキストファイルをダウンロード
        text_content = download_text_from_drive(file_id)
        
        # ファイル名からタイトルを生成
        title = file_name.replace(".txt", "").replace("_processed_", "")
        
        # 作成日時を取得
        created_time = file_meta.get("createdTime", "")
        datetime_str = created_time if created_time else datetime.now().isoformat()
        
        # テキスト処理パイプラインを実行
        draft_id = str(uuid.uuid4())
        process_text_pipeline(draft_id, text_content, title, DEFAULT_SLACK_CHANNEL, datetime_str)
        
        # ファイルを処理済みにマーク
        mark_file_as_processed(file_id, file_name)
        
        print(f"[Drive] File processed successfully: {file_name}")
    except Exception as e:
        print(f"[Drive] Error processing file notification: {e}")
        import traceback
        print(f"[Drive] Traceback: {traceback.format_exc()}")

# =========================
# アプリ起動/停止時の処理
# =========================
async def polling_task():
    """
    定期的にフォルダ内の新しいファイルをチェックするタスク
    """
    global _polling_task
    print(f"[Drive] Polling task started. Interval: {GOOGLE_DRIVE_POLL_INTERVAL} seconds")
    sys.stdout.flush()
    
    while True:
        try:
            await asyncio.sleep(GOOGLE_DRIVE_POLL_INTERVAL)
            if NOTTA_DRIVE_FOLDER_ID:
                print(f"[Drive] Polling for new files in folder: {NOTTA_DRIVE_FOLDER_ID}")
                sys.stdout.flush()
                # 同期的な関数を非同期で実行
                loop = asyncio.get_event_loop()
                await loop.run_in_executor(None, check_and_process_new_files, NOTTA_DRIVE_FOLDER_ID)
        except asyncio.CancelledError:
            print(f"[Drive] Polling task cancelled")
            sys.stdout.flush()
            break
        except Exception as e:
            print(f"[Drive] Error in polling task: {e}")
            import traceback
            print(f"[Drive] Traceback: {traceback.format_exc()}")
            sys.stdout.flush()

@app.on_event("startup")
async def startup_event():
    """
    アプリ起動時にGoogle Drive監視を開始
    """
    global _polling_task
    if GOOGLE_DRIVE_WATCH_ENABLED and NOTTA_DRIVE_FOLDER_ID:
        try:
            print(f"[Drive] Starting watch for folder: {NOTTA_DRIVE_FOLDER_ID}")
            channel_info = watch_drive_folder(NOTTA_DRIVE_FOLDER_ID)
            print(f"[Drive] Watch started successfully")
            sys.stdout.flush()
        except Exception as e:
            print(f"[Drive] Failed to start watch: {e}")
            import traceback
            print(f"[Drive] Traceback: {traceback.format_exc()}")
            sys.stdout.flush()
        
        # ポーリングタスクを開始（Push通知のバックアップとして）
        try:
            _polling_task = asyncio.create_task(polling_task())
            print(f"[Drive] Polling task started")
            sys.stdout.flush()
        except Exception as e:
            print(f"[Drive] Failed to start polling task: {e}")
            import traceback
            print(f"[Drive] Traceback: {traceback.format_exc()}")
            sys.stdout.flush()
    else:
        print(f"[Drive] Watch disabled or folder ID not set")
        print(f"[Drive] GOOGLE_DRIVE_WATCH_ENABLED: {GOOGLE_DRIVE_WATCH_ENABLED}")
        print(f"[Drive] NOTTA_DRIVE_FOLDER_ID: {NOTTA_DRIVE_FOLDER_ID}")
        sys.stdout.flush()

@app.on_event("shutdown")
async def shutdown_event():
    """
    アプリ停止時にGoogle Drive監視を停止
    """
    global _polling_task
    # ポーリングタスクを停止
    if _polling_task:
        try:
            _polling_task.cancel()
            await _polling_task
            print(f"[Drive] Polling task stopped")
            sys.stdout.flush()
        except asyncio.CancelledError:
            pass
        except Exception as e:
            print(f"[Drive] Error stopping polling task: {e}")
            sys.stdout.flush()
    
    # Watchチャンネルを停止
    if DRIVE_WATCH_CHANNEL_INFO:
        try:
            for folder_id, channel_info in DRIVE_WATCH_CHANNEL_INFO.items():
                channel_id = channel_info.get("id")
                resource_id = channel_info.get("resourceId")
                if channel_id and resource_id:
                    print(f"[Drive] Stopping watch for folder: {folder_id}")
                    stop_watch_drive_folder(channel_id, resource_id)
                    sys.stdout.flush()
        except Exception as e:
            print(f"[Drive] Error stopping watch: {e}")
            import traceback
            print(f"[Drive] Traceback: {traceback.format_exc()}")
            sys.stdout.flush()

# =========================
# FastAPIエンドポイント
# =========================
@app.get("/health")
def health():
    return {"ok": True}

@app.post("/upload")
async def upload_audio(
    background: BackgroundTasks,
    audio: UploadFile = File(...),
    title: str = Form(""),
    channel_id: Optional[str] = Form(None),
):
    # channel_idがNoneまたは空文字列で、DEFAULT_SLACK_CHANNELも空文字列の場合はエラー
    effective_channel = channel_id or DEFAULT_SLACK_CHANNEL
    if not effective_channel or effective_channel.strip() == "":
        raise HTTPException(status_code=400, detail="Slack投稿先が不明です。")

    draft_id = uuid.uuid4().hex
    ext = Path(audio.filename or "").suffix or ".webm"
    raw_path = UPLOAD_DIR / f"{draft_id}{ext}"
    with raw_path.open("wb") as f:
        shutil.copyfileobj(audio.file, f)
    
    # 音声ファイルの保存日時を取得（作成日時または更新日時の早い方）
    file_stat = raw_path.stat()
    created_time = file_stat.st_ctime
    modified_time = file_stat.st_mtime
    # より古い方の日時を使用
    file_time = time.localtime(min(created_time, modified_time))
    datetime_str = time.strftime("%Y年%m月%d日 | %H:%M", file_time)

    background.add_task(process_pipeline, draft_id, raw_path, title or audio.filename, effective_channel, datetime_str)
    return {"accepted": True, "draft_id": draft_id}

@app.post("/process-drive-file")
async def process_drive_file(
    background: BackgroundTasks,
    file_id: str = Form(...),
    channel_id: Optional[str] = Form(None),
):
    """
    Google DriveのファイルIDを指定して、テキストファイルを処理（テスト用）
    """
    # channel_idがNoneまたは空文字列で、DEFAULT_SLACK_CHANNELも空文字列の場合はエラー
    effective_channel = channel_id or DEFAULT_SLACK_CHANNEL
    if not effective_channel or effective_channel.strip() == "":
        raise HTTPException(status_code=400, detail="Slack投稿先が不明です。")
    
    if not NOTTA_DRIVE_FOLDER_ID:
        raise HTTPException(status_code=400, detail="NOTTA_DRIVE_FOLDER_ID が未設定です。")
    
    draft_id = uuid.uuid4().hex
    
    background.add_task(process_drive_file_task, draft_id, file_id, effective_channel)
    return {"accepted": True, "draft_id": draft_id, "file_id": file_id}

@app.post("/webhook/drive")
async def webhook_drive(request: Request, background: BackgroundTasks):
    """
    Google Drive Push通知のWebhookエンドポイント
    """
    try:
        # リクエストヘッダーをログに記録
        headers = dict(request.headers)
        print(f"[Drive Webhook] Received request: {request.method} {request.url.path}")
        print(f"[Drive Webhook] Headers: {headers}")
        sys.stdout.flush()
        
        # リクエストボディを取得
        body = await request.body()
        print(f"[Drive Webhook] Body length: {len(body)} bytes")
        if body:
            print(f"[Drive Webhook] Body preview: {body[:500].decode('utf-8', errors='ignore')}")
        sys.stdout.flush()
        
        # JSONとして解析
        try:
            notification = json.loads(body.decode("utf-8"))
            print(f"[Drive Webhook] Parsed notification: {json.dumps(notification, indent=2, ensure_ascii=False)}")
            sys.stdout.flush()
        except json.JSONDecodeError as e:
            print(f"[Drive Webhook] Invalid JSON in request body: {e}")
            sys.stdout.flush()
            return JSONResponse(status_code=400, content={"error": "Invalid JSON"})
        
        # 通知タイプを確認
        notification_type = notification.get("type", "")
        print(f"[Drive Webhook] Notification type: {notification_type}")
        sys.stdout.flush()
        
        # 同期通知（初期チャレンジ）
        if notification_type == "sync":
            print("[Drive Webhook] Received sync notification (initial challenge)")
            # チャレンジ値を返す
            challenge = notification.get("challenge", "")
            if challenge:
                print(f"[Drive Webhook] Returning challenge: {challenge}")
                sys.stdout.flush()
                return JSONResponse(content={"challenge": challenge})
            else:
                print("[Drive Webhook] No challenge in sync notification")
                sys.stdout.flush()
                return JSONResponse(status_code=400, content={"error": "No challenge"})
        
        # 変更通知
        elif notification_type == "change":
            print("[Drive Webhook] Received change notification")
            
            # Webhook検証（オプション）
            if GOOGLE_DRIVE_WEBHOOK_SECRET:
                token = notification.get("token", "")
                if token != GOOGLE_DRIVE_WEBHOOK_SECRET:
                    print("[Drive Webhook] Invalid token")
                    sys.stdout.flush()
                    return JSONResponse(status_code=403, content={"error": "Invalid token"})
            
            # 変更されたリソースのIDを取得
            resource_id = notification.get("resourceId", "")
            if not resource_id:
                print("[Drive Webhook] No resourceId in notification")
                sys.stdout.flush()
                return JSONResponse(status_code=400, content={"error": "No resourceId"})
            
            print(f"[Drive Webhook] Resource ID: {resource_id}")
            sys.stdout.flush()
            
            # 変更を検出したら、フォルダ内のファイルをチェック
            if NOTTA_DRIVE_FOLDER_ID:
                print(f"[Drive Webhook] Triggering check for folder: {NOTTA_DRIVE_FOLDER_ID}")
                sys.stdout.flush()
                # フォルダ内の新しいファイルを検出して処理
                background.add_task(check_and_process_new_files, NOTTA_DRIVE_FOLDER_ID)
            
            return JSONResponse(status_code=200, content={"ok": True})
        
        # 不明な通知タイプ
        else:
            print(f"[Drive Webhook] Unknown notification type: {notification_type}")
            sys.stdout.flush()
            return JSONResponse(status_code=400, content={"error": "Unknown notification type"})
    
    except Exception as e:
        print(f"[Drive Webhook] Error processing notification: {e}")
        import traceback
        print(f"[Drive Webhook] Traceback: {traceback.format_exc()}")
        sys.stdout.flush()
        return JSONResponse(status_code=500, content={"error": str(e)})

@app.get("/webhook/drive")
async def webhook_drive_get():
    """
    Google Drive Push通知のWebhookエンドポイント（GET - 初期検証用）
    """
    print(f"[Drive Webhook] Received GET request")
    sys.stdout.flush()
    return JSONResponse(status_code=200, content={"status": "ok", "message": "Webhook endpoint is ready"})

def check_and_process_new_files(folder_id: str):
    """
    フォルダ内の新しいファイルをチェックして処理（バックグラウンドタスク）
    """
    try:
        print(f"[Drive] Checking new files in folder: {folder_id}")
        sys.stdout.flush()
        
        service = get_drive_service("drive.readonly")
        
        # フォルダ内のファイルを一覧取得
        query = f"'{folder_id}' in parents and trashed=false and mimeType='text/plain'"
        print(f"[Drive] Query: {query}")
        sys.stdout.flush()
        
        results = service.files().list(
            q=query,
            fields="files(id, name, createdTime, modifiedTime, mimeType)",
            orderBy="createdTime desc",
            pageSize=10,  # 最新10件をチェック
            supportsAllDrives=True,
            includeItemsFromAllDrives=True
        ).execute()
        
        files = results.get("files", [])
        print(f"[Drive] Found {len(files)} text files in folder")
        sys.stdout.flush()
        
        # 各ファイルをチェックして処理
        processed_count = 0
        for file in files:
            file_id = file.get("id")
            file_name = file.get("name", "")
            
            # 既に処理済みか確認
            if is_file_processed(file_name):
                print(f"[Drive] Skipping processed file: {file_name}")
                sys.stdout.flush()
                continue
            
            # 処理を開始
            print(f"[Drive] Processing new file: {file_name} ({file_id})")
            sys.stdout.flush()
            try:
                process_drive_file_notification(file_id)
                processed_count += 1
            except Exception as e:
                print(f"[Drive] Error processing file {file_id}: {e}")
                import traceback
                print(f"[Drive] Traceback: {traceback.format_exc()}")
                sys.stdout.flush()
                continue
        
        print(f"[Drive] Processed {processed_count} new file(s)")
        sys.stdout.flush()
        
    except Exception as e:
        print(f"[Drive] Error checking new files: {e}")
        import traceback
        print(f"[Drive] Traceback: {traceback.format_exc()}")
        sys.stdout.flush()

def process_drive_file_task(draft_id: str, file_id: str, channel_id: str):
    """
    Google Driveのファイルを処理するバックグラウンドタスク
    """
    try:
        # 1. ファイルメタデータを取得
        print(f"[Drive] Processing file ID: {file_id}")
        metadata = get_file_metadata(file_id)
        file_name = metadata.get("name", "")
        created_time = metadata.get("createdTime", "")
        modified_time = metadata.get("modifiedTime", created_time)
        
        # 2. 処理済みかチェック
        if is_file_processed(file_name):
            print(f"[Drive] File already processed: {file_name}")
            return
        
        # 3. ファイル名から日時を抽出（ファイル名に日時が含まれている場合）
        # またはファイルの作成日時を使用
        datetime_str = ""
        if created_time:
            try:
                dt = datetime.fromisoformat(created_time.replace("Z", "+00:00"))
                datetime_str = dt.strftime("%Y年%m月%d日 | %H:%M")
            except Exception as e:
                print(f"[Drive] Failed to parse datetime: {e}")
                datetime_str = time.strftime("%Y年%m月%d日 | %H:%M", time.localtime())
        else:
            datetime_str = time.strftime("%Y年%m月%d日 | %H:%M", time.localtime())
        
        # 4. テキストファイルをダウンロード
        text = download_text_from_drive(file_id)
        
        if not text or not text.strip():
            print(f"[Drive] Empty text file: {file_id}")
            return
        
        # 5. ファイル名からタイトルを生成（拡張子を除く）
        title = Path(file_name).stem if file_name else "議事録"
        
        # 6. テキストを処理
        process_text_pipeline(draft_id, text, title, channel_id, datetime_str)
        
        # 7. 処理完了後、ファイル名を変更
        mark_file_as_processed(file_id, file_name)
        
        print(f"[Drive] File processed successfully: {file_id}")
        
    except HttpError as e:
        print(f"[Drive] Error processing file {file_id}: {e}")
        raise
    except Exception as e:
        print(f"[Drive] Unexpected error processing file {file_id}: {e}")
        raise

def process_pipeline(draft_id: str, raw_path: Path, title: str, channel_id: str, datetime_str: str):
    """音声ファイルからテキストを抽出して処理"""
    text = transcribe_audio(raw_path)
    trans_path = TRANS_DIR / f"{draft_id}.txt"
    trans_path.write_text(text, encoding="utf-8")
    draft = summarize_to_structured(text)
    draft.title = title.strip()[:200]
    draft.datetime_str = datetime_str  # 音声ファイルの保存日時を設定
    save_json(SUMM_DIR / f"{draft_id}.json", draft.dict())
    post_slack_draft(channel_id, draft_id, draft.title, draft, DRAFT_META)

def process_text_pipeline(draft_id: str, text: str, title: str, channel_id: str, datetime_str: str):
    """テキストを直接受け取って処理（Nottaからの文字起こしテキスト用）"""
    trans_path = TRANS_DIR / f"{draft_id}.txt"
    trans_path.write_text(text, encoding="utf-8")
    draft = summarize_to_structured(text)
    draft.title = title.strip()[:200]
    draft.datetime_str = datetime_str
    save_json(SUMM_DIR / f"{draft_id}.json", draft.dict())
    post_slack_draft(channel_id, draft_id, draft.title, draft, DRAFT_META)

@app.post("/slack/actions")
async def slack_actions(request: Request, x_slack_signature: str = Header(default=""), x_slack_request_timestamp: str = Header(default="")):
    raw = await request.body()
    verify_slack_signature(raw, x_slack_request_timestamp, x_slack_signature)
    form = await request.form()
    payload = json.loads(form["payload"])
    ptype = payload.get("type")

    # --- ボタン ---
    if ptype == "block_actions":
        action = payload["actions"][0]
        action_id = action["action_id"]
        draft_id = action.get("value")
        summ_path = SUMM_DIR / f"{draft_id}.json"
        data = json.loads(summ_path.read_text(encoding="utf-8"))
        d = Draft(**data)

        if action_id == "edit":
            client_slack.views_open(trigger_id=payload["trigger_id"], view=build_edit_modal(draft_id, d))
            return JSONResponse({"response_action": "clear"})

        if action_id == "task_complete":
            # タスク完了処理
            value = action.get("value", "")
            if ":" in value:
                task_draft_id, task_index = value.split(":", 1)
                try:
                    task_index = int(task_index)
                    # draft_idからDraftデータを取得
                    task_draft_data = json.loads((SUMM_DIR / f"{task_draft_id}.json").read_text(encoding="utf-8"))
                    task_d = Draft(**task_draft_data)
                    # タスクリストを更新（完了マーク）
                    tasks = parse_tasks_from_actions(task_d.actions)
                    if 0 <= task_index < len(tasks):
                        task = tasks[task_index]
                        # メッセージを更新して完了状態を表示
                        channel = payload.get("channel", {}).get("id") or DEFAULT_SLACK_CHANNEL
                        message_ts = payload.get("message", {}).get("ts")
                        if channel and message_ts:
                            # タスクリストブロックを更新
                            updated_blocks = build_tasks_blocks(task_d, task_draft_id)
                            # 該当タスクを完了状態に変更
                            for block in updated_blocks:
                                if block.get("type") == "section":
                                    text = block.get("text", {}).get("text", "")
                                    if f"☐ {task['title']}" in text or task['title'] in text:
                                        # チェックボックスを完了に変更
                                        block["text"]["text"] = text.replace("☐", "☑")
                                        # 完了ボタンを無効化
                                        if "accessory" in block:
                                            block["accessory"] = {
                                                "type": "button",
                                                "text": {"type": "plain_text", "text": "完了済み"},
                                                "style": "primary",
                                                "value": value,
                                                "action_id": "task_complete",
                                                "disabled": True
                                            }
                            try:
                                client_slack.chat_update(
                                    channel=channel,
                                    ts=message_ts,
                                    blocks=updated_blocks,
                                    text="アクションアイテム＆タスク"
                                )
                            except Exception as e:
                                print(f"[Slack] Failed to update task block: {e}")
                except (ValueError, IndexError, FileNotFoundError):
                    pass
            return JSONResponse({"response_action": "clear"})

        if action_id == "approve":
            # --- Slack更新（承認済み表示）---
            meta = DRAFT_META.get(draft_id, {})
            channel = meta.get("channel") or payload.get("channel", {}).get("id") or DEFAULT_SLACK_CHANNEL
            if not channel:
                return {"ok": False, "error": "チャンネルIDが取得できませんでした"}
            ts = meta.get("ts") or payload.get("message", {}).get("ts")
            
            # 日付と会議名を取得
            date_str = d.datetime_str or ""
            meeting_name = (d.meeting_name or d.title or "議事録")[:10]
            
            # シンプルな承認済みメッセージ（本文のみ）
            approved_text = f"✅ 承認済み議事録：{date_str} {meeting_name}"
            if ts:
                client_slack.chat_update(channel=channel, ts=ts, text=approved_text, blocks=[])

            # PDF命名用ヘルパー：日付と会議名を取得
            # datetime_strから日付を抽出（例："2025年11月3日 | 14:00" → "2025-11-03"）
            pdf_date_str = ""
            if d.datetime_str:
                # 日付形式を抽出
                date_patterns = [
                    r"(\d{4})年(\d{1,2})月(\d{1,2})日",
                    r"(\d{4})-(\d{1,2})-(\d{1,2})",
                    r"(\d{4})/(\d{1,2})/(\d{1,2})",
                ]
                for pattern in date_patterns:
                    match = re.search(pattern, d.datetime_str)
                    if match:
                        year, month, day = match.groups()
                        pdf_date_str = f"{year}-{int(month):02d}-{int(day):02d}"
                        break
            # 日付が取得できない場合は現在日付を使用
            if not pdf_date_str:
                pdf_date_str = datetime.now().strftime("%Y-%m-%d")
            
            # 会議名を取得（10文字制限）
            meeting_name_for_file = (d.meeting_name or d.title or "議事録")[:10]
            # ファイル名に使えない文字を置換
            meeting_name_for_file = re.sub(r'[<>:"/\\|?*]', '_', meeting_name_for_file)
            
            # --- ① 議事録PDF（命名規則：yyyy-mm-dd_議事録_会議名.pdf）
            pdf_filename = f"{pdf_date_str}_議事録_{meeting_name_for_file}.pdf"
            pdf_path = PDF_DIR / pdf_filename
            await create_pdf_async(d, pdf_path)

            # --- ② 設計チェックリストPDF（命名規則：yyyy-mm-dd_設計チェックリスト_会議名.pdf）
            checklist_filename = f"{pdf_date_str}_設計チェックリスト_{meeting_name_for_file}.pdf"
            checklist_path = PDF_DIR / checklist_filename
            create_design_checklist_pdf(checklist_path, d)

            # --- ③ Gmail送信（独立した処理、エラーが発生しても続行）
            if GMAIL_USER and GMAIL_PASS:
                try:
                    send_via_gmail(
                        GMAIL_USER, GMAIL_PASS, GMAIL_USER,
                        f"[議事録承認] {d.title}",
                        "承認済み議事録を添付します。",
                        pdf_path
                    )
                except Exception as e:
                    print(f"[Gmail] Send failed: {e}")

            # --- ④ Drive保存（独立した処理、エラーが発生しても続行）
            drive_file = None
            if GOOGLE_SERVICE_ACCOUNT_JSON or (GOOGLE_SERVICE_ACCOUNT_PATH and os.path.exists(GOOGLE_SERVICE_ACCOUNT_PATH)):
                try:
                    drive_file = upload_to_drive(pdf_path)
                except Exception as e:
                    print(f"[Drive] Upload failed: {e}")
                    drive_file = None

            # --- ⑤ 完了メッセージ（最初に投稿） ---
            msg = "✅ PDF化・メール送信・Google Drive保存を完了しました。"
            if drive_file and drive_file.get("webViewLink"):
                msg += f"\n🔗 Drive: {drive_file['webViewLink']}"
            client_slack.chat_postMessage(channel=channel, thread_ts=ts, text=msg)

            # --- ⑥ 議事録PDFを添付 ---
            try:
                client_slack.files_upload_v2(
                    channels=channel, thread_ts=ts,
                    initial_comment="議事録PDFを添付します。",
                    file=str(pdf_path), filename=pdf_path.name,
                    title=f"議事録：{d.title}"
                )
                # アップロード完了を待つ（Slack側の処理順序を保証）
                time.sleep(0.5)
            except Exception as e:
                print(f"[Slack] file upload failed: {e}")

            # --- ⑦ 設計チェックリストPDFを添付 ---
            try:
                client_slack.files_upload_v2(
                    channels=channel, thread_ts=ts,
                    initial_comment="設計チェックリストPDFを添付します。",
                    file=str(checklist_path), filename=checklist_path.name,
                    title="設計チェックリスト"
                )
                # アップロード完了を待つ（Slack側の処理順序を保証）
                time.sleep(0.5)
            except Exception as e:
                print(f"[Slack] file upload failed: {e}")

            # --- ⑧ タスクリストを同スレッドに表示 ---
            try:
                client_slack.chat_postMessage(
                    channel=channel, thread_ts=ts,
                    blocks=build_tasks_blocks(d, draft_id),
                    text="アクションアイテム＆タスク"
                )
            except Exception as e:
                print(f"[Slack] tasks post failed: {e}")

            # --- ⑨ リマインドをスケジュール（前日/1時間前） ---
            try:
                schedule_task_reminders(channel, ts, d)
                client_slack.chat_postMessage(channel=channel, thread_ts=ts, text="⏰ タスクのリマインドをスケジュールしました。")
            except Exception as e:
                print(f"[Slack] reminder schedule failed: {e}")
            return {"ok": True}

    # --- モーダル保存 ---
    if ptype == "view_submission" and payload["view"]["callback_id"] == "edit_submit":
        draft_id = payload["view"]["private_metadata"]
        state = payload["view"]["state"]["values"]
        updated = Draft(
            title="",
            summary=state.get("summary", {}).get("inp", {}).get("value", ""),
            decisions=state.get("decisions", {}).get("inp", {}).get("value", ""),
            actions=state.get("actions", {}).get("inp", {}).get("value", ""),
            issues=state.get("issues", {}).get("inp", {}).get("value", ""),
            meeting_name=state.get("meeting_name", {}).get("inp", {}).get("value", ""),
            datetime_str=state.get("datetime_str", {}).get("inp", {}).get("value", ""),
            participants=state.get("participants", {}).get("inp", {}).get("value", ""),
            purpose=state.get("purpose", {}).get("inp", {}).get("value", ""),
            risks=state.get("risks", {}).get("inp", {}).get("value", ""),
        )
        save_json(SUMM_DIR / f"{draft_id}.json", updated.dict())
        meta = DRAFT_META.get(draft_id, {})
        channel, ts = meta.get("channel"), meta.get("ts")
        if channel and ts:
            client_slack.chat_update(channel=channel, ts=ts, text="下書きを更新しました", blocks=build_minutes_preview_blocks(draft_id, updated))
        return JSONResponse({"response_action": "clear"})

    return {"ok": True}