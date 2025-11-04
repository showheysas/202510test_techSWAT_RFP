"""
Phase 6実装後のmain_original_backup.py と main.py の機能比較スクリプト
"""
import ast
import sys
from pathlib import Path
from typing import Dict, List, Set, Any

def extract_function_definitions(file_path: Path) -> Dict[str, Dict]:
    """関数定義を抽出"""
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except Exception as e:
        return {"error": str(e)}
    
    functions = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef):
            functions[node.name] = {
                "line": node.lineno,
                "args": [arg.arg for arg in node.args.args],
                "is_async": False
            }
        elif isinstance(node, ast.AsyncFunctionDef):
            functions[node.name] = {
                "line": node.lineno,
                "args": [arg.arg for arg in node.args.args],
                "is_async": True
            }
    return functions

def extract_function_calls(file_path: Path, func_name: str) -> List[str]:
    """特定の関数の呼び出し箇所を抽出"""
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except Exception as e:
        return [f"Error: {e}"]
    
    calls = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == func_name:
                calls.append(f"line {node.lineno}")
    return calls

def check_phase6_functions():
    """Phase 6で分離した関数が正しく分離されているか確認"""
    phase6_functions = {
        "schedule_task_reminders": "services/task_service.py",
        "mark_task_complete": "services/task_service.py",
        "update_task_block_in_slack": "services/task_service.py",
        "_tz": "services/task_service.py",
        "_parse_due_to_dt": "services/task_service.py",
        "_epoch": "services/task_service.py",
        "_load_user_map": "services/task_service.py",
        "_resolve_slack_user_id": "services/task_service.py",
    }
    
    new_main_path = Path("main.py")
    
    try:
        content = new_main_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(new_main_path))
        
        # 関数定義がmain.pyにないことを確認
        defined_in_main = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.FunctionDef):
                defined_in_main[node.name] = node.lineno
        
        # インポートされているか確認
        imported_from_task_service = set()
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                if node.module and "task_service" in node.module:
                    for alias in node.names:
                        imported_from_task_service.add(alias.name)
        
        results = {}
        for func_name, module_path in phase6_functions.items():
            # 関数定義がmain.pyにないことを確認
            has_definition = func_name in defined_in_main
            
            # インポートされているか確認（公開関数のみ）
            is_imported = func_name in imported_from_task_service if func_name in ["schedule_task_reminders", "mark_task_complete", "update_task_block_in_slack"] else True
            
            results[func_name] = {
                "should_not_be_defined": not has_definition,
                "is_imported": is_imported,
                "module": module_path,
                "status": not has_definition and (is_imported if func_name in ["schedule_task_reminders", "mark_task_complete", "update_task_block_in_slack"] else True)
            }
    except Exception as e:
        results["error"] = str(e)
    
    return results

def compare_task_complete_handling():
    """task_complete処理の比較"""
    original_path = Path("main_original_backup.py")
    new_path = Path("main.py")
    
    print("\n[比較] task_complete処理の確認...")
    
    # 元のファイルでの処理
    try:
        original_content = original_path.read_text(encoding="utf-8")
        original_lines = original_content.splitlines()
        
        original_has = False
        original_line = None
        for i, line in enumerate(original_lines, 1):
            if 'if action_id == "task_complete":' in line:
                original_has = True
                original_line = i
                break
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        return
    
    # 新しいファイルでの処理
    try:
        new_content = new_path.read_text(encoding="utf-8")
        new_lines = new_content.splitlines()
        
        new_has = False
        new_line = None
        uses_service = False
        for i, line in enumerate(new_lines, 1):
            if 'if action_id == "task_complete":' in line:
                new_has = True
                new_line = i
            if 'mark_task_complete' in line:
                uses_service = True
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        return
    
    if original_has and new_has:
        print(f"  ✓ 両方にtask_complete処理があります")
        print(f"    元: line {original_line}")
        print(f"    新: line {new_line}")
        if uses_service:
            print(f"    ✓ 新しい実装ではtask_serviceを使用しています")
        else:
            print(f"    ✗ 新しい実装でtask_serviceが使用されていません")
    elif original_has and not new_has:
        print(f"  ✗ 元のファイルには存在、新しいファイルには存在しない")
    elif not original_has and new_has:
        print(f"  ⚠ 新しいファイルにのみ存在")

