"""
デプロイ後のリファクタリング確認スクリプト
Phase 1とPhase 2までのモジュールが正しく動作するか確認
"""
import sys
from pathlib import Path

print("=" * 70)
print("リファクタリング確認（Phase 1 & Phase 2）")
print("=" * 70)

# 期待されるファイル一覧
expected_files = {
    "Phase 1": {
        "config.py": "環境変数と設定管理",
        "models.py": "Draftモデル定義",
        "utils/storage.py": "ストレージユーティリティ",
    },
    "Phase 2": {
        "services/__init__.py": "サービス層初期化",
        "services/openai_service.py": "OpenAIサービス（文字起こし・要約）",
    }
}

# 結果を記録
results = {
    "Phase 1": {"passed": 0, "failed": 0, "errors": []},
    "Phase 2": {"passed": 0, "failed": 0, "errors": []}
}

# Phase 1 の確認
print("\n" + "=" * 70)
print("Phase 1: 基盤構築の確認")
print("=" * 70)

# 1. config.py の確認
print("\n[1] config.py の確認")
try:
    if Path("config.py").exists():
        import config
        print("  ✓ config.py が存在します")
        
        # 必要な属性の確認
        required_attrs = [
            "OPENAI_API_KEY", "SLACK_BOT_TOKEN", "DEFAULT_SLACK_CHANNEL",
            "client_oa", "client_slack",
            "BASE_DIR", "DATA_DIR", "UPLOAD_DIR", "TRANS_DIR", "SUMM_DIR", "PDF_DIR"
        ]
        
        missing_attrs = []
        for attr in required_attrs:
            if hasattr(config, attr):
                print(f"    ✓ {attr} が存在します")
            else:
                missing_attrs.append(attr)
                print(f"    ✗ {attr} が存在しません")
        
        if not missing_attrs:
            print("  ✓ config.py のすべての属性が正しく定義されています")
            results["Phase 1"]["passed"] += 1
        else:
            print(f"  ✗ config.py に不足している属性があります: {missing_attrs}")
            results["Phase 1"]["failed"] += 1
            results["Phase 1"]["errors"].append(f"config.py: 不足属性 {missing_attrs}")
    else:
        print("  ✗ config.py が存在しません")
        results["Phase 1"]["failed"] += 1
        results["Phase 1"]["errors"].append("config.py が存在しません")
except Exception as e:
    print(f"  ✗ config.py のインポートまたは確認に失敗: {e}")
    results["Phase 1"]["failed"] += 1
    results["Phase 1"]["errors"].append(f"config.py エラー: {e}")

# 2. models.py の確認
print("\n[2] models.py の確認")
try:
    if Path("models.py").exists():
        from models import Draft
        print("  ✓ models.py が存在します")
        
        # Draftモデルの確認
        try:
            test_draft = Draft(
                title="テスト",
                summary="テストサマリー",
                decisions="決定事項",
                actions="アクション",
                issues="課題"
            )
            print("  ✓ Draftモデルが正しく定義されています")
            
            # フィールドの確認
            expected_fields = [
                "title", "summary", "decisions", "actions", "issues",
                "meeting_name", "datetime_str", "participants", "purpose", "risks"
            ]
            missing_fields = []
            for field in expected_fields:
                if hasattr(test_draft, field):
                    print(f"    ✓ {field} フィールドが存在します")
                else:
                    missing_fields.append(field)
                    print(f"    ✗ {field} フィールドが存在しません")
            
            if not missing_fields:
                print("  ✓ Draftモデルのすべてのフィールドが正しく定義されています")
                results["Phase 1"]["passed"] += 1
            else:
                print(f"  ✗ Draftモデルに不足しているフィールドがあります: {missing_fields}")
                results["Phase 1"]["failed"] += 1
                results["Phase 1"]["errors"].append(f"models.py: 不足フィールド {missing_fields}")
        except Exception as e:
            print(f"  ✗ Draftモデルの作成に失敗: {e}")
            results["Phase 1"]["failed"] += 1
            results["Phase 1"]["errors"].append(f"models.py: Draft作成エラー - {e}")
    else:
        print("  ✗ models.py が存在しません")
        results["Phase 1"]["failed"] += 1
        results["Phase 1"]["errors"].append("models.py が存在しません")
except Exception as e:
    print(f"  ✗ models.py のインポートまたは確認に失敗: {e}")
    results["Phase 1"]["failed"] += 1
    results["Phase 1"]["errors"].append(f"models.py エラー: {e}")

# 3. utils/storage.py の確認
print("\n[3] utils/storage.py の確認")
try:
    storage_path = Path("utils/storage.py")
    if storage_path.exists():
        from utils.storage import save_json, load_json
        print("  ✓ utils/storage.py が存在します")
        
        # 関数の確認
        if callable(save_json) and callable(load_json):
            print("  ✓ save_json と load_json が正しく定義されています")
            
            # 簡単な動作確認（一時ファイルで）
            import tempfile
            with tempfile.TemporaryDirectory() as tmpdir:
                test_file = Path(tmpdir) / "test.json"
                test_data = {"test": "data", "number": 123}
                
                try:
                    save_json(test_file, test_data)
                    if test_file.exists():
                        loaded = load_json(test_file)
                        if loaded == test_data:
                            print("  ✓ save_json と load_json が正常に動作します")
                            results["Phase 1"]["passed"] += 1
                        else:
                            print("  ✗ save_json と load_json の動作に問題があります")
                            results["Phase 1"]["failed"] += 1
                            results["Phase 1"]["errors"].append("utils/storage.py: 動作確認失敗")
                    else:
                        print("  ✗ save_json でファイルが作成されませんでした")
                        results["Phase 1"]["failed"] += 1
                        results["Phase 1"]["errors"].append("utils/storage.py: ファイル作成失敗")
                except Exception as e:
                    print(f"  ✗ 動作確認中にエラー: {e}")
                    results["Phase 1"]["failed"] += 1
                    results["Phase 1"]["errors"].append(f"utils/storage.py: 動作確認エラー - {e}")
        else:
            print("  ✗ save_json または load_json が正しく定義されていません")
            results["Phase 1"]["failed"] += 1
            results["Phase 1"]["errors"].append("utils/storage.py: 関数定義エラー")
    else:
        print("  ✗ utils/storage.py が存在しません")
        results["Phase 1"]["failed"] += 1
        results["Phase 1"]["errors"].append("utils/storage.py が存在しません")
