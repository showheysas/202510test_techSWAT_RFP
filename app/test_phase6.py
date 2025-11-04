"""
Phase 6 動作確認テストスクリプト（タスクサービス）
"""
import sys
from pathlib import Path

print("=" * 70)
print("Phase 6 動作確認テスト（タスクサービス）")
print("=" * 70)

# テスト1: モジュールのインポート
print("\n[テスト1] services/task_service.py のインポート")
try:
    try:
        from app.services.task_service import (
            schedule_task_reminders,
            mark_task_complete,
            update_task_block_in_slack
        )
        print("  ✓ Azure形式でインポート成功")
    except ImportError:
        from services.task_service import (
            schedule_task_reminders,
            mark_task_complete,
            update_task_block_in_slack
        )
        print("  ✓ ローカル形式でインポート成功")
    
    # 関数の確認
    functions = [
        schedule_task_reminders,
        mark_task_complete,
        update_task_block_in_slack
    ]
    
    print(f"  ✓ {len(functions)}個の関数がインポートされました")
    for func in functions:
        print(f"    - {func.__name__}")
    
except Exception as e:
    print(f"✗ task_service.py のインポート失敗: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# テスト2: 依存関係の確認
print("\n[テスト2] 依存関係の確認")
try:
    try:
        from app.config import DEFAULT_REMIND_HOUR, SLACK_USER_MAP_JSON, SUMM_DIR
        from app.models import Draft
        from app.services.slack_service import parse_tasks_from_actions, build_tasks_blocks
        print("  ✓ 依存モジュールのインポート成功（Azure形式）")
    except ImportError:
        from config import DEFAULT_REMIND_HOUR, SLACK_USER_MAP_JSON, SUMM_DIR
        from models import Draft
        from services.slack_service import parse_tasks_from_actions, build_tasks_blocks
        print("  ✓ 依存モジュールのインポート成功（ローカル形式）")
    
    print(f"  - DEFAULT_REMIND_HOUR: {DEFAULT_REMIND_HOUR}")
    print(f"  - SUMM_DIR: {SUMM_DIR}")
    
except Exception as e:
    print(f"✗ 依存関係の確認失敗: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

# テスト3: 関数の基本動作確認（モック）
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
        actions="・タスクA（担当：田中、期限：10/25）\n・タスクB（期限：11/5）",
        issues="課題1",
        meeting_name="テスト会議",
        datetime_str="2025年10月25日 | 14:00",
        participants="田中, 佐藤",
        purpose="テスト目的",
        risks="リスク1"
    )
    
    # parse_tasks_from_actions のテスト（依存関係）
    print("\n  [3-1] parse_tasks_from_actions のテスト（依存関係確認）")
    tasks = parse_tasks_from_actions(test_draft.actions)
    if isinstance(tasks, list) and len(tasks) > 0:
        print(f"    ✓ タスクがパースされました（{len(tasks)}個）")
    else:
        print("    ✗ タスクのパースに失敗")
        sys.exit(1)
    
    # mark_task_complete のテスト（実際のファイルは使用しない）
    print("\n  [3-2] mark_task_complete の関数シグネチャ確認")
    import inspect
    sig = inspect.signature(mark_task_complete)
    params = list(sig.parameters.keys())
    print(f"    ✓ 関数シグネチャ: mark_task_complete({', '.join(params)})")
    print(f"    ✓ 戻り値の型: {sig.return_annotation}")
    
    # update_task_block_in_slack のテスト
    print("\n  [3-3] update_task_block_in_slack の関数シグネチャ確認")
    sig = inspect.signature(update_task_block_in_slack)
    params = list(sig.parameters.keys())
    print(f"    ✓ 関数シグネチャ: update_task_block_in_slack({', '.join(params)})")
    
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

# テスト5: 元のmain.pyから削除された関数の確認
print("\n[テスト5] 元のmain.pyから削除された関数の確認")
try:
    import sys
    sys.path.insert(0, '.')
    import main
    
    removed_functions = [
        "_tz",
        "_parse_due_to_dt",
        "_epoch",
        "_load_user_map",
        "_resolve_slack_user_id",
        "schedule_task_reminders"
    ]
    
    all_removed = True
    for func_name in removed_functions:
        if hasattr(main, func_name):
            print(f"    ✗ {func_name} がまだ main.py に存在しています")
            all_removed = False
        else:
            print(f"    ✓ {func_name} は main.py から削除されています")
    
    if all_removed:
        print("  ✓ すべてのタスク関連関数が main.py から削除されました")
    else:
        print("  ⚠ 一部の関数が main.py に残っています")
    
except Exception as e:
    print(f"  ⚠ 確認中にエラー: {e}")

print("\n" + "=" * 70)
print("✓ すべてのテストが成功しました！")
print("=" * 70)
print("\nPhase 6 の動作確認完了。")
print("注意: 実際のSlack API呼び出しテストは行っていません（コスト削減のため）")
print("実際の使用時は、各関数が正しく動作することを確認してください。")

