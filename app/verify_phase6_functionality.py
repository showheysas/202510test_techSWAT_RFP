"""
Phase 6実装後の詳細な機能比較スクリプト
処理フローが同じであることを確認
"""
import ast
import sys
from pathlib import Path
from typing import Dict

def extract_function_body(file_path: Path, func_name: str) -> Dict:
    """関数の本体を抽出"""
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except Exception as e:
        return {"error": str(e)}
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return {
                "line": node.lineno,
                "end_line": node.end_lineno if hasattr(node, 'end_lineno') else None,
                "args": [arg.arg for arg in node.args.args],
                "body_length": len(node.body)
            }
        elif isinstance(node, ast.AsyncFunctionDef) and node.name == func_name:
            return {
                "line": node.lineno,
                "end_line": node.end_lineno if hasattr(node, 'end_lineno') else None,
                "args": [arg.arg for arg in node.args.args],
                "body_length": len(node.body),
                "async": True
            }
    return {"error": "Function not found"}

def compare_task_complete_implementation():
    """task_complete処理の実装を比較"""
    original_path = Path("main_original_backup.py")
    new_path = Path("main.py")
    
    print("\n[詳細比較] task_complete処理の実装...")
    
    try:
        original_content = original_path.read_text(encoding="utf-8")
        original_lines = original_content.splitlines()
        
        new_content = new_path.read_text(encoding="utf-8")
        new_lines = new_content.splitlines()
        
        # 元のファイルでのtask_complete処理
        original_start = None
        original_end = None
        for i, line in enumerate(original_lines, 1):
            if 'if action_id == "task_complete":' in line:
                original_start = i
            if original_start and i > original_start and line.strip() and not line.startswith(' ') and not line.startswith('\t'):
                if 'if action_id ==' in line or 'return JSONResponse' in line:
                    original_end = i - 1
                    break
        
        # 新しいファイルでのtask_complete処理
        new_start = None
        new_end = None
        for i, line in enumerate(new_lines, 1):
            if 'if action_id == "task_complete":' in line:
                new_start = i
            if new_start and i > new_start and line.strip() and not line.startswith(' ') and not line.startswith('\t'):
                if 'if action_id ==' in line or 'return JSONResponse' in line:
                    new_end = i - 1
                    break
        
        if original_start and new_start:
            print(f"  元の実装: line {original_start}-{original_end or '?'} ({original_end - original_start if original_end else '?'}行)")
            print(f"  新しい実装: line {new_start}-{new_end or '?'} ({new_end - new_start if new_end else '?'}行)")
            
            # 新しい実装がサービスを使用しているか確認
            uses_mark_task_complete = any('mark_task_complete' in line for line in new_lines[new_start-1:new_end or len(new_lines)])
            uses_update_task_block = any('update_task_block_in_slack' in line for line in new_lines[new_start-1:new_end or len(new_lines)])
            
            if uses_mark_task_complete and uses_update_task_block:
                print(f"    ✓ 新しい実装はtask_serviceを使用しています")
            else:
                print(f"    ⚠ 新しい実装でtask_serviceが使用されていない可能性")
                if not uses_mark_task_complete:
                    print(f"      - mark_task_completeが使用されていません")
                if not uses_update_task_block:
                    print(f"      - update_task_block_in_slackが使用されていません")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
        import traceback
        traceback.print_exc()

def compare_schedule_task_reminders_usage():
    """schedule_task_remindersの使用箇所を比較"""
    original_path = Path("main_original_backup.py")
    new_path = Path("main.py")
    
    print("\n[詳細比較] schedule_task_remindersの使用箇所...")
    
    try:
        original_content = original_path.read_text(encoding="utf-8")
        original_lines = original_content.splitlines()
        
        new_content = new_path.read_text(encoding="utf-8")
        new_lines = new_content.splitlines()
        
        original_usage = []
        for i, line in enumerate(original_lines, 1):
            if "schedule_task_reminders(" in line and not line.strip().startswith("def"):
                # 前後のコンテキストを取得
                context_start = max(0, i - 2)
                context_end = min(len(original_lines), i + 2)
                context = "\n".join([f"  {j}: {original_lines[j-1]}" for j in range(context_start+1, context_end+1)])
                original_usage.append(f"line {i}\n{context}")
        
        new_usage = []
        for i, line in enumerate(new_lines, 1):
            if "schedule_task_reminders(" in line and not line.strip().startswith("def"):
                # 前後のコンテキストを取得
                context_start = max(0, i - 2)
                context_end = min(len(new_lines), i + 2)
                context = "\n".join([f"  {j}: {new_lines[j-1]}" for j in range(context_start+1, context_end+1)])
                new_usage.append(f"line {i}\n{context}")
        
        print(f"    元のファイル: {len(original_usage)}箇所")
        if original_usage:
            print(f"      {original_usage[0][:200]}...")
        
        print(f"    新しいファイル: {len(new_usage)}箇所")
        if new_usage:
            print(f"      {new_usage[0][:200]}...")
        
        if len(original_usage) == len(new_usage):
            print(f"    ✓ 呼び出し箇所の数は同じです")
        else:
            print(f"    ⚠ 呼び出し箇所の数が異なります")
    except Exception as e:
        print(f"  ✗ エラー: {e}")

def check_task_service_imports():
    """task_serviceのインポートを確認"""
    new_path = Path("main.py")
    
    print("\n[詳細比較] task_serviceのインポート確認...")
    
    try:
        content = new_path.read_text(encoding="utf-8")
        
        # Phase 6のインポートが正しく行われているか
        required_imports = [
            "from app.services.task_service import",
            "schedule_task_reminders",
            "mark_task_complete",
            "update_task_block_in_slack",
        ]
        
        fallback_imports = [
            "from services.task_service import",
        ]
        
        all_imports_found = True
        for import_line in required_imports:
            if import_line in content:
                print(f"    ✓ {import_line} が見つかりました")
            else:
                # fallbackをチェック
                if import_line.startswith("from ") and any(fallback in content for fallback in fallback_imports):
                    print(f"    ✓ {import_line} が見つかりました（フォールバック形式）")
                else:
                    print(f"    ✗ {import_line} が見つかりません")
                    all_imports_found = False
        
        if all_imports_found:
            print("    ✓ すべての必要なインポートが存在します")
        
    except Exception as e:
        print(f"    ✗ エラー: {e}")

def main():
    print("=" * 80)
    print("Phase 6実装後の詳細な機能比較（処理フロー確認）")
    print("=" * 80)
    
    original_path = Path("main_original_backup.py")
    new_path = Path("main.py")
    
    if not original_path.exists():
        print(f"✗ エラー: {original_path} が見つかりません")
        sys.exit(1)
    if not new_path.exists():
        print(f"✗ エラー: {new_path} が見つかりません")
        sys.exit(1)
    
    # task_complete処理の比較
    compare_task_complete_implementation()
    
    # schedule_task_remindersの使用箇所比較
    compare_schedule_task_reminders_usage()
    
    # task_serviceのインポート確認
    check_task_service_imports()
    
    print("\n" + "=" * 80)
    print("詳細比較完了")
    print("=" * 80)

if __name__ == "__main__":
    main()

