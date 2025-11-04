"""
Phase 3 動作確認テストスクリプト（Slackサービス）
"""
import sys
from pathlib import Path

print("=" * 70)
print("Phase 3 動作確認テスト（Slackサービス）")
print("=" * 70)

# テスト1: モジュールのインポート
print("\n[テスト1] services/slack_service.py のインポート")
try:
    try:
        from app.services.slack_service import (
            verify_slack_signature,
            build_minutes_preview_blocks,
            build_edit_modal,
            build_tasks_blocks,
            parse_tasks_from_actions,
            post_slack_draft
        )
        print("  ✓ Azure形式でインポート成功")
    except ImportError:
        from services.slack_service import (
            verify_slack_signature,
            build_minutes_preview_blocks,
            build_edit_modal,
            build_tasks_blocks,
            parse_tasks_from_actions,
            post_slack_draft
        )
        print("  ✓ ローカル形式でインポート成功")
    
    # 関数の確認
    functions = [
        verify_slack_signature,
        build_minutes_preview_blocks,
        build_edit_modal,
        build_tasks_blocks,
        parse_tasks_from_actions,
        post_slack_draft
    ]
    
    print(f"  ✓ {len(functions)}個の関数がインポートされました")
    for func in functions:
        print(f"    - {func.__name__}")
    
except Exception as e:
    print(f"✗ slack_service.py のインポート失敗: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# テスト2: 依存関係の確認
print("\n[テスト2] 依存関係の確認")
try:
    try:
        from app.config import client_slack, SLACK_SIGNING_SECRET
        from app.models import Draft
        print("  ✓ config.client_slack のインポート成功（Azure形式）")
    except ImportError:
        from config import client_slack, SLACK_SIGNING_SECRET
        from models import Draft
        print("  ✓ config.client_slack のインポート成功（ローカル形式）")
    
    print(f"  - client_slack の型: {type(client_slack).__name__}")
    
except Exception as e:
    print(f"✗ 依存関係の確認失敗: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# テスト3: 関数の動作確認（モック）
print("\n[テスト3] 関数の基本動作確認")
print("  ※ 実際のSlack API呼び出しは行いません（コスト削減）")

try:
    try:
        from app.models import Draft
    except ImportError:
        from models import Draft
    
    # テスト用Draftを作成
    test_draft = Draft(
        title="テスト議事録",
        summary="これはテストです",
        decisions="決定事項1",
        actions="・タスクA（担当：田中、期限：10/25）\n・タスクB",
        issues="課題1",
        meeting_name="テスト会議",
        datetime_str="2025年10月25日 | 14:00",
        participants="田中, 佐藤",
        purpose="テスト目的",
        risks="リスク1"
    )
    
    # build_minutes_preview_blocks のテスト
    print("\n  [3-1] build_minutes_preview_blocks のテスト")
    blocks = build_minutes_preview_blocks("test_draft_id", test_draft)
    if isinstance(blocks, list) and len(blocks) > 0:
        print(f"    ✓ ブロックが生成されました（{len(blocks)}個）")
    else:
        print("    ✗ ブロックの生成に失敗")
        sys.exit(1)
    
    # build_edit_modal のテスト
    print("\n  [3-2] build_edit_modal のテスト")
    modal = build_edit_modal("test_draft_id", test_draft)
    if isinstance(modal, dict) and "blocks" in modal:
        print(f"    ✓ モーダルが生成されました（{len(modal.get('blocks', []))}個のブロック）")
    else:
        print("    ✗ モーダルの生成に失敗")
        sys.exit(1)
    
    # parse_tasks_from_actions のテスト
    print("\n  [3-3] parse_tasks_from_actions のテスト")
    tasks = parse_tasks_from_actions(test_draft.actions)
    if isinstance(tasks, list) and len(tasks) > 0:
        print(f"    ✓ タスクがパースされました（{len(tasks)}個）")
        for i, task in enumerate(tasks):
            print(f"      タスク{i+1}: {task.get('title')}, 担当: {task.get('assignee')}, 期限: {task.get('due')}")
    else:
        print("    ✗ タスクのパースに失敗")
        sys.exit(1)
    
    # build_tasks_blocks のテスト
    print("\n  [3-4] build_tasks_blocks のテスト")
    task_blocks = build_tasks_blocks(test_draft, "test_draft_id")
    if isinstance(task_blocks, list) and len(task_blocks) > 0:
        print(f"    ✓ タスクブロックが生成されました（{len(task_blocks)}個）")
    else:
        print("    ✗ タスクブロックの生成に失敗")
        sys.exit(1)
    
except Exception as e:
    print(f"✗ 関数の動作確認失敗: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# テスト4: main.pyからのインポート確認
print("\n[テスト4] main.pyからのインポート確認")
try:
    try:
        from app.main import app
        print("  ✓ app.main からインポート成功（Azure形式）")
    except ImportError:
        import sys
        sys.path.insert(0, '.')
        from main import app
        print("  ✓ main からインポート成功（ローカル形式）")
    
    print(f"  - app の型: {type(app).__name__}")
    
except Exception as e:
    print(f"✗ main.pyからのインポート失敗: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

print("\n" + "=" * 70)
print("✓ すべてのテストが成功しました！")
print("=" * 70)
print("\nPhase 3 の動作確認完了。")
print("注意: 実際のSlack API呼び出しテストは行っていません（コスト削減のため）")
print("実際の使用時は、各関数が正しく動作することを確認してください。")

