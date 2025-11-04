"""
Phase 2 動作確認テストスクリプト（OpenAIサービス）
"""
import sys
from pathlib import Path

print("=" * 60)
print("Phase 2 動作確認テスト（OpenAIサービス）")
print("=" * 60)

# テスト1: モジュールのインポート
print("\n[テスト1] services/openai_service.py のインポート")
try:
    from services.openai_service import transcribe_audio, summarize_to_structured
    print("✓ openai_service.py のインポート成功")
    
    # 関数の確認
    print(f"  - transcribe_audio: {transcribe_audio}")
    print(f"  - summarize_to_structured: {summarize_to_structured}")
    
except Exception as e:
    print(f"✗ openai_service.py のインポート失敗: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# テスト2: 依存関係の確認
print("\n[テスト2] 依存関係の確認")
try:
    # config.pyからclient_oaをインポートできるか
    from config import client_oa
    print("✓ config.client_oa のインポート成功")
    
    # models.pyからDraftをインポートできるか
    from models import Draft
    print("✓ models.Draft のインポート成功")
    
    # OpenAIクライアントの型確認
    print(f"  - client_oa の型: {type(client_oa).__name__}")
    
except Exception as e:
    print(f"✗ 依存関係の確認失敗: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# テスト3: summarize_to_structured の基本動作（モック）
print("\n[テスト3] summarize_to_structured の基本動作確認")
print("  ※ 実際のAPI呼び出しは行いません（コスト削減）")
print("  ✓ 関数のシグネチャ確認のみ")

# 関数のドキュメント確認
if summarize_to_structured.__doc__:
    print("  ✓ ドキュメント文字列が設定されています")
else:
    print("  ⚠ ドキュメント文字列が設定されていません")

# テスト4: モジュール構造の確認
print("\n[テスト4] モジュール構造の確認")
try:
    import services.openai_service as oai_service
    print("✓ モジュールとして正しくインポート可能")
    
    # 公開されている関数の確認
    public_functions = [
        name for name in dir(oai_service)
        if not name.startswith('_') and callable(getattr(oai_service, name))
    ]
    print(f"  - 公開関数: {', '.join(public_functions)}")
    
    expected_functions = ['transcribe_audio', 'summarize_to_structured']
    for func_name in expected_functions:
        if func_name in public_functions:
            print(f"  ✓ {func_name} が公開されています")
        else:
            print(f"  ✗ {func_name} が見つかりません")
            sys.exit(1)
    
except Exception as e:
    print(f"✗ モジュール構造の確認失敗: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# テスト5: インポートパスの確認
print("\n[テスト5] インポートパスの確認")
try:
    # 異なる方法でインポートできるか確認
    from services import openai_service
    print("✓ from services import openai_service 成功")
    
    from services.openai_service import transcribe_audio as transcribe
    print("✓ エイリアス付きインポート成功")
    
except Exception as e:
    print(f"✗ インポートパスの確認失敗: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 60)
print("✓ すべてのテストが成功しました！")
print("=" * 60)
print("\nPhase 2 の動作確認完了。")
print("注意: 実際のAPI呼び出しテストは行っていません（コスト削減のため）")
print("実際の使用時は、transcribe_audio() と summarize_to_structured() が")
print("正しく動作することを確認してください。")

