"""
データモデル定義
"""
from pydantic import BaseModel


class Draft(BaseModel):
    """議事録の下書きモデル"""
    # 既存
    title: str
    summary: str
    decisions: str
    actions: str
    issues: str
    # 追加（任意入力・空でOK）
    meeting_name: str = ""     # 例：Q3プロジェクトロードマッププレビュー
    datetime_str: str = ""     # 例：2025年10月25日 | 14:00-16:00
    participants: str = ""      # 例：田中(PM), 佐藤(デザイナー), ...
    purpose: str = ""          # 例：Q3のロードマップを確認し優先順位を決定する
    risks: str = ""            # 箇条書き想定（なければ空）

