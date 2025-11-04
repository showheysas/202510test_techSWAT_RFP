# リファクタリング計画書

## 概要
1783行の`main.py`を機能ごとに分割し、保守性の高いモジュール構成にリファクタリングします。

## バックアップ
- `main_original_backup.py` - 元のmain.pyの完全バックアップ

---

## Phase 1: 基盤構築 🔧
**目標**: 設定とモデル、基本ユーティリティを分離

### 1.1 `config.py` 作成
- [ ] 環境変数の読み込み
- [ ] グローバル設定の管理
- [ ] クライアント初期化（OpenAI、Slack）
- [ ] ディレクトリパスの定義

**影響範囲**: なし（新規作成）
**テスト**: 環境変数読み込みテスト

### 1.2 `models.py` 作成
- [ ] `Draft`モデルの移動
- [ ] 型ヒントの確認

**影響範囲**: なし（新規作成）
**テスト**: モデルバリデーションテスト

### 1.3 `utils/storage.py` 作成
- [ ] `save_json()` 関数
- [ ] ファイル読み込みヘルパー

**影響範囲**: なし（新規作成）
**テスト**: JSON保存・読み込みテスト

**完了条件**: 
- 各モジュールが独立して動作
- 元のmain.pyから参照可能（後で統合）

---

## Phase 2: OpenAIサービス 📝
**目標**: 文字起こしと要約機能を分離

### 2.1 `services/__init__.py` 作成
- [ ] 空の__init__.pyを作成

### 2.2 `services/openai_service.py` 作成
- [ ] `transcribe_audio()` - Whisper文字起こし
- [ ] `summarize_to_structured()` - GPT要約
- [ ] config.pyからOpenAIクライアントをインポート

**影響範囲**: なし（新規作成）
**テスト**: 
- 文字起こし機能のテスト
- 要約機能のテスト

**完了条件**: 
- OpenAIサービスが独立して動作
- 元のmain.pyから呼び出し可能

---

## Phase 3: Slackサービス 💬
**目標**: Slack関連機能を分離

### 3.1 `services/slack_service.py` 作成
- [ ] `verify_slack_signature()` - 署名検証
- [ ] `build_minutes_preview_blocks()` - プレビューブロック生成
- [ ] `build_edit_modal()` - 編集モーダル生成
- [ ] `build_tasks_blocks()` - タスクブロック生成
- [ ] `post_slack_draft()` - Slack投稿
- [ ] グローバル変数 `DRAFT_META` の管理（クラス内で管理）

**影響範囲**: なし（新規作成）
**テスト**: 
- ブロック生成のテスト
- 署名検証のテスト

**完了条件**: 
- Slackサービスが独立して動作
- 元のmain.pyから呼び出し可能

---

## Phase 4: PDFサービス 📄
**目標**: PDF生成機能を分離

### 4.1 `services/pdf_service.py` 作成
- [ ] `create_pdf_async()` - 議事録PDF生成
- [ ] `create_design_checklist_pdf()` - 設計チェックリストPDF生成
- [ ] 内部ヘルパー関数（`wrap_cjk`, `meta_row`, `section_bar`, `draw_paragraph`）

**影響範囲**: なし（新規作成）
**テスト**: 
- PDF生成のテスト
- レイアウト確認

**完了条件**: 
- PDFサービスが独立して動作
- 元のmain.pyから呼び出し可能

---

## Phase 5: Gmail/Driveサービス 📧📁
**目標**: GmailとGoogle Drive機能を分離

### 5.1 `services/gmail_service.py` 作成
- [ ] `send_via_gmail()` - Gmail送信
- [ ] config.pyから設定をインポート

**影響範囲**: なし（新規作成）
**テスト**: Gmail送信テスト（テストモード）

### 5.2 `services/drive_service.py` 作成
- [ ] `get_drive_service()` - Driveサービス取得
- [ ] `upload_to_drive()` - ファイルアップロード
- [ ] `get_file_metadata()` - メタデータ取得
- [ ] `download_text_from_drive()` - テキストダウンロード
- [ ] `watch_drive_folder()` - フォルダ監視開始
- [ ] `stop_watch_drive_folder()` - 監視停止
- [ ] `check_and_process_new_files()` - 新規ファイルチェック
- [ ] `process_drive_file_notification()` - 通知処理
- [ ] `is_file_processed()` / `mark_file_as_processed()` - 処理済みマーク
- [ ] グローバル変数 `DRIVE_WATCH_CHANNEL_INFO` の管理（クラス内で管理）

