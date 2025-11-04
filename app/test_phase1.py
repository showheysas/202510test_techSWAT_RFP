"""
Phase 1 動作確認テストスクリプト
"""
import sys
from pathlib import Path
import tempfile
import os

print("=" * 60)
print("Phase 1 動作確認テスト")
print("=" * 60)

# テスト1: config.py のインポート
print("\n[テスト1] config.py のインポート")
try:
    import config
    print("✓ config.py のインポート成功")
    
    # 設定値の確認
    print(f"  - BASE_DIR: {config.BASE_DIR}")
    print(f"  - DATA_DIR: {config.DATA_DIR}")
    print(f"  - UPLOAD_DIR: {config.UPLOAD_DIR}")
    print(f"  - TRANS_DIR: {config.TRANS_DIR}")
    print(f"  - SUMM_DIR: {config.SUMM_DIR}")
    print(f"  - PDF_DIR: {config.PDF_DIR}")
    
    # ディレクトリが存在するか確認
    for dir_name, dir_path in [
        ("UPLOAD_DIR", config.UPLOAD_DIR),
        ("TRANS_DIR", config.TRANS_DIR),
        ("SUMM_DIR", config.SUMM_DIR),
        ("PDF_DIR", config.PDF_DIR),
    ]:
        if dir_path.exists():
            print(f"  ✓ {dir_name} が存在: {dir_path}")
        else:
            print(f"  ✗ {dir_name} が存在しません: {dir_path}")
    
    # クライアントの確認
    print(f"  - client_oa: {type(config.client_oa).__name__}")
    print(f"  - client_slack: {type(config.client_slack).__name__}")
    
except Exception as e:
    print(f"✗ config.py のインポート失敗: {e}")
    sys.exit(1)

# テスト2: models.py のインポート
print("\n[テスト2] models.py のインポート")
try:
    from models import Draft
    print("✓ models.py のインポート成功")
    
    # Draftモデルのテスト
    test_draft = Draft(
        title="テスト議事録",
        summary="これはテストです",
        decisions="決定事項1",
        actions="アクション1",
        issues="課題1",
        meeting_name="テスト会議",
        datetime_str="2025年10月25日 | 14:00",
        participants="田中, 佐藤",
        purpose="テスト目的",
        risks="リスク1"
    )
    print("✓ Draftモデルの作成成功")
    
    # 辞書への変換
    draft_dict = test_draft.dict()
    print(f"  - フィールド数: {len(draft_dict)}")
    print(f"  - title: {draft_dict['title']}")
    print(f"  - meeting_name: {draft_dict['meeting_name']}")
    
except Exception as e:
    print(f"✗ models.py のインポートまたはテスト失敗: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# テスト3: utils/storage.py のインポート
print("\n[テスト3] utils/storage.py のインポート")
try:
    from utils.storage import save_json, load_json
    print("✓ utils/storage.py のインポート成功")
    
    # 一時ディレクトリでテスト
    with tempfile.TemporaryDirectory() as tmpdir:
        test_path = Path(tmpdir) / "test.json"
        test_data = {
            "test_key": "test_value",
            "number": 123,
            "list": [1, 2, 3],
            "nested": {"a": "b"}
        }
        
        # 保存テスト
        save_json(test_path, test_data)
        print("✓ save_json() 成功")
        
        if test_path.exists():
            print(f"  - ファイルが作成されました: {test_path}")
        else:
            print(f"  ✗ ファイルが作成されませんでした: {test_path}")
            sys.exit(1)
        
        # 読み込みテスト
        loaded_data = load_json(test_path)
        print("✓ load_json() 成功")
        
        # データの比較
        if loaded_data == test_data:
            print("  ✓ 保存・読み込みデータが一致")
        else:
            print(f"  ✗ データが一致しません")
            print(f"    保存: {test_data}")
            print(f"    読み込み: {loaded_data}")
            sys.exit(1)
        
        # 日本語データのテスト
        jp_test_path = Path(tmpdir) / "test_jp.json"
        jp_data = {
            "title": "テスト議事録",
            "summary": "これは日本語のテストです",
            "items": ["項目1", "項目2", "項目3"]
        }
        save_json(jp_test_path, jp_data)
        loaded_jp_data = load_json(jp_test_path)
        if loaded_jp_data == jp_data:
            print("  ✓ 日本語データの保存・読み込み成功")
        else:
            print(f"  ✗ 日本語データが一致しません")
            sys.exit(1)
    
except Exception as e:
    print(f"✗ utils/storage.py のインポートまたはテスト失敗: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# テスト4: 統合テスト（実際の使用例）
print("\n[テスト4] 統合テスト")
try:
    from config import SUMM_DIR
    from models import Draft
    from utils.storage import save_json, load_json
    
    # テスト用Draftを作成
    test_draft = Draft(
        title="統合テスト議事録",
        summary="統合テストのサマリー",
        decisions="決定事項",
        actions="アクション",
        issues="課題"
    )
    
    # JSONファイルに保存
    test_summary_path = SUMM_DIR / "test_integration.json"
    save_json(test_summary_path, test_draft.dict())
    print("✓ Draft → JSON保存 成功")
    
    # JSONファイルから読み込み
    loaded_dict = load_json(test_summary_path)
    loaded_draft = Draft(**loaded_dict)
    print("✓ JSON → Draft復元 成功")
    
    # データの確認
    if loaded_draft.title == test_draft.title:
        print("  ✓ データが正しく保存・読み込みされました")
    else:
        print(f"  ✗ データが一致しません")
        sys.exit(1)
    
    # テストファイルを削除
    if test_summary_path.exists():
        test_summary_path.unlink()
        print("  ✓ テストファイルを削除しました")
    
except Exception as e:
    print(f"✗ 統合テスト失敗: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("✓ すべてのテストが成功しました！")
print("=" * 60)
print("\nPhase 1 の動作確認完了。次のフェーズに進めます。")

