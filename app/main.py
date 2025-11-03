import os
import sys
import json
import uuid
import shutil
import time
import hmac
import hashlib
import re
from pathlib import Path
from typing import Optional
from datetime import datetime

from fastapi import FastAPI, UploadFile, File, Form, BackgroundTasks, HTTPException, Request, Header
from fastapi.responses import JSONResponse
from pydantic import BaseModel
from dotenv import load_dotenv

from slack_sdk import WebClient
from slack_sdk.errors import SlackApiError

# ---- OpenAI SDK（Whisper & GPT要約）----
from openai import OpenAI

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
# 初期化
# =========================
load_dotenv()

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY", "")
SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN", "")
SLACK_SIGNING_SECRET = os.getenv("SLACK_SIGNING_SECRET", "")
DEFAULT_SLACK_CHANNEL = os.getenv("SLACK_CHANNEL_ID", "")
GMAIL_USER = os.getenv("GMAIL_USER", "")
GMAIL_PASS = os.getenv("GMAIL_PASS", "")
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

DRAFT_META = {}
# Drive Push通知チャンネル情報の保存（メモリ）
DRIVE_WATCH_CHANNEL_INFO = {}

if not OPENAI_API_KEY:
    raise RuntimeError("OPENAI_API_KEY が未設定です。")
if not SLACK_BOT_TOKEN:
    raise RuntimeError("SLACK_BOT_TOKEN が未設定です。")
if not GMAIL_USER or not GMAIL_PASS:
    print("⚠️ Gmail設定が未設定です。メール送信はスキップされます。")

client_oa = OpenAI(api_key=OPENAI_API_KEY)
client_slack = WebClient(token=SLACK_BOT_TOKEN)

BASE_DIR = Path(__file__).parent
DATA_DIR = BASE_DIR / "data"
UPLOAD_DIR = DATA_DIR / "uploads"
TRANS_DIR = DATA_DIR / "transcripts"
SUMM_DIR = DATA_DIR / "summaries"
PDF_DIR = DATA_DIR / "pdf"
for d in (UPLOAD_DIR, TRANS_DIR, SUMM_DIR, PDF_DIR):
    d.mkdir(parents=True, exist_ok=True)

app = FastAPI(title="Minutes Ingest + PDF(ReportLab) + Gmail + Drive")

# =========================
# モデル
# =========================
class Draft(BaseModel):
    # 既存
    title: str
    summary: str
    decisions: str
    actions: str
    issues: str
    # 追加（任意入力・空でOK）
    meeting_name: str = ""     # 例：Q3プロジェクトロードマッププレビュー
    datetime_str: str = ""     # 例：2025年10月25日 | 14:00-16:00
    participants: str = ""     # 例：田中(PM), 佐藤(デザイナー), ...
    purpose: str = ""          # 例：Q3のロードマップを確認し優先順位を決定する
    risks: str = ""            # 箇条書き想定（なければ空）

# =========================
# 内部ヘルパ
# =========================
def transcribe_audio(file_path: Path) -> str:
    """Whisperで文字起こし"""
    with file_path.open("rb") as f:
        result = client_oa.audio.transcriptions.create(
            model="whisper-1",
            file=f
        )
    return getattr(result, "text", "") or result.__dict__.get("text", "")

