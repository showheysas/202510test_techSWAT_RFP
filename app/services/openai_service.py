"""
OpenAIサービスモジュール
Whisper文字起こしとGPT要約機能を提供
"""
import json
from pathlib import Path
from typing import Optional

from config import client_oa
from models import Draft


def transcribe_audio(file_path: Path) -> str:
    """
    Whisperで音声ファイルを文字起こし
    
    Args:
        file_path: 音声ファイルのパス
        
    Returns:
        文字起こしされたテキスト
    """
    with file_path.open("rb") as f:
        result = client_oa.audio.transcriptions.create(
            model="whisper-1",
            file=f
        )
    return getattr(result, "text", "") or result.__dict__.get("text", "")


def summarize_to_structured(text: str) -> Draft:
    """
    GPTで文字起こしテキストを構造化された議事録に要約
    
    Args:
        text: 文字起こしテキスト
        
    Returns:
        構造化された議事録（Draftモデル）
    """
    system_prompt = """You are a meeting minutes assistant. Analyze the transcript and return JSON with the following structure:
    
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
    
    user_prompt = f"以下は会議の文字起こしです。日本語で要約してください。\n---\n{text}"
    
    resp = client_oa.chat.completions.create(
        model="gpt-4o-mini",
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ],
        temperature=0.2,
    )
    
    content = resp.choices[0].message.content.strip()
    
    # JSONコードブロックを除去
    if "```" in content:
        content = content.split("```")[1]
        if content.strip().startswith("json"):
            content = content.split("\n", 1)[1]
    
    # JSONをパース
    try:
        data = json.loads(content)
    except json.JSONDecodeError:
        # JSONパース失敗時は、コンテンツをそのままサマリーとして使用
        return Draft(
            title="",
            summary=content,
            decisions="",
            actions="",
            issues="",
            meeting_name="",
            datetime_str="",
            participants="",
            purpose="",
            risks=""
        )
    
    # データ正規化用のヘルパー関数
    def _norm(x):
        """データを正規化（リスト、辞書、その他を適切な形式に変換）"""
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
    
    def _to_str(x):
        """データを文字列に変換"""
        if x is None:
            return ""
        if isinstance(x, list):
            return ", ".join(str(i) for i in x)
        return str(x)
    
    # アクションが空の場合は警告メッセージを設定
    actions_text = _norm(data.get("actions", ""))
    if not actions_text or actions_text.strip() == "":
        actions_text = "アクションアイテムが特定できませんでした"
    
    # リスクが空の場合はデフォルトメッセージを設定
    risks_text = _norm(data.get("risks", ""))
    if not risks_text or risks_text.strip() == "":
        risks_text = "特になし"
    
    return Draft(
        title="",
        summary=_norm(data.get("summary", "")),
        decisions=_norm(data.get("decisions", "")),
        actions=actions_text,
        issues=_norm(data.get("issues", "")),
        meeting_name=_to_str(data.get("meeting_name")),
        datetime_str=_to_str(data.get("datetime_str")),
        participants=_to_str(data.get("participants")),
        purpose=_to_str(data.get("purpose")),
        risks=risks_text,
    )

