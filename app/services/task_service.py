"""
タスクサービスモジュール
タスク関連の機能（完了処理、リマインドなど）を提供
"""
import json
import re
import time
from typing import Optional, Tuple
from datetime import datetime, timedelta

# Azure App Service環境とローカル開発環境の両方に対応
try:
    from app.config import (
        client_slack, DEFAULT_REMIND_HOUR, SLACK_USER_MAP_JSON,
        SUMM_DIR, DEFAULT_SLACK_CHANNEL
    )
    from app.models import Draft
    from app.services.slack_service import parse_tasks_from_actions, build_tasks_blocks
except ImportError:
    from config import (
        client_slack, DEFAULT_REMIND_HOUR, SLACK_USER_MAP_JSON,
        SUMM_DIR, DEFAULT_SLACK_CHANNEL
    )
    from models import Draft
    from services.slack_service import parse_tasks_from_actions, build_tasks_blocks

from slack_sdk.errors import SlackApiError

try:
    from zoneinfo import ZoneInfo  # Python 3.9+
except Exception:
    ZoneInfo = None


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
    - リマインド作成から3分後
    
    投稿先：同スレッド。担当者Slack IDが分かればメンション付与。
    
    Args:
        channel: SlackチャンネルID
        thread_ts: スレッドのタイムスタンプ
        d: Draftモデル
    """
    tasks = parse_tasks_from_actions(d.actions)
    if not tasks: 
        return

    # 現在時刻から3分後
    now = datetime.now(_tz()) if _tz() else datetime.now()
    reminder_time = now + timedelta(minutes=3)
    post_at = _epoch(reminder_time)
    
    if not post_at:
        return

    for t in tasks:
        mention = ""
        uid = _resolve_slack_user_id(t.get("assignee"))
        if uid:
            mention = f"<@{uid}> "
        text = (f"{mention}🔔 ⏰ リマインド：*{t['title']}* "
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


def mark_task_complete(draft_id: str, task_index: int) -> Tuple[Optional[Draft], Optional[list]]:
    """
    タスクを完了状態にマークする
    
    Args:
        draft_id: 下書きID
        task_index: タスクのインデックス
        
    Returns:
        (Draft, 更新されたブロック) のタプル。エラー時は (None, None)
    """
    try:
        # draft_idからDraftデータを取得
        task_draft_data = json.loads((SUMM_DIR / f"{draft_id}.json").read_text(encoding="utf-8"))
        task_d = Draft(**task_draft_data)
        
        # タスクリストを取得
        tasks = parse_tasks_from_actions(task_d.actions)
        if 0 <= task_index < len(tasks):
            task = tasks[task_index]
            
            # タスクリストブロックを更新
            updated_blocks = build_tasks_blocks(task_d, draft_id)
            
            # 該当タスクを完了状態に変更
            for block in updated_blocks:
                if block.get("type") == "section":
                    text = block.get("text", {}).get("text", "")
                    if f"☐ {task['title']}" in text or task['title'] in text:
                        # チェックボックスを完了に変更
                        block["text"]["text"] = text.replace("☐", "☑")
                        # 完了ボタンを無効化
                        if "accessory" in block:
                            task_value = f"{draft_id}:{task_index}"
                            block["accessory"] = {
                                "type": "button",
                                "text": {"type": "plain_text", "text": "完了済み"},
                                "style": "primary",
                                "value": task_value,
                                "action_id": "task_complete",
                                "disabled": True
                            }
            
            return task_d, updated_blocks
        else:
            print(f"[Task] Invalid task index: {task_index} (total tasks: {len(tasks)})")
            return None, None
    except (ValueError, IndexError, FileNotFoundError) as e:
        print(f"[Task] Error marking task complete: {e}")
        return None, None


def update_task_block_in_slack(channel: str, message_ts: str, blocks: list) -> bool:
    """
    Slackメッセージのタスクブロックを更新
    
    Args:
        channel: SlackチャンネルID
        message_ts: メッセージのタイムスタンプ
        blocks: 更新されたブロック
        
    Returns:
        成功した場合はTrue、失敗した場合はFalse
    """
    try:
        client_slack.chat_update(
            channel=channel,
            ts=message_ts,
            blocks=blocks,
            text="アクションアイテム＆タスク"
        )
        return True
    except Exception as e:
        print(f"[Slack] Failed to update task block: {e}")
        return False