def summarize_to_structured(text: str) -> Draft:
    """GPTで要約"""
    sys = """You are a meeting minutes assistant. Analyze the transcript and return JSON with the following structure:
    
    Required fields (extract from transcript or infer):
    - meeting_name: Meeting title or topic (extract if mentioned, otherwise use first few sentences)
    - datetime_str: Date and time if available in transcript, otherwise leave empty
    - participants: List of participants mentioned (convert to string: "name1, name2, ...")
    - purpose: Meeting purpose or agenda
    - summary: Overall summary of the meeting (important - this should be a comprehensive paragraph)
    - decisions: Decisions made during the meeting (use bullet points with "・" prefix for multiple items)
    - actions: Action items extracted from transcript - MUST identify tasks mentioned even if assignee/date not specified. 
      Format each as: "・task_description（担当：person_name、期限：estimated_date）"
      If no assignee mentioned, infer from context or use "担当：未定"
      If no date mentioned, estimate reasonable deadline or use "期限：未定"
    - issues: Open issues or concerns that remain unresolved (use bullet points with "・" prefix)
    - risks: Identified risks, challenges, or potential problems (use bullet points with "・" prefix)
    
    CRITICAL:
    - You MUST extract actions from the transcript even if not explicitly stated as "action items"
    - Look for phrases like "next steps", "we should", "need to", "will do", etc.
    - Always populate actions field - if nothing specific, at least extract implicit tasks from the summary
    - risks field must be populated - identify any potential problems, challenges, or concerns mentioned
    
    Return ALL fields as strings. For multi-line content, use newline characters."""
    user = f"以下は会議の文字起こしです。日本語で要約してください。\n---\n{text}"
    resp = client_oa.chat.completions.create(
        model="gpt-4o-mini",
        messages=[{"role":"system","content":sys},{"role":"user","content":user}],
        temperature=0.2,
    )
    content = resp.choices[0].message.content.strip()
    if "```" in content:
        content = content.split("```")[1]
        if content.strip().startswith("json"):
            content = content.split("\n", 1)[1]
    try:
        data = json.loads(content)
    except:
        return Draft(title="", summary=content, decisions="", actions="", issues="", meeting_name="", datetime_str="", participants="", purpose="", risks="")
    def _norm(x):
        if isinstance(x, list):
            return "\n".join([f"・{i}" for i in x])
        elif isinstance(x, dict):
            if 'action' in x and 'responsible' in x:
                return f"・{x['action']}（担当：{x['responsible']}）"
            elif 'action' in x:
                return f"・{x['action']}"
            else:
                return "\n".join([f"・{k}: {v}" for k, v in x.items()])
        return str(x)
    # 文字列変換ヘルパー
    def _to_str(x):
        if x is None:
            return ""
        if isinstance(x, list):
            return ", ".join(str(i) for i in x)
        return str(x)
    
    # アクションが空の場合は空文字ではなく警告を設定
    actions_text = _norm(data.get("actions",""))
    if not actions_text or actions_text.strip() == "":
        actions_text = "アクションアイテムが特定できませんでした"
    
    # リスクが空の場合は空文字ではなく警告を設定
    risks_text = _norm(data.get("risks",""))
    if not risks_text or risks_text.strip() == "":
        risks_text = "特になし"
    
    return Draft(
        title="",
        summary=_norm(data.get("summary","")),
        decisions=_norm(data.get("decisions","")),
        actions=actions_text,
        issues=_norm(data.get("issues","")),
        meeting_name=_to_str(data.get("meeting_name")),
        datetime_str=_to_str(data.get("datetime_str")),
        participants=_to_str(data.get("participants")),
        purpose=_to_str(data.get("purpose")),
        risks=risks_text,
    )