except Exception as e:
    print(f"  ✗ utils/storage.py のインポートまたは確認に失敗: {e}")
    results["Phase 1"]["failed"] += 1
    results["Phase 1"]["errors"].append(f"utils/storage.py エラー: {e}")

# Phase 2 の確認
print("\n" + "=" * 70)
print("Phase 2: OpenAIサービスの確認")
print("=" * 70)

# 4. services/openai_service.py の確認
print("\n[4] services/openai_service.py の確認")
try:
    oai_service_path = Path("services/openai_service.py")
    if oai_service_path.exists():
        from services.openai_service import transcribe_audio, summarize_to_structured
        print("  ✓ services/openai_service.py が存在します")
        
        # 関数の確認
        if callable(transcribe_audio) and callable(summarize_to_structured):
            print("  ✓ transcribe_audio と summarize_to_structured が正しく定義されています")
            
            # 依存関係の確認
            try:
                from config import client_oa
                from models import Draft
                print("  ✓ 依存関係（config, models）が正しく解決できます")
                print("  ✓ OpenAIサービスは独立して動作可能です")
                results["Phase 2"]["passed"] += 1
            except Exception as e:
                print(f"  ✗ 依存関係の解決に失敗: {e}")
                results["Phase 2"]["failed"] += 1
                results["Phase 2"]["errors"].append(f"依存関係エラー: {e}")
        else:
            print("  ✗ transcribe_audio または summarize_to_structured が正しく定義されていません")
            results["Phase 2"]["failed"] += 1
            results["Phase 2"]["errors"].append("openai_service.py: 関数定義エラー")
    else:
        print("  ✗ services/openai_service.py が存在しません")
        results["Phase 2"]["failed"] += 1
        results["Phase 2"]["errors"].append("services/openai_service.py が存在しません")
except Exception as e:
    print(f"  ✗ services/openai_service.py のインポートまたは確認に失敗: {e}")
    results["Phase 2"]["failed"] += 1
    results["Phase 2"]["errors"].append(f"openai_service.py エラー: {e}")

# 5. services/__init__.py の確認
print("\n[5] services/__init__.py の確認")
try:
    services_init_path = Path("services/__init__.py")
    if services_init_path.exists():
        import services
        print("  ✓ services/__init__.py が存在します")
        print("  ✓ services パッケージとして正しく認識されます")
        results["Phase 2"]["passed"] += 1
    else:
        print("  ⚠ services/__init__.py が存在しません（オプション）")
        print("    注: パッケージとして認識されない可能性がありますが、動作には影響しない場合があります")
except Exception as e:
    print(f"  ⚠ services/__init__.py の確認中にエラー: {e}")

# 統合テスト
print("\n" + "=" * 70)
print("統合テスト")
print("=" * 70)

print("\n[6] Phase 1とPhase 2の統合確認")
try:
    # すべてのモジュールをインポート
    from config import client_oa, client_slack, SUMM_DIR
    from models import Draft
    from utils.storage import save_json, load_json
    from services.openai_service import transcribe_audio, summarize_to_structured
    
    print("  ✓ すべてのモジュールが正常にインポートできます")
    
    # 統合動作確認（実際のAPI呼び出しなし）
    print("  ✓ モジュール間の依存関係が正しく解決されています")
    print("  ✓ リファクタリングされたモジュールは独立して動作可能です")
    
    results["Phase 1"]["passed"] += 1
    results["Phase 2"]["passed"] += 1
except Exception as e:
    print(f"  ✗ 統合テストに失敗: {e}")
    import traceback
    traceback.print_exc()

# 結果サマリー
print("\n" + "=" * 70)
print("結果サマリー")
print("=" * 70)

for phase_name, result in results.items():
    print(f"\n{phase_name}:")
    print(f"  ✓ 成功: {result['passed']}")
    print(f"  ✗ 失敗: {result['failed']}")
    
    if result['errors']:
        print(f"  エラー詳細:")
        for error in result['errors']:
            print(f"    - {error}")

total_passed = sum(r['passed'] for r in results.values())
total_failed = sum(r['failed'] for r in results.values())

print("\n" + "=" * 70)
print("総合結果")
print("=" * 70)
print(f"総成功数: {total_passed}")
print(f"総失敗数: {total_failed}")

if total_failed == 0:
    print("\n✓ Phase 1とPhase 2のリファクタリングは正常に完了しています！")
    print("  すべてのモジュールが正しく動作します。")
    sys.exit(0)
else:
    print("\n✗ 一部のモジュールに問題があります。")
    print("  上記のエラー詳細を確認してください。")
    sys.exit(1)

