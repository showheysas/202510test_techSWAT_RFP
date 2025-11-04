"""
詳細な機能比較スクリプト
実際の処理フローが同じであることを確認
"""
import ast
import sys
from pathlib import Path
from typing import Dict, List, Set

def extract_function_body_signature(file_path: Path, func_name: str) -> Dict:
    """関数の本体とシグネチャを抽出"""
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except Exception as e:
        return {"error": str(e)}
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == func_name:
            return {
                "line": node.lineno,
                "args": [arg.arg for arg in node.args.args],
                "body_lines": len(node.body),
                "has_return": any(isinstance(n, ast.Return) for n in ast.walk(node))
            }
        elif isinstance(node, ast.AsyncFunctionDef) and node.name == func_name:
            return {
                "line": node.lineno,
                "args": [arg.arg for arg in node.args.args],
                "body_lines": len(node.body),
                "has_return": any(isinstance(n, ast.Return) for n in ast.walk(node)),
                "async": True
            }
    return {"error": "Function not found"}

def check_function_usage(file_path: Path, func_name: str) -> List[str]:
    """関数の使用箇所を抽出"""
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except Exception as e:
        return [f"Error: {e}"]
    
    usages = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            if isinstance(node.func, ast.Name) and node.func.id == func_name:
                usages.append(f"line {node.lineno}")
            elif isinstance(node.func, ast.Attribute):
                # メソッド呼び出しの場合はスキップ
                pass
    return usages

def compare_pipeline_functions():
    """パイプライン関数（process_pipeline, process_text_pipeline）の比較"""
    original_path = Path("main_original_backup.py")
    new_path = Path("main.py")
    
    pipeline_funcs = ["process_pipeline", "process_text_pipeline"]
    
    print("\n[詳細比較] パイプライン関数の確認...")
    for func_name in pipeline_funcs:
        print(f"\n  {func_name}:")
        
        original_info = extract_function_body_signature(original_path, func_name)
        new_info = extract_function_body_signature(new_path, func_name)
        
        if "error" in original_info:
            print(f"    ✗ 元のファイル: {original_info['error']}")
            continue
        if "error" in new_info:
            print(f"    ✗ 新しいファイル: {new_info['error']}")
            continue
        
        # 引数の比較
        if original_info["args"] == new_info["args"]:
            print(f"    ✓ 引数は同じ: {original_info['args']}")
        else:
            print(f"    ✗ 引数が異なります")
            print(f"      元: {original_info['args']}")
            print(f"      新: {new_info['args']}")
        
        # 使用されている関数の確認
        original_usage = check_function_usage(original_path, func_name)
        new_usage = check_function_usage(new_path, func_name)
        
        if original_usage and new_usage:
            print(f"    ✓ 両方で使用されています")
        elif original_usage and not new_usage:
            print(f"    ⚠ 元のファイルでは使用、新しいファイルでは未使用")
        elif not original_usage and new_usage:
            print(f"    ⚠ 元のファイルでは未使用、新しいファイルでは使用")

def compare_post_slack_draft():
    """post_slack_draft関数の呼び出し方法の比較"""
    original_path = Path("main_original_backup.py")
    new_path = Path("main.py")
    
    print("\n[詳細比較] post_slack_draftの呼び出し確認...")
    
    # 元のファイルでの呼び出し
    try:
        original_content = original_path.read_text(encoding="utf-8")
        original_lines = original_content.splitlines()
        
        original_calls = []
        for i, line in enumerate(original_lines, 1):
            if "post_slack_draft(" in line and not line.strip().startswith("def"):
                original_calls.append(f"line {i}: {line.strip()}")
    except Exception as e:
        print(f"    ✗ エラー: {e}")
        return
    
    # 新しいファイルでの呼び出し
    try:
        new_content = new_path.read_text(encoding="utf-8")
        new_lines = new_content.splitlines()
        
        new_calls = []
        for i, line in enumerate(new_lines, 1):
            if "post_slack_draft(" in line and not line.strip().startswith("def"):
                new_calls.append(f"line {i}: {line.strip()}")
    except Exception as e:
        print(f"    ✗ エラー: {e}")
        return
    
    print(f"    元のファイルでの呼び出し: {len(original_calls)}箇所")
    for call in original_calls[:3]:  # 最初の3つだけ表示
        print(f"      {call}")
    
    print(f"    新しいファイルでの呼び出し: {len(new_calls)}箇所")
    for call in new_calls[:3]:  # 最初の3つだけ表示
        print(f"      {call}")
    
    # 引数の比較（DRAFT_METAが追加されているか）
    if len(original_calls) == len(new_calls):
        print(f"    ✓ 呼び出し箇所の数は同じです")
    else:
        print(f"    ⚠ 呼び出し箇所の数が異なります（元: {len(original_calls)}, 新: {len(new_calls)}）")
    
    # 新しいバージョンでDRAFT_METAが引数として渡されているか確認
    has_draft_meta = any("DRAFT_META" in call for call in new_calls)
    if has_draft_meta:
        print(f"    ✓ 新しいバージョンではDRAFT_METAが引数として渡されています")
    else:
        print(f"    ⚠ 新しいバージョンでDRAFT_METAが引数として渡されていません")

def main():
    print("=" * 80)
    print("詳細な機能比較（処理フロー確認）")
    print("=" * 80)
    
    original_path = Path("main_original_backup.py")
    new_path = Path("main.py")
    
    if not original_path.exists():
        print(f"✗ エラー: {original_path} が見つかりません")
        sys.exit(1)
    if not new_path.exists():
        print(f"✗ エラー: {new_path} が見つかりません")
        sys.exit(1)
    
    # パイプライン関数の比較
    compare_pipeline_functions()
    
    # post_slack_draftの呼び出し比較
    compare_post_slack_draft()
    
    # インポートの確認
    print("\n[詳細比較] インポート文の確認...")
    try:
        new_content = new_path.read_text(encoding="utf-8")
        
        # Phase 1-3のインポートが正しく行われているか
        required_imports = [
            "from app.services.slack_service import",
            "from app.services.openai_service import",
            "from app.utils.storage import",
            "from app.config import",
            "from app.models import",
        ]
        
        fallback_imports = [
            "from services.slack_service import",
            "from services.openai_service import",
            "from utils.storage import",
            "from config import",
            "from models import",
        ]
        
        all_imports_found = True
        for import_line in required_imports + fallback_imports:
            if import_line in new_content:
                print(f"    ✓ {import_line} が見つかりました")
                break
        else:
            # どちらも見つからない場合
            print(f"    ✗ 必要なインポートが見つかりません")
            all_imports_found = False
        
        if all_imports_found:
            print("    ✓ すべての必要なインポートが存在します")
        
    except Exception as e:
        print(f"    ✗ エラー: {e}")
    
    print("\n" + "=" * 80)
    print("詳細比較完了")
    print("=" * 80)

if __name__ == "__main__":
    main()