def verify_slack_signature(body: bytes, timestamp: str, signature: str):
    if not SLACK_SIGNING_SECRET:
        return
    # 5分以内チェック
    try:
        if abs(time.time() - int(timestamp)) > 60*5:
            raise HTTPException(status_code=401, detail="Slack timestamp expired")
    except Exception:
        raise HTTPException(status_code=401, detail="Slack timestamp invalid")
    basestring = f"v0:{timestamp}:{body.decode()}".encode()
    my_sig = "v0=" + hmac.new(SLACK_SIGNING_SECRET.encode(), basestring, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(my_sig, signature):
        raise HTTPException(status_code=401, detail="Slack signature invalid")

# 追加：読みやすいプレビュー用ブロック
def build_minutes_preview_blocks(draft_id: str, d: Draft):
    def md_section(label, text):
        return {"type":"section","text":{"type":"mrkdwn","text":f"*{label}*\n{text or '-'}"}}

    head = [
        {"type":"header","text":{"type":"plain_text","text":"議事録ボット"}},
        {"type":"section","fields":[
            {"type":"mrkdwn","text":f"*会議名:*\n{d.meeting_name or d.title or '（無題）'}"},
            {"type":"mrkdwn","text":f"*日時:*\n{d.datetime_str or '-'}"},
            {"type":"mrkdwn","text":f"*参加者:*\n{d.participants or '-'}"},
            {"type":"mrkdwn","text":f"*目的:*\n{d.purpose or '-'}"},
        ]},
        {"type":"divider"},
    ]
    body = [
        md_section("サマリー", d.summary),
        md_section("決定事項", d.decisions),
        md_section("未決定事項", d.issues),
    ]
    # アクション（タスクリスト）を追加
    if (d.actions or "").strip():
        body += [md_section("アクション", d.actions)]
    # リスク欄（任意）
    if (d.risks or "").strip():
        body += [md_section("リスク", d.risks)]

    tail = [
        {"type":"actions","elements":[
            {"type":"button","text":{"type":"plain_text","text":"編集"},"action_id":"edit","value":draft_id},
            {"type":"button","text":{"type":"plain_text","text":"承認"},"style":"primary","action_id":"approve","value":draft_id},
        ]}
    ]
    return head + body + tail

# 追加：アクション文字列からタスク配列へ軽量パース
def parse_tasks_from_actions(actions_text: str):
    tasks = []
    for raw in (actions_text or "").splitlines():
        item = raw.lstrip("・").strip()
        if not item: continue
        # （担当：○○）, （期限：10/25） を抜く
        assignee = None
        due = None
        m1 = re.search(r"（担当：([^）]+)）", item)
        if m1: assignee = m1.group(1); item = item.replace(m1.group(0), "").strip()
        m2 = re.search(r"（期限：([^）]+)）", item)
        if m2: due = m2.group(1); item = item.replace(m2.group(0), "").strip()
        tasks.append({"title": item, "assignee": assignee, "due": due})
    return tasks

# 追加：タスクのSlackブロック（画像2の「アクションアイテム&タスク」風）
def build_tasks_blocks(d: Draft, draft_id: str = ""):
    tasks = parse_tasks_from_actions(d.actions)
    if not tasks:
        return [{"type":"section","text":{"type":"mrkdwn","text":"アクションアイテムは登録されていません。"}}]
    
    # 各タスクを個別のセクションブロックとして表示
    blocks = [
        {"type":"header","text":{"type":"plain_text","text":"✅ アクションアイテム＆タスク"}},
    ]
    
    for i, t in enumerate(tasks):
        task_value = f"{draft_id}:{i}" if draft_id else str(i)
        # 担当者と期限のフィールド
        fields = []
        if t.get("assignee"):
            fields.append({"type":"mrkdwn","text":f"*担当:*\n{t['assignee']}"})
        if t.get("due"):
            fields.append({"type":"mrkdwn","text":f"*期限:*\n{t['due']}"})
        
        # チェックボックス付きセクションブロック
        text = f"☐ {t['title']}"
        if fields:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": text},
                "fields": fields,
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "完了"},
                    "value": task_value,
                    "action_id": "task_complete",
                }
            })
        else:
            blocks.append({
                "type": "section",
                "text": {"type": "mrkdwn", "text": text},
                "accessory": {
                    "type": "button",
                    "text": {"type": "plain_text", "text": "完了"},
                    "value": task_value,
                    "action_id": "task_complete",
                }
            })
    
    return blocks

def post_slack_draft(channel_id: str, draft_id: str, title: str, d: Draft):
    blocks = build_minutes_preview_blocks(draft_id, d)   # ← ここを差し替え
    try:
        resp = client_slack.chat_postMessage(channel=channel_id, text="議事録 下書き", blocks=blocks)
        DRAFT_META[draft_id] = {"channel": channel_id, "ts": resp["ts"]}
        return resp
    except Exception as e:
        print(f"[Slack] Post draft failed for channel {channel_id}: {e}")
        # channel_idが不正な場合は空のchannel_idを設定してDRAFT_METAに保存
        DRAFT_META[draft_id] = {"channel": "", "ts": ""}
        raise