**影響範囲**: なし（新規作成）
**テスト**: 
- Driveアップロードテスト
- ファイル取得テスト

**完了条件**: 
- Gmail/Driveサービスが独立して動作
- 元のmain.pyから呼び出し可能

---

## Phase 6: タスクサービス ✅
**目標**: タスク関連機能を分離

### 6.1 `services/task_service.py` 作成
- [ ] `parse_tasks_from_actions()` - タスクパース
- [ ] `schedule_task_reminders()` - リマインドスケジュール
- [ ] `_parse_due_to_dt()` - 日付パース
- [ ] `_resolve_slack_user_id()` - ユーザーID解決
- [ ] `_load_user_map()` - ユーザーマップ読み込み
- [ ] `_tz()`, `_epoch()` - タイムゾーン/エポック変換

**影響範囲**: なし（新規作成）
**テスト**: 
- タスクパースのテスト
- リマインドスケジュールのテスト

**完了条件**: 
- タスクサービスが独立して動作
- 元のmain.pyから呼び出し可能

---

## Phase 7: パイプライン 🔄
**目標**: 処理パイプラインを分離

### 7.1 `pipelines/__init__.py` 作成
- [ ] 空の__init__.pyを作成

### 7.2 `pipelines/processing.py` 作成
- [ ] `process_pipeline()` - 音声処理パイプライン
- [ ] `process_text_pipeline()` - テキスト処理パイプライン
- [ ] `process_drive_file_task()` - Driveファイル処理タスク
- [ ] 各サービスをインポートして使用

**影響範囲**: なし（新規作成）
**テスト**: 
- パイプライン全体のテスト
- エラーハンドリング確認

**完了条件**: 
- パイプラインが独立して動作
- 元のmain.pyから呼び出し可能

---

## Phase 8: ルート分割 🛣️
**目標**: エンドポイントを機能ごとに分割

### 8.1 `routes/__init__.py` 作成
- [ ] 空の__init__.pyを作成

### 8.2 `routes/upload.py` 作成
- [ ] `/upload` - 音声アップロードエンドポイント
- [ ] `/process-drive-file` - Driveファイル処理エンドポイント
- [ ] `/health` - ヘルスチェックエンドポイント

**影響範囲**: なし（新規作成）
**テスト**: エンドポイントの動作確認

### 8.3 `routes/slack.py` 作成
- [ ] `/slack/actions` - Slackアクション処理エンドポイント
- [ ] Slackアクション処理ロジック全体

**影響範囲**: なし（新規作成）
**テスト**: Slackアクションの動作確認

### 8.4 `routes/webhook.py` 作成
- [ ] `/webhook/drive` (GET/POST) - Drive Webhookエンドポイント
- [ ] Webhook処理ロジック

**影響範囲**: なし（新規作成）
**テスト**: Webhookの動作確認

**完了条件**: 
- 各ルートが独立して動作
- 元のmain.pyから呼び出し可能

---

## Phase 9: 新main.pyの統合 🔗
**目標**: すべてのモジュールを統合し、元のmain.pyを置き換え

### 9.1 新 `main.py` 作成
- [ ] FastAPIアプリの初期化
- [ ] 各ルートのインポートと登録
- [ ] 起動/停止イベントハンドラ（`startup_event`, `shutdown_event`）
- [ ] ポーリングタスク（`polling_task`）
- [ ] グローバル変数の管理（必要最小限）

### 9.2 動作確認
- [ ] 各エンドポイントの動作確認
- [ ] 統合テスト
- [ ] エラーハンドリング確認

### 9.3 クリーンアップ
- [ ] 未使用のインポート削除
- [ ] コメント整理
- [ ] 型ヒント確認

**完了条件**: 
- 新main.pyが完全に動作
- 元のmain.pyと同等の機能
- すべてのテストがパス

---

## 実装の原則

1. **段階的統合**: 各フェーズで作成したモジュールを元のmain.pyから段階的に使用
2. **後方互換性**: 既存の動作を維持
3. **テスト**: 各フェーズで動作確認
4. **型ヒント**: すべての関数に型ヒントを維持
5. **エラーハンドリング**: 既存のエラーハンドリングを維持

---

## 各フェーズの進め方

1. モジュールを作成
2. 元のmain.pyから該当コードを移動
3. インポートと依存関係を整理
4. 動作確認
5. 次のフェーズへ進む

---

## 注意事項

- 各フェーズは独立してテスト可能
- バックアップ（`main_original_backup.py`）は常に参照可能
- 問題が発生した場合は、前のフェーズに戻れる
- グローバル変数は最小限に（サービスクラス内で管理）

