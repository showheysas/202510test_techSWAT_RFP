"""
ストレージユーティリティ
ファイルの保存・読み込みに関するヘルパー関数
"""
import json
from pathlib import Path


def save_json(path: Path, data: dict) -> None:
    """
    JSONファイルを保存する
    
    Args:
        path: 保存先のパス
        data: 保存するデータ（辞書型）
    """
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, ensure_ascii=False, indent=2),
        encoding="utf-8"
    )


def load_json(path: Path) -> dict:
    """
    JSONファイルを読み込む
    
    Args:
        path: 読み込むファイルのパス
        
    Returns:
        読み込んだデータ（辞書型）
        
    Raises:
        FileNotFoundError: ファイルが存在しない場合
        json.JSONDecodeError: JSONの解析に失敗した場合
    """
    if not path.exists():
        raise FileNotFoundError(f"File not found: {path}")
    
    return json.loads(path.read_text(encoding="utf-8"))