def build_edit_modal(draft_id: str, d: Draft):
    return {
        "type": "modal",
        "callback_id": "edit_submit",
        "private_metadata": draft_id,
        "title": {"type": "plain_text", "text": "議事録 編集"},
        "submit": {"type": "plain_text", "text": "保存"},
        "close": {"type": "plain_text", "text": "キャンセル"},
        "blocks": [
            {"type":"input","block_id":"meeting_name","label":{"type":"plain_text","text":"会議名"},
             "element":{"type":"plain_text_input","action_id":"inp","initial_value":d.meeting_name or ""}},
            {"type":"input","block_id":"datetime_str","label":{"type":"plain_text","text":"日時"},
             "element":{"type":"plain_text_input","action_id":"inp","initial_value":d.datetime_str or ""}},
            {"type":"input","block_id":"participants","label":{"type":"plain_text","text":"参加者"},
             "element":{"type":"plain_text_input","action_id":"inp","initial_value":d.participants or ""}},
            {"type":"input","block_id":"purpose","label":{"type":"plain_text","text":"目的"},
             "element":{"type":"plain_text_input","action_id":"inp","multiline":True,"initial_value":d.purpose or ""}},
            {"type":"input","block_id":"summary","label":{"type":"plain_text","text":"サマリー"},
             "element":{"type":"plain_text_input","action_id":"inp","multiline":True,"initial_value":d.summary}},
            {"type":"input","block_id":"decisions","label":{"type":"plain_text","text":"決定事項"},
             "element":{"type":"plain_text_input","action_id":"inp","multiline":True,"initial_value":d.decisions}},
            {"type":"input","block_id":"issues","label":{"type":"plain_text","text":"未決定事項"},
             "element":{"type":"plain_text_input","action_id":"inp","multiline":True,"initial_value":d.issues}},
            {"type":"input","block_id":"actions","label":{"type":"plain_text","text":"アクション"},
             "element":{"type":"plain_text_input","action_id":"inp","multiline":True,"initial_value":d.actions}},
            {"type":"input","block_id":"risks","label":{"type":"plain_text","text":"リスク"},
             "element":{"type":"plain_text_input","action_id":"inp","multiline":True,"initial_value":d.risks or ""}},
        ]
    }

def save_json(path: Path, data: dict):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")

def _escape_html(s: str) -> str:
    return (s or "").replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")