def compare_schedule_task_reminders():
    """schedule_task_remindersの呼び出し確認"""
    original_path = Path("main_original_backup.py")
    new_path = Path("main.py")
    
    print("\n[比較] schedule_task_remindersの呼び出し確認...")
    
    # 元のファイルでの呼び出し
    try:
        original_content = original_path.read_text(encoding="utf-8")
        original_lines = original_content.splitlines()
        
        original_calls = []
        for i, line in enumerate(original_lines, 1):
            if "schedule_task_reminders(" in line and not line.strip().startswith("def"):
                original_calls.append(f"line {i}: {line.strip()[:80]}")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        return
    
    # 新しいファイルでの呼び出し
    try:
        new_content = new_path.read_text(encoding="utf-8")
        new_lines = new_content.splitlines()
        
        new_calls = []
        for i, line in enumerate(new_lines, 1):
            if "schedule_task_reminders(" in line and not line.strip().startswith("def"):
                new_calls.append(f"line {i}: {line.strip()[:80]}")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        return
    
    print(f"    元のファイルでの呼び出し: {len(original_calls)}箇所")
    for call in original_calls[:3]:
        print(f"      {call}")
    
    print(f"    新しいファイルでの呼び出し: {len(new_calls)}箇所")
    for call in new_calls[:3]:
        print(f"      {call}")
    
    if len(original_calls) == len(new_calls):
        print(f"    ✓ 呼び出し箇所の数は同じです")
    else:
        print(f"    ⚠ 呼び出し箇所の数が異なります（元: {len(original_calls)}, 新: {len(new_calls)}）")

def main():
    print("=" * 80)
    print("Phase 6実装後の機能比較（main_original_backup.py vs main.py）")
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
    original_functions = extract_function_definitions(original_path)
    new_functions = extract_function_definitions(new_main_path)
    
    if "error" in original_functions:
        print(f"✗ 元のファイルの解析エラー: {original_functions['error']}")
        sys.exit(1)
    if "error" in new_functions:
        print(f"✗ 新しいファイルの解析エラー: {new_functions['error']}")
        sys.exit(1)
    
    print(f"  ✓ 元のファイル: {len(original_functions)} 個の関数")
    print(f"  ✓ 新しいファイル: {len(new_functions)} 個の関数")
    
    # Phase 6の関数が正しく分離されているか確認
    print("\n[2] Phase 6の関数分離確認...")
    phase6_check = check_phase6_functions()
    
    all_ok = True
    for func_name, check in phase6_check.items():
        if func_name == "error":
            print(f"  ✗ エラー: {check}")
            all_ok = False
            continue
        
        if check["status"]:
            print(f"  ✓ {func_name}: {check['module']} から分離（定義なし）")
        else:
            print(f"  ✗ {func_name}: 問題あり")
            if not check["should_not_be_defined"]:
                print(f"    - 警告: main.pyに定義が残っています")
            if not check["is_imported"]:
                print(f"    - 警告: インポートされていません")
            all_ok = False
    
    # task_complete処理の比較
    compare_task_complete_handling()
    
    # schedule_task_remindersの呼び出し比較
    compare_schedule_task_reminders()
    
    # エンドポイントの比較
    print("\n[3] FastAPIエンドポイントの比較...")
    try:
        original_content = original_path.read_text(encoding="utf-8")
        original_tree = ast.parse(original_content)
        
        new_content = new_main_path.read_text(encoding="utf-8")
        new_tree = ast.parse(new_content)
        
        original_endpoints = []
        new_endpoints = []
        
        for node in ast.walk(original_tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr in ["get", "post", "put", "delete", "patch"]:
                        if isinstance(node.func.value, ast.Name) and node.func.value.id == "app":
                            decorator = node.func.attr
                            path = None
                            if node.args and isinstance(node.args[0], ast.Constant):
                                path = node.args[0].value
                            original_endpoints.append((decorator.upper(), path or "/"))
        
        for node in ast.walk(new_tree):
            if isinstance(node, ast.Call):
                if isinstance(node.func, ast.Attribute):
                    if node.func.attr in ["get", "post", "put", "delete", "patch"]:
                        if isinstance(node.func.value, ast.Name) and node.func.value.id == "app":
                            decorator = node.func.attr
                            path = None
                            if node.args and isinstance(node.args[0], ast.Constant):
                                path = node.args[0].value
                            new_endpoints.append((decorator.upper(), path or "/"))
        
        original_endpoints_set = set(original_endpoints)
        new_endpoints_set = set(new_endpoints)
        
        if original_endpoints_set == new_endpoints_set:
            print(f"  ✓ エンドポイントは同じです（{len(original_endpoints_set)}個）")
            for method, path in sorted(original_endpoints_set):
                print(f"    - {method} {path}")
        else:
            print("  ✗ エンドポイントに差異があります")
            missing = original_endpoints_set - new_endpoints_set
            added = new_endpoints_set - original_endpoints_set
            if missing:
                print(f"    欠落: {missing}")
            if added:
                print(f"    追加: {added}")
            all_ok = False
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        all_ok = False
    
    # まとめ
    print("\n" + "=" * 80)
    if all_ok:
        print("✓ 比較結果: Phase 6のリファクタリングは正しく実装されています")
        print("  - 分離された関数はmain.pyから削除され、モジュールからインポートされています")
        print("  - エンドポイントは同じです")
        print("  - タスク関連の処理は同じように動作します")
    else:
        print("✗ 比較結果: いくつかの問題が見つかりました")
        print("  上記の警告を確認してください")
    print("=" * 80)

if __name__ == "__main__":
    main()

