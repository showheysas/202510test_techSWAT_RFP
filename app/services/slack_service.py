"""
Slackサービスモジュール
Slack関連の機能（投稿、ブロック生成、署名検証など）を提供
"""
import time
import hmac
import hashlib
import re
from typing import Optional
from fastapi import HTTPException

# Azure App Service環境とローカル開発環境の両方に対応
try:
    from app.config import client_slack, SLACK_SIGNING_SECRET, DEFAULT_SLACK_CHANNEL
    from app.models import Draft
except ImportError:
    from config import client_slack, SLACK_SIGNING_SECRET, DEFAULT_SLACK_CHANNEL
    from models import Draft


# DRAFT_METAはmain.pyで管理（グローバル変数として共有）
# このモジュールからは参照のみ（モジュール外から設定される）

def verify_slack_signature(body: bytes, timestamp: str, signature: str):
    """
    Slackリクエストの署名を検証
    
    Args:
        body: リクエストボディ（バイト）
        timestamp: タイムスタンプ
        signature: 署名
    """
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


def build_minutes_preview_blocks(draft_id: str, d: Draft):
    """
    議事録プレビュー用のSlackブロックを生成
    
    Args:
        draft_id: 下書きID
        d: Draftモデル
        
    Returns:
        Slackブロックのリスト
    """
    def md_section(label, text):
        return {"type":"section","text":{"type":"mrkdwn","text":f"*{label}*\n{text or '-'}"}}

    # 議事録名を最大10文字に制限
    meeting_name_display = d.meeting_name or d.title or '（無題）'
    if len(meeting_name_display) > 10:
        meeting_name_display = meeting_name_display[:10] + "..."
    
    head = [
        {"type":"header","text":{"type":"plain_text","text":"議事録ボット"}},
        {"type":"section","fields":[
            {"type":"mrkdwn","text":f"*会議名:*\n{meeting_name_display}"},
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


def build_edit_modal(draft_id: str, d: Draft):
    """
    議事録編集用のSlackモーダルを生成
    
    Args:
        draft_id: 下書きID
        d: Draftモデル
        
    Returns:
        Slackモーダルの設定辞書
    """
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


def parse_tasks_from_actions(actions_text: str):
    """
    アクション文字列からタスク配列へ軽量パース
    
    Args:
        actions_text: アクション文字列（例：「・タスクA（担当：田中、期限：10/25）」）
        
    Returns:
        タスクのリスト（各タスクは {"title": str, "assignee": Optional[str], "due": Optional[str]}）
    """
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


def build_tasks_blocks(d: Draft, draft_id: str = ""):
    """
    タスクのSlackブロックを生成（画像2の「アクションアイテム&タスク」風）
    
    Args:
        d: Draftモデル
        draft_id: 下書きID（オプション）
        
    Returns:
        Slackブロックのリスト
    """
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


def post_slack_draft(channel_id: str, draft_id: str, title: str, d: Draft, draft_meta: dict):
    """
    Slackに議事録下書きを投稿
    
    Args:
        channel_id: SlackチャンネルID
        draft_id: 下書きID
        title: タイトル
        d: Draftモデル
        draft_meta: DRAFT_META辞書（更新される）
        
    Returns:
        Slack APIの応答
    """
    # 重複投稿を防ぐ：既に投稿済みの場合はスキップ
    if draft_id in draft_meta and draft_meta[draft_id].get("ts"):
        print(f"[Slack] Draft {draft_id} already posted, skipping duplicate")
        return draft_meta[draft_id]
    
    blocks = build_minutes_preview_blocks(draft_id, d)
    try:
        resp = client_slack.chat_postMessage(channel=channel_id, text="議事録 下書き", blocks=blocks)
        draft_meta[draft_id] = {"channel": channel_id, "ts": resp["ts"]}
        return resp
    except Exception as e:
        print(f"[Slack] Post draft failed for channel {channel_id}: {e}")
        # channel_idが不正な場合は空のchannel_idを設定してDRAFT_METAに保存
        draft_meta[draft_id] = {"channel": "", "ts": ""}
        raise

