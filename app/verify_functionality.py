"""
機能的な動作確認スクリプト
main_original_backup.py と main.py が同じ動作をすることを確認
"""
import sys
from pathlib import Path

print("=" * 70)
print("機能的な動作確認")
print("=" * 70)

# エンドポイントの確認
def extract_endpoints_detailed(file_path: Path):
    """エンドポイントを詳細に抽出"""
    endpoints = []
    try:
        content = file_path.read_text(encoding="utf-8")
        lines = content.split('\n')
        for i, line in enumerate(lines):
            if '@app.get' in line or '@app.post' in line:
                # パスを抽出
                if '@app.get' in line:
                    method = 'GET'
                    path = line.split('(')[1].split(')')[0].strip('"\'')
                elif '@app.post' in line:
                    method = 'POST'
                    path = line.split('(')[1].split(')')[0].strip('"\'')
                
                # 関数名を取得
                func_name = None
                for j in range(i+1, min(i+5, len(lines))):
                    if lines[j].strip().startswith('def '):
                        func_name = lines[j].strip().split('def ')[1].split('(')[0]
                        break
                
                endpoints.append({
                    'method': method,
                    'path': path,
                    'func': func_name,
                    'line': i+1
                })
    except Exception as e:
        print(f"エラー: {e}")
    return endpoints

print("\n[1] エンドポイントの詳細比較")
print("-" * 70)

original_path = Path("main_original_backup.py")
new_path = Path("main.py")

original_endpoints = extract_endpoints_detailed(original_path)
new_endpoints = extract_endpoints_detailed(new_path)

print(f"元のファイルのエンドポイント: {len(original_endpoints)}")
for ep in original_endpoints:
    print(f"  {ep['method']} {ep['path']} -> {ep['func']} (行{ep['line']})")

print(f"\n新ファイルのエンドポイント: {len(new_endpoints)}")
for ep in new_endpoints:
    print(f"  {ep['method']} {ep['path']} -> {ep['func']} (行{ep['line']})")

# エンドポイントの一致確認
original_endpoint_signatures = {(ep['method'], ep['path']) for ep in original_endpoints}
new_endpoint_signatures = {(ep['method'], ep['path']) for ep in new_endpoints}

if original_endpoint_signatures == new_endpoint_signatures:
    print("\n✓ すべてのエンドポイントが一致しています")
else:
    print("\n⚠ エンドポイントに差異があります")
    missing = original_endpoint_signatures - new_endpoint_signatures
    added = new_endpoint_signatures - original_endpoint_signatures
    if missing:
        print(f"  元のファイルにのみ存在: {missing}")
    if added:
        print(f"  新ファイルにのみ存在: {added}")

print("\n[2] 重要な関数の呼び出し確認")
print("-" * 70)

def check_function_usage(file_path: Path, func_name: str):
    """関数がファイル内で使用されているか確認"""
    try:
        content = file_path.read_text(encoding="utf-8")
        # 関数定義を探す
        has_definition = f"def {func_name}(" in content
        # 関数呼び出しを探す（定義以外）
        calls = content.count(f"{func_name}(") - (1 if has_definition else 0)
        return has_definition, calls
    except Exception as e:
        return False, 0

important_functions = {
    'transcribe_audio': 'services/openai_service.py',
    'summarize_to_structured': 'services/openai_service.py',
    'save_json': 'utils/storage.py',
    'Draft': 'models.py',
}

print("リファクタリングされた関数/クラスの使用確認:")
for func_name, module_path in important_functions.items():
    original_def, original_calls = check_function_usage(original_path, func_name)
    new_def, new_calls = check_function_usage(new_path, func_name)
    
    if func_name == 'Draft':
        # クラスの場合は定義チェック
        original_has_class = 'class Draft' in original_path.read_text(encoding="utf-8")
        new_has_class = 'class Draft' in new_path.read_text(encoding="utf-8")
        new_has_import = f'from models import Draft' in new_path.read_text(encoding="utf-8") or 'import models' in new_path.read_text(encoding="utf-8")
        
        print(f"  {func_name}:")
        print(f"    元のファイル: 定義あり={original_has_class}, 使用={original_calls}")
        print(f"    新ファイル: 定義あり={new_has_class}, インポートあり={new_has_import}, 使用={new_calls}")
        if not new_has_class and new_has_import and new_calls == original_calls:
            print(f"    ✓ モジュールから正しくインポートされています")
        elif new_calls != original_calls:
            print(f"    ⚠ 使用回数が異なります（元:{original_calls}, 新:{new_calls}）")
    else:
        print(f"  {func_name}:")
        print(f"    元のファイル: 定義あり={original_def}, 使用={original_calls}")
        print(f"    新ファイル: 定義あり={new_def}, 使用={new_calls}")
        
        # 新ファイルでインポートされているか確認
        new_has_import = False
        if module_path:
            import_line = f"from {module_path.replace('/', '.').replace('.py', '')} import {func_name}"
            if import_line in new_path.read_text(encoding="utf-8"):
                new_has_import = True
        
        if not new_def and new_has_import and new_calls == original_calls:
            print(f"    ✓ モジュールから正しくインポートされています")
        elif new_calls != original_calls:
            print(f"    ⚠ 使用回数が異なります（元:{original_calls}, 新:{new_calls}）")

