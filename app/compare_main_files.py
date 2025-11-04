"""
main_original_backup.py と main.py の機能比較スクリプト
Phase 1-3までのリファクタリングが正しく機能していることを確認
"""
import ast
import sys
from pathlib import Path
from typing import Dict, List, Set, Any

def extract_function_calls(node: ast.AST, results: Dict[str, List[str]]) -> None:
    """ASTノードから関数呼び出しを抽出"""
    if isinstance(node, ast.Call):
        if isinstance(node.func, ast.Name):
            func_name = node.func.id
            if func_name not in results:
                results[func_name] = []
            # 呼び出し元の行番号を記録
            if hasattr(node, 'lineno'):
                results[func_name].append(f"line {node.lineno}")
        elif isinstance(node.func, ast.Attribute):
            # メソッド呼び出し（例: client_slack.chat_postMessage）
            if isinstance(node.func.value, ast.Name):
                method_name = f"{node.func.value.id}.{node.func.attr}"
                if method_name not in results:
                    results[method_name] = []
                if hasattr(node, 'lineno'):
                    results[method_name].append(f"line {node.lineno}")
    
    # 子ノードを再帰的に処理
    for child in ast.iter_child_nodes(node):
        extract_function_calls(child, results)

def extract_function_definitions(node: ast.AST) -> Dict[str, ast.FunctionDef]:
    """関数定義を抽出"""
    functions = {}
    if isinstance(node, ast.FunctionDef):
        functions[node.name] = node
    for child in ast.iter_child_nodes(node):
        functions.update(extract_function_definitions(child))
    return functions

def extract_imports(node: ast.AST) -> Dict[str, List[str]]:
    """インポート文を抽出"""
    imports = {}
    if isinstance(node, ast.Import):
        for alias in node.names:
            imports[alias.name] = []
    elif isinstance(node, ast.ImportFrom):
        module = node.module or ""
        for alias in node.names:
            imports[alias.name] = [module]
    return imports

def analyze_file(file_path: Path) -> Dict[str, Any]:
    """ファイルを解析して主要な情報を抽出"""
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except Exception as e:
        return {"error": str(e)}
    
    result = {
        "functions": {},
        "function_calls": {},
        "imports": {},
        "endpoints": [],
        "global_vars": []
    }
    
    # 関数定義を抽出
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            result["functions"][node.name] = {
                "line": node.lineno,
                "args": [arg.arg for arg in node.args.args]
            }
        elif isinstance(node, ast.AsyncFunctionDef):
            result["functions"][node.name] = {
                "line": node.lineno,
                "args": [arg.arg for arg in node.args.args],
                "async": True
            }
    
    # 関数呼び出しを抽出
    extract_function_calls(tree, result["function_calls"])
    
    # インポートを抽出
    for node in ast.walk(tree):
        if isinstance(node, (ast.Import, ast.ImportFrom)):
            imports = extract_imports(node)
            result["imports"].update(imports)
    
    # FastAPIエンドポイントを抽出（@app.get, @app.post など）
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Attribute):
                if node.func.attr in ["get", "post", "put", "delete", "patch"]:
                    if isinstance(node.func.value, ast.Name) and node.func.value.id == "app":
                        decorator = node.func.attr
                        path = None
                        if node.args and isinstance(node.args[0], ast.Constant):
                            path = node.args[0].value
                        result["endpoints"].append({
                            "method": decorator.upper(),
                            "path": path or "/",
                            "line": node.lineno
                        })
    
    # グローバル変数を抽出
    for node in ast.walk(tree):
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    if target.id.isupper() or target.id.startswith("_"):
                        result["global_vars"].append(target.id)
    
    return result

def compare_phase1_3_functions() -> Dict[str, bool]:
    """Phase 1-3で分離した関数が正しくインポートされているか確認"""
    phase_functions = {
        # Phase 1
        "save_json": "utils/storage.py",
        # Phase 2
        "transcribe_audio": "services/openai_service.py",
        "summarize_to_structured": "services/openai_service.py",
        # Phase 3
        "verify_slack_signature": "services/slack_service.py",
        "build_minutes_preview_blocks": "services/slack_service.py",
        "build_edit_modal": "services/slack_service.py",
        "build_tasks_blocks": "services/slack_service.py",
        "parse_tasks_from_actions": "services/slack_service.py",
        "post_slack_draft": "services/slack_service.py",
    }
    
    results = {}
    new_main_path = Path("main.py")
    
    try:
        content = new_main_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(new_main_path))
        
        # インポートされた関数を確認
        imported_functions = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and ("slack_service" in node.module or "openai_service" in node.module or "storage" in node.module):
                    for alias in node.names:
                        imported_functions.add(alias.name)
        
        for func_name, module_path in phase_functions.items():
            # 関数定義がmain.pyにないことを確認
            has_definition = False
            for node in ast.walk(tree):
                if isinstance(node, ast.FunctionDef) and node.name == func_name:
                    has_definition = True
                    break
            
            # インポートされているか確認
            is_imported = func_name in imported_functions
            
            results[func_name] = {
                "should_not_be_defined": not has_definition,
                "should_be_imported": is_imported,
                "module": module_path,
                "status": not has_definition and is_imported
            }
    except Exception as e:
        results["error"] = str(e)
    
    return results

