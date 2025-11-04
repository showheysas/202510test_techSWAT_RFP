"""
重複投稿の原因調査スクリプト
Phase 3で分離したpost_slack_draft関数の実装を確認
"""
import ast
from pathlib import Path

def extract_post_slack_draft_implementation(file_path: Path):
    """post_slack_draft関数の実装を抽出"""
    try:
        content = file_path.read_text(encoding="utf-8")
        tree = ast.parse(content, filename=str(file_path))
    except Exception as e:
        return {"error": str(e)}
    
    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "post_slack_draft":
            # 関数の本体を抽出
            lines = content.splitlines()
            start_line = node.lineno
            end_line = node.end_lineno if hasattr(node, 'end_lineno') else start_line + len(node.body)
            
            # 引数を抽出
            args = [arg.arg for arg in node.args.args]
            
            # 重複チェックのロジックを確認
            has_duplicate_check = False
            uses_global = False
            uses_param = False
            
            for child in ast.walk(node):
                if isinstance(child, ast.If):
                    # 重複チェックのif文を探す
                    if isinstance(child.test, ast.Compare):
                        has_duplicate_check = True
                elif isinstance(child, ast.Name):
                    if child.id == "DRAFT_META":
                        uses_global = True
                elif isinstance(child, ast.Subscript):
                    if isinstance(child.value, ast.Name) and child.value.id == "draft_meta":
                        uses_param = True
            
            return {
                "line": start_line,
                "end_line": end_line,
                "args": args,
                "body_preview": "\n".join(lines[start_line-1:min(start_line+20, len(lines))]),
                "has_duplicate_check": has_duplicate_check,
                "uses_global": uses_global,
                "uses_param": uses_param
            }
    
    return {"error": "Function not found"}

def main():
    print("=" * 80)
    print("重複投稿の原因調査")
    print("=" * 80)
    
    original_path = Path("main_original_backup.py")
    new_service_path = Path("services/slack_service.py")
    new_main_path = Path("main.py")
    
    print("\n[1] 元の実装（main_original_backup.py）の確認...")
    original_impl = extract_post_slack_draft_implementation(original_path)
    if "error" in original_impl:
        print(f"  ✗ エラー: {original_impl['error']}")
    else:
        print(f"  行番号: {original_impl['line']}-{original_impl['end_line']}")
        print(f"  引数: {original_impl['args']}")
        print(f"  重複チェック: {'あり' if original_impl['has_duplicate_check'] else 'なし'}")
        print(f"  グローバル変数使用: {'あり' if original_impl['uses_global'] else 'なし'}")
        print(f"  パラメータ使用: {'あり' if original_impl['uses_param'] else 'なし'}")
    
    print("\n[2] 新しい実装（services/slack_service.py）の確認...")
    new_service_impl = extract_post_slack_draft_implementation(new_service_path)
    if "error" in new_service_impl:
        print(f"  ✗ エラー: {new_service_impl['error']}")
    else:
        print(f"  行番号: {new_service_impl['line']}-{new_service_impl['end_line']}")
        print(f"  引数: {new_service_impl['args']}")
        print(f"  重複チェック: {'あり' if new_service_impl['has_duplicate_check'] else 'なし'}")
        print(f"  グローバル変数使用: {'あり' if new_service_impl['uses_global'] else 'なし'}")
        print(f"  パラメータ使用: {'あり' if new_service_impl['uses_param'] else 'なし'}")
    
    print("\n[3] 比較分析...")
    if "error" not in original_impl and "error" not in new_service_impl:
        # 引数の比較
        if original_impl["args"] != new_service_impl["args"]:
            print(f"  ⚠ 引数が異なります")
            print(f"    元: {original_impl['args']}")
            print(f"    新: {new_service_impl['args']}")
            print(f"    → 新しい実装では 'draft_meta' を引数として受け取るように変更されています")
            print(f"    → これは正しい変更ですが、呼び出し側でグローバル変数の参照を渡す必要があります")
        
        # 重複チェックの比較
        if original_impl["has_duplicate_check"] and new_service_impl["has_duplicate_check"]:
            print(f"  ✓ 両方とも重複チェックがあります")
        else:
            print(f"  ✗ 重複チェックに差異があります")
    
    # 呼び出し箇所の確認
    print("\n[4] main.pyでの呼び出し確認...")
    try:
        new_main_content = new_main_path.read_text(encoding="utf-8")
        lines = new_main_content.splitlines()
        
        call_count = 0
        for i, line in enumerate(lines, 1):
            if "post_slack_draft(" in line and not line.strip().startswith("def"):
                call_count += 1
                print(f"  呼び出し {call_count}: line {i}")
                print(f"    {line.strip()[:100]}")
                # DRAFT_METAが引数として渡されているか確認
                if "DRAFT_META" in line:
                    print(f"    ✓ DRAFT_METAが引数として渡されています")
                else:
                    print(f"    ✗ DRAFT_METAが引数として渡されていません！")
    except Exception as e:
        print(f"  ✗ エラー: {e}")
    
    print("\n" + "=" * 80)
    print("調査結果の要約")
    print("=" * 80)
    print("\n可能性のある原因:")
    print("1. post_slack_draft関数は正しく分離されています")
    print("2. draft_metaパラメータとして渡されていますが、参照が正しく機能しているか確認が必要")
    print("3. 重複チェックのロジックは同じですが、draft_metaの更新タイミングに問題がある可能性")
    print("\n確認すべき点:")
    print("- DRAFT_METAが正しく参照渡しされているか（Pythonでは辞書は参照渡しのはず）")
    print("- 複数のワーカープロセスが同時に実行されている場合、メモリ上のDRAFT_METAが共有されない可能性")
    print("- 同じdraft_idで複数回呼び出されている可能性")

if __name__ == "__main__":
    main()