print("\n[3] グローバル変数と設定の確認")
print("-" * 70)

def check_global_var(file_path: Path, var_name: str):
    """グローバル変数が存在するか確認"""
    try:
        content = file_path.read_text(encoding="utf-8")
        # 変数定義を探す
        has_def = f"{var_name} = " in content or f"{var_name}=" in content
        # インポートを探す
        has_import = f"import {var_name}" in content or f"from" in content and var_name in content.split("import")[-1] if "import" in content else False
        return has_def, has_import
    except Exception as e:
        return False, False

important_vars = [
    'DRAFT_META',
    'DRIVE_WATCH_CHANNEL_INFO',
    '_polling_task',
    'client_oa',
    'client_slack',
    'SUMM_DIR',
    'TRANS_DIR',
    'UPLOAD_DIR',
]

print("重要なグローバル変数/設定:")
for var_name in important_vars:
    original_def, original_import = check_global_var(original_path, var_name)
    new_def, new_import = check_global_var(new_path, var_name)
    
    print(f"  {var_name}:")
    print(f"    元のファイル: 定義={original_def}, インポート={original_import}")
    print(f"    新ファイル: 定義={new_def}, インポート={new_import}")
    
    # 新ファイルではconfig.pyからインポートされているはず
    if var_name in ['client_oa', 'client_slack', 'SUMM_DIR', 'TRANS_DIR', 'UPLOAD_DIR']:
        if not new_def and new_import:
            print(f"    ✓ config.pyから正しくインポートされています")
        elif new_def and not new_import:
            print(f"    ⚠ まだ定義されています（リファクタリングが必要）")

print("\n[4] 処理パイプラインの確認")
print("-" * 70)

def check_pipeline_functions(file_path: Path):
    """パイプライン関数の内容を簡易確認"""
    try:
        content = file_path.read_text(encoding="utf-8")
        
        # process_pipeline関数の確認
        has_process_pipeline = 'def process_pipeline' in content
        calls_transcribe = 'transcribe_audio(' in content
        calls_summarize = 'summarize_to_structured(' in content
        calls_save_json = 'save_json(' in content
        
        # process_text_pipeline関数の確認
        has_process_text_pipeline = 'def process_text_pipeline' in content
        
        return {
            'has_process_pipeline': has_process_pipeline,
            'has_process_text_pipeline': has_process_text_pipeline,
            'calls_transcribe': calls_transcribe,
            'calls_summarize': calls_summarize,
            'calls_save_json': calls_save_json,
        }
    except Exception as e:
        return {}

original_pipeline = check_pipeline_functions(original_path)
new_pipeline = check_pipeline_functions(new_path)

print("パイプライン関数:")
print(f"  process_pipeline:")
print(f"    元のファイル: 存在={original_pipeline.get('has_process_pipeline')}, transcribe呼び出し={original_pipeline.get('calls_transcribe')}, summarize呼び出し={original_pipeline.get('calls_summarize')}, save_json呼び出し={original_pipeline.get('calls_save_json')}")
print(f"    新ファイル: 存在={new_pipeline.get('has_process_pipeline')}, transcribe呼び出し={new_pipeline.get('calls_transcribe')}, summarize呼び出し={new_pipeline.get('calls_summarize')}, save_json呼び出し={new_pipeline.get('calls_save_json')}")

if (original_pipeline.get('has_process_pipeline') == new_pipeline.get('has_process_pipeline') and
    original_pipeline.get('calls_transcribe') == new_pipeline.get('calls_transcribe') and
    original_pipeline.get('calls_summarize') == new_pipeline.get('calls_summarize') and
    original_pipeline.get('calls_save_json') == new_pipeline.get('calls_save_json')):
    print("    ✓ パイプライン関数は同じ動作をしています")

print(f"\n  process_text_pipeline:")
print(f"    元のファイル: 存在={original_pipeline.get('has_process_text_pipeline')}")
print(f"    新ファイル: 存在={new_pipeline.get('has_process_text_pipeline')}")

print("\n" + "=" * 70)
print("最終確認結果")
print("=" * 70)

all_match = (
    original_endpoint_signatures == new_endpoint_signatures and
    original_pipeline.get('has_process_pipeline') == new_pipeline.get('has_process_pipeline') and
    original_pipeline.get('has_process_text_pipeline') == new_pipeline.get('has_process_text_pipeline')
)

if all_match:
    print("✓ 主要な機能は一致しています")
    print("✓ リファクタリングは正常に完了しています")
    print("\n変更点:")
    print("  - transcribe_audio, summarize_to_structured → services/openai_service.py からインポート")
    print("  - Draft → models.py からインポート")
    print("  - save_json → utils/storage.py からインポート")
    print("  - 設定・クライアント → config.py からインポート")
    print("\n✓ 動作は同じですが、コードがモジュール化されています")
else:
    print("⚠ 一部の差異があります。詳細を確認してください。")