# =========================
# PDF生成（ReportLab, 日本語折返し対応）
# =========================
async def create_pdf_async(d: Draft, out_path: Path):
    """
    ReportLab を使用してPDF生成。
    - 日本語フォント（HeiseiKakuGo-W5）を登録
    - 文字幅計測でCJK向けの折返し
    - ページ下端での自動改ページ
    """
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    # ---- ページ設定
    PAGE_W, PAGE_H = A4
    MARGIN_L = 72        # 左 1 inch
    MARGIN_R = 72        # 右 1 inch
    MARGIN_T = 36        # 上 0.5 inch
    MARGIN_B = 36        # 下 0.5 inch
    LINE_GAP = 15
    SECTION_GAP = 10
    TITLE_SIZE = 14
    BODY_SIZE = 11

    # ---- 日本語フォント登録
    FONT_NAME = "HeiseiKakuGo-W5"
    pdfmetrics.registerFont(UnicodeCIDFont(FONT_NAME))

    # ---- レイアウト用関数：横幅に応じた折返し
    def wrap_cjk(text: str, font_name: str, font_size: int, max_width: float):
        """
        日本語CJK向けの1文字ずつ積み上げ折返し。
        ・英数字やスペースもそのまま1文字単位で計測（単語ベースではなく幅ベース）
        ・入力の改行(\n)は段落区切りとして扱い、段落ごとにラップ
        """
        lines = []
        if not text:
            return ["-"]

        for raw_line in text.splitlines() or [""]:
            if raw_line == "":
                lines.append("")  # 空行
                continue
            buf = ""
            for ch in raw_line:
                new_buf = buf + ch
                w = pdfmetrics.stringWidth(new_buf, font_name, font_size)
                if w <= max_width:
                    buf = new_buf
                else:
                    if buf:
                        lines.append(buf)
                        buf = ch  # 新しい行を現在の文字から開始
                    else:
                        # 1文字でも超える場合は強制配置
                        lines.append(ch)
                        buf = ""
            if buf or raw_line == "":
                lines.append(buf)
        return lines

    # ---- キャンバス生成
    c = canvas.Canvas(str(out_path), pagesize=A4)

    def ensure_page_space(current_y: float, needed: float) -> float:
        """必要行数分の高さが足りなければ改ページ"""
        if current_y - needed < MARGIN_B:
            c.showPage()
            # 新ページでもフォントを再設定
            c.setFont(FONT_NAME, BODY_SIZE)
            return PAGE_H - MARGIN_T
        return current_y

    # ---- タイトル
    y = PAGE_H - MARGIN_T
    c.setFont(FONT_NAME, TITLE_SIZE)
    title_text = f"議事録：{d.meeting_name or d.title or '（無題）'}"
    c.drawString(MARGIN_L, y, title_text)

    # ---- 本文
    c.setFont(FONT_NAME, BODY_SIZE)
    y -= 30

    max_text_width = PAGE_W - (MARGIN_L + MARGIN_R)

    # メタ情報（会議名、日時、参加者、目的）
    if d.meeting_name or d.datetime_str or d.participants or d.purpose:
        c.setFont(FONT_NAME, BODY_SIZE)
        if d.meeting_name:
            c.drawString(MARGIN_L + 18, y, f"会議名: {d.meeting_name}")
            y -= LINE_GAP
        if d.datetime_str:
            c.drawString(MARGIN_L + 18, y, f"日時: {d.datetime_str}")
            y -= LINE_GAP
        if d.participants:
            c.drawString(MARGIN_L + 18, y, f"参加者: {d.participants}")
            y -= LINE_GAP
        if d.purpose:
            c.drawString(MARGIN_L + 18, y, f"目的: {d.purpose}")
            y -= LINE_GAP
        y -= SECTION_GAP

    sections = [
        ("Summary", d.summary),
        ("Decision", d.decisions),
        ("Action",  d.actions),
        ("Issue",   d.issues),
        ("Risk",    d.risks),
    ]

    for label, text in sections:
        # セクション見出し
        y = ensure_page_space(y, LINE_GAP * 2)
        c.drawString(MARGIN_L, y, f"{label}:")
        y -= 20

        # ラップしてから描画
        wrapped_lines = wrap_cjk(text, FONT_NAME, BODY_SIZE, max_text_width)
        for line in wrapped_lines:
            y = ensure_page_space(y, LINE_GAP)
            c.drawString(MARGIN_L + 18, y, line)  # 少しインデント
            y -= LINE_GAP

        y -= SECTION_GAP

    c.save()
    print("reportlabでPDF生成完了（日本語折返し対応）")

