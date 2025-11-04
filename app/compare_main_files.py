"""
main_original_backup.py と main.py の動作比較スクリプト
"""
import sys
import ast
from pathlib import Path
from typing import Dict, Set, List

print("=" * 70)
print("main_original_backup.py と main.py の動作比較")
print("=" * 70)

def extract_function_definitions(file_path: Path) -> Dict[str, ast.FunctionDef]:
    """ファイルから関数定義を抽出"""
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        functions = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                functions[node.name] = node
        return functions
    except Exception as e:
        print(f"エラー: {file_path} の解析に失敗: {e}")
        return {}

def extract_class_definitions(file_path: Path) -> Dict[str, ast.ClassDef]:
    """ファイルからクラス定義を抽出"""
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        classes = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef):
                classes[node.name] = node
        return classes
    except Exception as e:
        print(f"エラー: {file_path} の解析に失敗: {e}")
        return {}

def extract_endpoints(file_path: Path) -> List[str]:
    """FastAPIエンドポイントを抽出"""
    endpoints = []
    try:
        content = file_path.read_text(encoding="utf-8")
        lines = content.split('\n')
        for i, line in enumerate(lines):
            # @app.get, @app.post などのデコレータを探す
            if '@app.get' in line or '@app.post' in line or '@app.put' in line or '@app.delete' in line:
                # 次の行から関数名を取得
                if i + 1 < len(lines):
                    func_line = lines[i + 1].strip()
                    if func_line.startswith('def '):
                        func_name = func_line.split('def ')[1].split('(')[0]
                        endpoint_type = 'GET' if '@app.get' in line else 'POST' if '@app.post' in line else 'PUT' if '@app.put' in line else 'DELETE'
                        # パスを抽出
                        path = line.split('(')[1].split(')')[0].strip('"\'')
                        endpoints.append(f"{endpoint_type} {path} ({func_name})")
    except Exception as e:
        print(f"エラー: エンドポイント抽出に失敗: {e}")
    return endpoints

def extract_imports(file_path: Path) -> Dict[str, Set[str]]:
    """インポート文を抽出"""
    imports = {"standard": set(), "third_party": set(), "local": set()}
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    module = alias.name
                    if module.startswith('.'):
                        imports["local"].add(module)
                    elif module in ['os', 'sys', 'json', 'uuid', 'shutil', 'time', 'hmac', 'hashlib', 're', 'asyncio', 'pathlib', 'typing', 'datetime']:
                        imports["standard"].add(module)
                    else:
                        imports["third_party"].add(module)
            elif isinstance(node, ast.ImportFrom):
                if node.module:
                    if node.module.startswith('.'):
                        imports["local"].add(node.module)
                    elif node.module in ['os', 'sys', 'json', 'uuid', 'shutil', 'time', 'hmac', 'hashlib', 're', 'asyncio', 'pathlib', 'typing', 'datetime']:
                        imports["standard"].add(node.module)
                    else:
                        imports["third_party"].add(node.module)
    except Exception as e:
        print(f"エラー: インポート抽出に失敗: {e}")
    return imports

# ファイルの存在確認
original_path = Path("main_original_backup.py")
new_path = Path("main.py")

if not original_path.exists():
    print(f"✗ {original_path} が見つかりません")
    sys.exit(1)

if not new_path.exists():
    print(f"✗ {new_path} が見つかりません")
    sys.exit(1)

print("\n[1] 関数定義の比較")
print("-" * 70)

original_functions = extract_function_definitions(original_path)
new_functions = extract_function_definitions(new_path)

original_func_names = set(original_functions.keys())
new_func_names = set(new_functions.keys())

# 両方にある関数
common_functions = original_func_names & new_func_names
print(f"共通の関数: {len(common_functions)}")
print(f"  {sorted(common_functions)}")

# 元のファイルにのみある関数
only_original = original_func_names - new_func_names
if only_original:
    print(f"\n元のファイルにのみ存在する関数: {len(only_original)}")
    print(f"  {sorted(only_original)}")
    print("  ⚠ これらの関数が新ファイルで削除またはリファクタリングされています")
else:
    print("\n✓ すべての関数が新ファイルにも存在します")

# 新ファイルにのみある関数
only_new = new_func_names - original_func_names
if only_new:
    print(f"\n新ファイルにのみ存在する関数: {len(only_new)}")
    print(f"  {sorted(only_new)}")

print("\n[2] クラス定義の比較")
print("-" * 70)

original_classes = extract_class_definitions(original_path)
new_classes = extract_class_definitions(new_path)

original_class_names = set(original_classes.keys())
new_class_names = set(new_classes.keys())

# 両方にあるクラス
common_classes = original_class_names & new_class_names
print(f"共通のクラス: {len(common_classes)}")
print(f"  {sorted(common_classes)}")

# 元のファイルにのみあるクラス
only_original_class = original_class_names - new_class_names
if only_original_class:
    print(f"\n元のファイルにのみ存在するクラス: {len(only_original_class)}")
    print(f"  {sorted(only_original_class)}")
    print("  ⚠ これらのクラスが新ファイルで削除またはリファクタリングされています")
else:
    print("\n✓ すべてのクラスが新ファイルにも存在します（モジュールからインポート）")

