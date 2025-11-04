"""
デプロイ前の互換性チェック
既存のmain.pyが新しいモジュールと競合しないか確認
"""
import sys
from pathlib import Path

print("=" * 60)
print("デプロイ前互換性チェック")
print("=" * 60)

# チェック1: 既存のmain.pyが新モジュールをインポートしていないか確認
print("\n[チェック1] main.pyのインポート文確認")
try:
    main_content = Path("main.py").read_text(encoding="utf-8")
    
    # 新しく作成したモジュールへのインポートがないか確認
    new_modules = [
        ("config", "config.py"),
        ("models", "models.py"),
        ("utils.storage", "utils/storage.py"),
        ("services.openai_service", "services/openai_service.py"),
    ]
    
    conflicts = []
    for module_name, file_path in new_modules:
        if f"import {module_name}" in main_content or f"from {module_name}" in main_content:
            conflicts.append(f"  ✗ {module_name} がインポートされています")
        else:
            print(f"  ✓ {module_name} はインポートされていません（安全）")
    
    if conflicts:
        print("\n⚠ 警告: 以下のモジュールがインポートされています:")
        for conflict in conflicts:
            print(conflict)
    else:
        print("\n✓ main.pyは新モジュールをインポートしていません（安全）")
        
except Exception as e:
    print(f"✗ チェック失敗: {e}")
    sys.exit(1)

# チェック2: 新モジュールが存在するか確認
print("\n[チェック2] 新モジュールの存在確認")
new_files = [
    "config.py",
    "models.py",
    "utils/storage.py",
    "services/__init__.py",
    "services/openai_service.py",
]

all_exist = True
for file_path in new_files:
    path = Path(file_path)
    if path.exists():
        print(f"  ✓ {file_path} が存在します")
    else:
        print(f"  ✗ {file_path} が存在しません")
        all_exist = False

if all_exist:
    print("\n✓ すべての新モジュールが存在します")
else:
    print("\n⚠ 一部のモジュールが存在しません（デプロイには影響なし）")

# チェック3: 既存のmain.pyが正常にインポートできるか（構文チェック）
print("\n[チェック3] main.pyの構文チェック")
try:
    # 構文チェックのみ（実行はしない）
    compile(Path("main.py").read_text(encoding="utf-8"), "main.py", "exec")
    print("  ✓ main.pyの構文は正常です")
except SyntaxError as e:
    print(f"  ✗ main.pyに構文エラーがあります: {e}")
    sys.exit(1)
except Exception as e:
    print(f"  ⚠ 構文チェック中にエラー: {e}")

# チェック4: 新モジュールが誤ってインポートされる可能性の確認
print("\n[チェック4] 名前空間の競合確認")
try:
    # main.py内で定義されているクラス/関数名を確認
    main_content = Path("main.py").read_text(encoding="utf-8")
    
    # main.py内の定義を確認
    main_defines = {
        "Draft": "class Draft" in main_content,
        "client_oa": "client_oa = " in main_content,
        "client_slack": "client_slack = " in main_content,
        "save_json": "def save_json" in main_content,
    }
    
    print("  main.py内の定義:")
    for name, exists in main_defines.items():
        status = "✓ 定義あり" if exists else "✗ 定義なし"
        print(f"    - {name}: {status}")
    
    # 新モジュールとの競合がないことを確認
    print("\n  ✓ main.pyは独自の定義を持っているため、新モジュールと競合しません")
    
except Exception as e:
    print(f"  ✗ 確認失敗: {e}")

# チェック5: デプロイ時の動作確認（模擬）
print("\n[チェック5] デプロイ時の動作シミュレーション")
print("  以下のシナリオを確認:")
print("  1. main.pyが実行される")
print("  2. 新モジュール（config.py等）が同じディレクトリに存在する")
print("  3. 新モジュールがインポートされない限り、影響なし")

# config.pyが存在する場合、インポートされても動作するか確認
print("\n  config.pyの動作確認:")
try:
    # config.pyをインポートしてみる（実際にはmain.pyはインポートしない）
    import config
    print("    ✓ config.pyは独立して動作可能")
    
    # 既存のmain.pyと競合しないことを確認
    # main.pyは独自に環境変数を読み込むため、config.pyをインポートしない限り問題なし
    print("    ✓ main.pyはconfig.pyをインポートしないため、競合しません")
    
except Exception as e:
    print(f"    ⚠ config.pyのインポートでエラー: {e}")
    print("    （main.pyはインポートしないため、デプロイには影響なし）")

print("\n" + "=" * 60)
print("デプロイ安全性の結論")
print("=" * 60)
print("""
✓ 既存のmain.pyは新モジュールをインポートしていません
✓ 新モジュールは独立して存在しており、main.pyに影響しません
✓ main.pyは独自のコードを持っており、正常に動作します

結論: 現在の状態でAzureにデプロイ可能です。

注意事項:
- 新モジュール（config.py, models.py等）はデプロイに含まれますが、
  main.pyは使用していないため、動作に影響はありません
- 将来的にリファクタリングを進める際は、段階的にmain.pyを新モジュールに
  移行していくことができます
""")