# 追加：設計チェックリストPDF
def create_design_checklist_pdf(out_path: Path, d: Draft):
    from reportlab.lib.pagesizes import A4
    from reportlab.pdfgen import canvas
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.cidfonts import UnicodeCIDFont

    PAGE_W, PAGE_H = A4
    MARGIN_L, MARGIN_R, MARGIN_T, MARGIN_B = 72, 72, 50, 36
    TITLE_SIZE, H_SIZE, BODY = 16, 13, 11
    LINE = 18

    pdfmetrics.registerFont(UnicodeCIDFont("HeiseiKakuGo-W5"))
    c = canvas.Canvas(str(out_path), pagesize=A4)

    def yline(y): return y - LINE
    def draw_title(txt, y):
        c.setFont("HeiseiKakuGo-W5", TITLE_SIZE); c.drawString(MARGIN_L, y, txt); return yline(y)-6
    def draw_head(k, v, y):
        c.setFont("HeiseiKakuGo-W5", BODY); c.drawString(MARGIN_L, y, f"{k}：{v or '-'}"); return yline(y)
    def draw_h(txt, y):
        c.setFont("HeiseiKakuGo-W5", H_SIZE); c.drawString(MARGIN_L, y, f"■ {txt}"); return yline(y)
    def draw_box_item(txt, y):
        c.setFont("HeiseiKakuGo-W5", BODY)
        c.rect(MARGIN_L, y-12, 10, 10, stroke=1, fill=0)
        c.drawString(MARGIN_L+16, y-2, txt); return yline(y)

    y = PAGE_H - MARGIN_T
    y = draw_title("設計チェックリスト", y)
    y = draw_head("会議名", d.meeting_name or d.title, y)
    y = draw_head("日時", d.datetime_str, y)
    y = draw_head("目的", d.purpose, y)
    y -= 6

    # DoR
    y = draw_h("作業を始める前の準備（DoR: Definition of Ready）", y)
    for item in [
        "要件定義書ができている",
        "ユーザーストーリーが明確に定義されている",
        "技術的制約が共有されている",
        "デザインシステム/ガイドライン等設定済み",
    ]: y = draw_box_item(item, y)

    y -= 6
    # ハンドオフ
    y = draw_h("デザイン引き渡し（ハンドオフ）", y)
    for item in [
        "画面フロー・経路図", "ワイヤーフレーム（全画面）", "UIコンポーネント仕様",
        "インタラクション/アニメーション定義", "レスポンシブ対応仕様",
        "アクセシビリティ対応（WCAG AA相当）",
    ]: y = draw_box_item(item, y)

    y -= 6
    # DoD
    y = draw_h("作業完了の確認（DoD: Definition of Done）", y)
    for item in [
        "デザインレビュー完了", "関係者の最終確認完了",
        "アセット（画像・アイコン）共有済み",
        "最新デザインファイルがマージ済み",
        "エンジニアへの巻き書き/仕様書が完了",
    ]: y = draw_box_item(item, y)

    # 署名欄
    y -= 10; c.setFont("HeiseiKakuGo-W5", BODY)
    for role in ["デザイナー", "エンジニア", "PM"]:
        c.drawString(MARGIN_L, y, f"{role} 署名：_________________________"); y = yline(y)
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
                folder_accessible = True
                meta["parents"] = [GOOGLE_DRIVE_FOLDER_ID]
                sys.stdout.flush()
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
@app.on_event("startup")
async def startup_event():
    """
    アプリ起動時にGoogle Drive監視を開始
    """
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
        # リクエストボディを取得
        body = await request.body()
        
        # JSONとして解析
        try:
            notification = json.loads(body.decode("utf-8"))
        except json.JSONDecodeError:
            print("[Drive Webhook] Invalid JSON in request body")
            return JSONResponse(status_code=400, content={"error": "Invalid JSON"})
        
        # 通知タイプを確認
        notification_type = notification.get("type", "")
        
        # 同期通知（初期チャレンジ）
        if notification_type == "sync":
            print("[Drive Webhook] Received sync notification (initial challenge)")
            # チャレンジ値を返す
            challenge = notification.get("challenge", "")
            if challenge:
                print(f"[Drive Webhook] Returning challenge: {challenge}")
                return JSONResponse(content={"challenge": challenge})
            else:
                print("[Drive Webhook] No challenge in sync notification")
                return JSONResponse(status_code=400, content={"error": "No challenge"})
        
        # 変更通知
        elif notification_type == "change":
            print("[Drive Webhook] Received change notification")
            
            # Webhook検証（オプション）
            if GOOGLE_DRIVE_WEBHOOK_SECRET:
                token = notification.get("token", "")
                if token != GOOGLE_DRIVE_WEBHOOK_SECRET:
                    print("[Drive Webhook] Invalid token")
                    return JSONResponse(status_code=403, content={"error": "Invalid token"})
            
            # 変更されたリソースのIDを取得
            resource_id = notification.get("resourceId", "")
            if not resource_id:
                print("[Drive Webhook] No resourceId in notification")
                return JSONResponse(status_code=400, content={"error": "No resourceId"})
            
            # 変更を検出したら、フォルダ内のファイルをチェック
            if NOTTA_DRIVE_FOLDER_ID:
                # フォルダ内の新しいファイルを検出して処理
                background.add_task(check_and_process_new_files, NOTTA_DRIVE_FOLDER_ID)
            
            return JSONResponse(status_code=200, content={"ok": True})
        
        # 不明な通知タイプ
        else:
            print(f"[Drive Webhook] Unknown notification type: {notification_type}")
            return JSONResponse(status_code=400, content={"error": "Unknown notification type"})
    
    except Exception as e:
        print(f"[Drive Webhook] Error processing notification: {e}")
        import traceback
        print(f"[Drive Webhook] Traceback: {traceback.format_exc()}")
        return JSONResponse(status_code=500, content={"error": str(e)})