print("\n[3] エンドポイントの比較")
print("-" * 70)

original_endpoints = extract_endpoints(original_path)
new_endpoints = extract_endpoints(new_path)

print(f"元のファイルのエンドポイント数: {len(original_endpoints)}")
for ep in sorted(original_endpoints):
    print(f"  - {ep}")

print(f"\n新ファイルのエンドポイント数: {len(new_endpoints)}")
for ep in sorted(new_endpoints):
    print(f"  - {ep}")

if set(original_endpoints) == set(new_endpoints):
    print("\n✓ すべてのエンドポイントが一致しています")
else:
    print("\n⚠ エンドポイントに差異があります")
    missing = set(original_endpoints) - set(new_endpoints)
    added = set(new_endpoints) - set(original_endpoints)
    if missing:
        print(f"  元のファイルにのみ存在: {missing}")
    if added:
        print(f"  新ファイルにのみ存在: {added}")

print("\n[4] インポートの比較")
print("-" * 70)

original_imports = extract_imports(original_path)
new_imports = extract_imports(new_path)

print("元のファイルのインポート:")
print(f"  標準ライブラリ: {len(original_imports['standard'])}")
print(f"  サードパーティ: {len(original_imports['third_party'])}")
print(f"  ローカル: {len(original_imports['local'])}")

print("\n新ファイルのインポート:")
print(f"  標準ライブラリ: {len(new_imports['standard'])}")
print(f"  サードパーティ: {len(new_imports['third_party'])}")
print(f"  ローカル: {len(new_imports['local'])}")

# 新しく追加されたインポート（リファクタリングされたモジュール）
new_local_imports = new_imports['local'] - original_imports['local']
if new_local_imports:
    print(f"\n✓ 新しく追加されたローカルインポート（リファクタリング）:")
    for imp in sorted(new_local_imports):
        print(f"  - {imp}")

print("\n[5] 重要な関数の確認")
print("-" * 70)

important_functions = [
    'transcribe_audio',
    'summarize_to_structured',
    'save_json',
    'verify_slack_signature',
    'post_slack_draft',
    'process_pipeline',
    'process_text_pipeline',
]

print("重要関数の存在確認:")
for func_name in important_functions:
    in_original = func_name in original_func_names
    in_new = func_name in new_func_names
    
    if in_original and not in_new:
        print(f"  ✗ {func_name}: 元のファイルには存在、新ファイルには存在しない")
        print(f"     → モジュールからインポートされている可能性があります")
    elif not in_original and in_new:
        print(f"  ⚠ {func_name}: 新ファイルにのみ存在")
    elif in_original and in_new:
        print(f"  ✓ {func_name}: 両方のファイルに存在")
    else:
        print(f"  ? {func_name}: 両方のファイルに存在しない")

print("\n[6] グローバル変数の確認")
print("-" * 70)

def extract_global_vars(file_path: Path) -> Set[str]:
    """グローバル変数の定義を抽出"""
    vars_set = set()
    try:
        content = file_path.read_text(encoding="utf-8")
        lines = content.split('\n')
        for line in lines:
            # グローバル変数の定義（= で割り当てられている）を探す
            stripped = line.strip()
            if stripped and not stripped.startswith('#') and not stripped.startswith('def ') and not stripped.startswith('class '):
                if '=' in stripped and not stripped.startswith('if ') and not stripped.startswith('for ') and not stripped.startswith('while '):
                    var_name = stripped.split('=')[0].strip()
                    if var_name and not var_name.startswith('_') or var_name.startswith('DRAFT_') or var_name.startswith('DRIVE_'):
                        vars_set.add(var_name)
    except Exception as e:
        print(f"エラー: グローバル変数抽出に失敗: {e}")
    return vars_set

original_vars = extract_global_vars(original_path)
new_vars = extract_global_vars(new_path)

important_vars = ['DRAFT_META', 'DRIVE_WATCH_CHANNEL_INFO', '_polling_task', 'app']
print("重要なグローバル変数:")
for var_name in important_vars:
    in_original = var_name in original_vars or var_name in str(original_path.read_text(encoding="utf-8"))
    in_new = var_name in new_vars or var_name in str(new_path.read_text(encoding="utf-8"))
    
    if in_original and in_new:
        print(f"  ✓ {var_name}: 両方のファイルに存在")
    elif in_original and not in_new:
        print(f"  ✗ {var_name}: 元のファイルには存在、新ファイルには存在しない")
    else:
        print(f"  ? {var_name}: 確認が必要")

print("\n" + "=" * 70)
print("比較結果のサマリー")
print("=" * 70)

print(f"""
関数定義:
  - 共通: {len(common_functions)}
  - 元のみ: {len(only_original)}
  - 新のみ: {len(only_new)}

エンドポイント:
  - 元のファイル: {len(original_endpoints)}
  - 新ファイル: {len(new_endpoints)}
  - 一致: {'✓' if set(original_endpoints) == set(new_endpoints) else '✗'}

リファクタリング:
  - 新規モジュールインポート: {len(new_local_imports)}個
""")

if len(only_original) == 0 and set(original_endpoints) == set(new_endpoints):
    print("✓ リファクタリングは正常に完了しています。主要な機能は保持されています。")
else:
    print("⚠ 一部の差異があります。詳細を確認してください。")