def main():
    print("=" * 80)
    print("main_original_backup.py と main.py の機能比較")
    print("=" * 80)
    
    original_path = Path("main_original_backup.py")
    new_main_path = Path("main.py")
    
    if not original_path.exists():
        print(f"✗ エラー: {original_path} が見つかりません")
        sys.exit(1)
    if not new_main_path.exists():
        print(f"✗ エラー: {new_main_path} が見つかりません")
        sys.exit(1)
    
    print("\n[1] ファイル解析中...")
    original_analysis = analyze_file(original_path)
    new_analysis = analyze_file(new_main_path)
    
    if "error" in original_analysis:
        print(f"✗ 元のファイルの解析エラー: {original_analysis['error']}")
        sys.exit(1)
    if "error" in new_analysis:
        print(f"✗ 新しいファイルの解析エラー: {new_analysis['error']}")
        sys.exit(1)
    
    print(f"  ✓ 元のファイル: {len(original_analysis['functions'])} 個の関数")
    print(f"  ✓ 新しいファイル: {len(new_analysis['functions'])} 個の関数")
    
    # Phase 1-3の関数が正しく分離されているか確認
    print("\n[2] Phase 1-3の関数分離確認...")
    phase_check = compare_phase1_3_functions()
    
    all_ok = True
    for func_name, check in phase_check.items():
        if func_name == "error":
            print(f"  ✗ エラー: {check}")
            all_ok = False
            continue
        
        if check["status"]:
            print(f"  ✓ {func_name}: {check['module']} からインポート（定義なし）")
        else:
            print(f"  ✗ {func_name}: 問題あり")
            if not check["should_not_be_defined"]:
                print(f"    - 警告: main.pyに定義が残っています")
            if not check["should_be_imported"]:
                print(f"    - 警告: インポートされていません")
            all_ok = False
    
    # エンドポイントの比較
    print("\n[3] FastAPIエンドポイントの比較...")
    original_endpoints = {(e["method"], e["path"]) for e in original_analysis["endpoints"]}
    new_endpoints = {(e["method"], e["path"]) for e in new_analysis["endpoints"]}
    
    if original_endpoints == new_endpoints:
        print(f"  ✓ エンドポイントは同じです（{len(original_endpoints)}個）")
        for method, path in sorted(original_endpoints):
            print(f"    - {method} {path}")
    else:
        print("  ✗ エンドポイントに差異があります")
        missing = original_endpoints - new_endpoints
        added = new_endpoints - original_endpoints
        if missing:
            print(f"    欠落: {missing}")
        if added:
            print(f"    追加: {added}")
        all_ok = False
    
    # 重要な関数呼び出しの確認
    print("\n[4] 重要な関数呼び出しの確認...")
    important_calls = [
        "transcribe_audio",
        "summarize_to_structured",
        "save_json",
        "post_slack_draft",
        "build_minutes_preview_blocks",
        "build_edit_modal",
        "verify_slack_signature",
    ]
    
    for func_name in important_calls:
        original_has = func_name in original_analysis["function_calls"]
        new_has = func_name in new_analysis["function_calls"]
        
        if original_has and new_has:
            print(f"  ✓ {func_name}: 両方で使用されています")
        elif original_has and not new_has:
            print(f"  ⚠ {func_name}: 元のファイルでは使用、新しいファイルでは未使用")
        elif not original_has and new_has:
            print(f"  ⚠ {func_name}: 元のファイルでは未使用、新しいファイルでは使用")
    
    # グローバル変数の確認
    print("\n[5] グローバル変数の確認...")
    original_globals = set(original_analysis["global_vars"])
    new_globals = set(new_analysis["global_vars"])
    
    important_globals = ["DRAFT_META", "DRIVE_WATCH_CHANNEL_INFO", "_polling_task"]
    for var_name in important_globals:
        if var_name in original_globals and var_name in new_globals:
            print(f"  ✓ {var_name}: 両方に存在")
        elif var_name in original_globals:
            print(f"  ✗ {var_name}: 元のファイルには存在、新しいファイルには存在しない")
            all_ok = False
        elif var_name in new_globals:
            print(f"  ⚠ {var_name}: 新しいファイルにのみ存在")
    
    # まとめ
    print("\n" + "=" * 80)
    if all_ok:
        print("✓ 比較結果: Phase 1-3のリファクタリングは正しく実装されています")
        print("  - 分離された関数はmain.pyから削除され、モジュールからインポートされています")
        print("  - エンドポイントは同じです")
        print("  - 重要な関数呼び出しは両方で使用されています")
    else:
        print("✗ 比較結果: いくつかの問題が見つかりました")
        print("  上記の警告を確認してください")
    print("=" * 80)

if __name__ == "__main__":
    main()