def check_and_process_new_files(folder_id: str):
    """
    フォルダ内の新しいファイルをチェックして処理（バックグラウンドタスク）
    """
    try:
        service = get_drive_service("drive.readonly")
        
        # フォルダ内のファイルを一覧取得
        query = f"'{folder_id}' in parents and trashed=false and mimeType='text/plain'"
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
        
        # 各ファイルをチェックして処理
        for file in files:
            file_id = file.get("id")
            file_name = file.get("name", "")
            
            # 既に処理済みか確認
            if is_file_processed(file_name):
                continue
            
            # 処理を開始
            print(f"[Drive] Processing new file: {file_name} ({file_id})")
            try:
                process_drive_file_notification(file_id)
            except Exception as e:
                print(f"[Drive] Error processing file {file_id}: {e}")
                continue
        
    except Exception as e:
        print(f"[Drive] Error checking new files: {e}")
        import traceback
        print(f"[Drive] Traceback: {traceback.format_exc()}")

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
    post_slack_draft(channel_id, draft_id, draft.title, draft)

def process_text_pipeline(draft_id: str, text: str, title: str, channel_id: str, datetime_str: str):
    """テキストを直接受け取って処理（Nottaからの文字起こしテキスト用）"""
    trans_path = TRANS_DIR / f"{draft_id}.txt"
    trans_path.write_text(text, encoding="utf-8")
    draft = summarize_to_structured(text)
    draft.title = title.strip()[:200]
    draft.datetime_str = datetime_str
    save_json(SUMM_DIR / f"{draft_id}.json", draft.dict())
    post_slack_draft(channel_id, draft_id, draft.title, draft)

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

        if action_id == "approve":
            # --- Slack更新（承認済み表示）---
            meta = DRAFT_META.get(draft_id, {})
            channel = meta.get("channel") or payload.get("channel", {}).get("id") or DEFAULT_SLACK_CHANNEL
            if not channel:
                return {"ok": False, "error": "チャンネルIDが取得できませんでした"}
            ts = meta.get("ts") or payload.get("message", {}).get("ts")
            approved_blocks = [{"type":"section","text":{"type":"mrkdwn","text":"*✅ 承認済み議事録*"}}] + build_minutes_preview_blocks(draft_id, d)[:-1]
            if ts:
                client_slack.chat_update(channel=channel, ts=ts, text="承認済み議事録", blocks=approved_blocks)
            client_slack.chat_postMessage(channel=channel, thread_ts=ts, text="PDF化・メール送信・Drive保存を実行中...")

            # --- ① 議事録PDF（既存）
            pdf_path = PDF_DIR / f"{draft_id}.pdf"
            await create_pdf_async(d, pdf_path)

            # --- ② 設計チェックリストPDF（新規）
            checklist_path = PDF_DIR / f"{draft_id}_design_checklist.pdf"
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

            # --- ⑤ SlackへPDFを2点とも添付 ---
            try:
                client_slack.files_upload_v2(
                    channels=channel, thread_ts=ts,
                    initial_comment="議事録PDFを添付します。",
                    file=str(pdf_path), filename=pdf_path.name,
                    title=f"議事録：{d.title}"
                )
                client_slack.files_upload_v2(
                    channels=channel, thread_ts=ts,
                    initial_comment="設計チェックリストPDFを添付します。",
                    file=str(checklist_path), filename=checklist_path.name,
                    title="設計チェックリスト"
                )
            except Exception as e:
                print(f"[Slack] file upload failed: {e}")

            # --- ⑥ タスクリストを同スレッドに表示 ---
            try:
                client_slack.chat_postMessage(
                    channel=channel, thread_ts=ts,
                    blocks=build_tasks_blocks(d, draft_id),
                    text="アクションアイテム＆タスク"
                )
            except Exception as e:
                print(f"[Slack] tasks post failed: {e}")

            # 完了メッセージ
            msg = "✅ PDF化・メール送信・Google Drive保存を完了しました。"
            if drive_file and drive_file.get("webViewLink"):
                msg += f"\n🔗 Drive: {drive_file['webViewLink']}"
            client_slack.chat_postMessage(channel=channel, thread_ts=ts, text=msg)
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