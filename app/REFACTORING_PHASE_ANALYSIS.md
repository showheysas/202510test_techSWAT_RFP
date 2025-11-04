# 「アクションアイテム＆タスク」の「実行」ボタン - リファクタリング計画での位置づけ

## リファクタリング計画における該当Phase

### Phase 6: サービス層 - タスクサービス（task_service.py）

**該当する理由:**
- タスク完了処理（`task_complete`）はタスク管理の機能
- `parse_tasks_from_actions()` は既にPhase 3で分離済みだが、タスクの状態管理や完了処理は未分離
- タスク関連のビジネスロジックは独立したサービスとして分離すべき

### 現在の実装状況

#### Phase 3で既に分離済み（`services/slack_service.py`）
- `build_tasks_blocks()` - タスクブロックの生成
- `parse_tasks_from_actions()` - アクション文字列からタスク配列へのパース

#### まだ分離されていない（`main.py`に残っている）
- `task_complete` の処理ロジック（約1321-1369行目）
- タスク完了状態の更新処理
- タスク完了時のメッセージ更新処理

#### Phase 8で分離予定（`routes/slack.py`）
- `slack_actions()` エンドポイント全体
- ただし、`task_complete` の処理ロジックはPhase 6で分離すべき

## Phase 6で実装すべき内容

### `services/task_service.py` に実装すべき機能

1. **タスク完了処理**
   ```python
   def mark_task_complete(draft_id: str, task_index: int, draft_meta: dict) -> dict:
       """
       タスクを完了状態にマークする
       - Draftデータを読み込む
       - タスクを完了状態に更新
       - 更新されたブロックを返す
       """
   ```

2. **タスクブロックの更新**
   ```python
   def update_task_block_for_completion(blocks: list, task_index: int) -> list:
       """
       タスクブロックを完了状態に更新
       - チェックボックスを☐から☑に変更
       - 完了ボタンを無効化
       """
   ```

3. **タスク状態の管理**
   - タスク完了状態の永続化（必要に応じて）

## 修正が必要なモジュール（現時点）

### 1. `main.py` の `slack_actions()` エンドポイント
- **場所**: 約1321-1369行目
- **理由**: `task_complete` の処理ロジックが直接実装されている
- **修正内容**: 
  - タスク完了処理を `services/task_service.py` に移動
  - `task_service.mark_task_complete()` を呼び出すように変更

### 2. `services/slack_service.py` の `build_tasks_blocks()` 関数
- **場所**: 約163-218行目
- **理由**: タスク完了状態の表示をサポートする必要がある可能性
- **修正内容**: 
  - 完了済みタスクの表示に対応（必要に応じて）

## 推奨される実装順序

### オプション1: Phase 6を先に実装（推奨）
1. **Phase 6: タスクサービス**を実装
   - `services/task_service.py` を作成
   - `task_complete` の処理ロジックを移動
   - `main.py` から `task_service` を呼び出すように修正

2. **Phase 8: ルート分割**で `slack_actions` エンドポイントを分離
   - その時点で、`task_service` は既に分離済みなので、ルートはシンプルになる

### オプション2: 現在のPhase 3のまま修正
- `services/slack_service.py` にタスク完了処理を追加
- ただし、これはPhase 3のスコープを超えるため、Phase 6として実装する方が適切

## 結論

**「アクションアイテム＆タスク」の「実行」ボタンの修正は、Phase 6（タスクサービス）で実装すべきです。**

現在は Phase 3 まで完了しているため、Phase 6 の実装が必要です。

### 修正が必要な主なモジュール

1. **`main.py`** - `task_complete` 処理の修正（一時的、Phase 6で移動）
2. **`services/task_service.py`** - 新規作成（Phase 6）
3. **`services/slack_service.py`** - 必要に応じて修正（タスク完了状態の表示対応）

