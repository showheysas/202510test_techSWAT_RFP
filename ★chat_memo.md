app/
├── main.py                     # FastAPIアプリ初期化・エンドポイント（約200行）
├── config.py                   # 環境変数・設定管理（約100行）
├── models.py                   # Pydanticモデル定義（約20行）
├── services/                   # 外部サービス連携モジュール
│   ├── __init__.py
│   ├── openai_service.py      # OpenAI関連（文字起こし、要約）（150行程度）
│   ├── slack_service.py       # Slack関連（投稿、モーダル、ブロック）（400行程度）
│   ├── pdf_service.py         # PDF生成（議事録、チェックリスト）（350行程度）
│   ├── gmail_service.py        # Gmail送信（30行程度）
│   ├── drive_service.py       # Google Drive関連（450行程度）
│   └── task_service.py         # タスク関連（パース、リマインド）（150行程度）
├── routes/
│   ├── __init__.py
│   ├── upload.py              # アップロード関連エンドポイント（100行程度）
│   ├── slack.py               # Slackアクション処理（200行程度）
│   └── webhook.py             # Webhook関連（200行程度）
├── utils/
│   ├── __init__.py
│   └── storage.py             # ファイル保存・読み込み（30行程度）
└── pipelines/
    ├── __init__.py
    └── processing.py          # 処理パイプライン（50行程度）

2. 各モジュールの責任
config.py
環境変数の読み込み
グローバル設定の管理
クライアント初期化（OpenAI、Slack）
models.py
Draftモデル
services/openai_service.py
transcribe_audio() - Whisper文字起こし
summarize_to_structured() - GPT要約
services/slack_service.py
post_slack_draft() - Slack投稿
build_minutes_preview_blocks() - プレビューブロック生成
build_edit_modal() - 編集モーダル生成
build_tasks_blocks() - タスクブロック生成
verify_slack_signature() - 署名検証
services/task_service.py
parse_tasks_from_actions() - タスクパース
schedule_task_reminders() - リマインドスケジュール
_parse_due_to_dt() - 日付パース
_resolve_slack_user_id() - ユーザーID解決
services/pdf_service.py
create_pdf_async() - 議事録PDF生成
create_design_checklist_pdf() - 設計チェックリストPDF生成
services/gmail_service.py
send_via_gmail() - Gmail送信
services/drive_service.py
get_drive_service() - Driveサービス取得
upload_to_drive() - ファイルアップロード
get_file_metadata() - メタデータ取得
download_text_from_drive() - テキストダウンロード
watch_drive_folder() - フォルダ監視開始
stop_watch_drive_folder() - 監視停止
check_and_process_new_files() - 新規ファイルチェック
process_drive_file_notification() - 通知処理
is_file_processed() / mark_file_as_processed() - 処理済みマーク
routes/upload.py
/upload - 音声アップロード
/process-drive-file - Driveファイル処理
routes/slack.py
/slack/actions - Slackアクション処理
routes/webhook.py
/webhook/drive - Drive Webhook
pipelines/processing.py
process_pipeline() - 音声処理パイプライン
process_text_pipeline() - テキスト処理パイプライン
process_drive_file_task() - Driveファイル処理タスク
utils/storage.py
save_json() - JSON保存
ファイル読み込みヘルパー
3. メリット
保守性: 機能ごとに分離され、変更が容易
テスト: 各モジュールを個別にテスト可能
可読性: ファイルが小さく、理解しやすい
再利用性: サービスを他のプロジェクトでも再利用可能
チーム開発: 複数人で並行開発しやすい
4. 実装のポイント
循環参照を避ける（services間の依存を最小化）
設定はconfig.pyに集約
グローバル変数（DRAFT_META、DRIVE_WATCH_CHANNEL_INFO）は専用モジュールで管理
型ヒントを維持
既存の動作を維持
この方針で進めますか？必要なら、具体的なモジュールから実装を開始します。


実施内容
バックアップ作成: main_original_backup.py として現在のmain.pyを保存
計画書作成: REFACTORING_PLAN.md に詳細な計画を記載
計画の概要
9つのフェーズに分割：
Phase 1: 基盤構築（config.py, models.py, utils/storage.py）
Phase 2: OpenAIサービス
Phase 3: Slackサービス
Phase 4: PDFサービス
Phase 5: Gmail/Driveサービス
Phase 6: タスクサービス
Phase 7: パイプライン
Phase 8: ルート分割
Phase 9: 新main.pyの統合
各フェーズは独立してテスト可能で、段階的に進められます。

各フェーズの内容を説明します。
Phase 6: タスクサービス ✅
目的: 議事録から抽出したアクションアイテム（タスク）を管理する機能を集約
含まれる機能：
タスクの解析 (parse_tasks_from_actions)
アクション文字列（例：「・タスクA（担当：田中、期限：10/25）」）を解析
タスク名、担当者、期限を抽出
リマインド機能 (schedule_task_reminders)
タスクの期限前日にリマインド
期限1時間前にリマインド
Slackに自動送信
日付・時刻の変換
期限文字列（「10/25」「2025-10-25 15:00」など）をdatetimeに変換
タイムゾーン処理（JST）
SlackユーザーID解決
名前（「田中(PM)」）からSlackユーザーIDを解決
コード箇所: ```262:437:app/main.py```
Phase 7: パイプライン 🔄
目的: 音声やテキストを処理する一連の流れを定義
含まれる機能：
音声処理パイプライン (process_pipeline)
テキスト処理パイプライン (process_text_pipeline)
（Nottaからの文字起こしテキスト用）
Driveファイル処理タスク (process_drive_file_task)
役割: 各サービス（OpenAI、Slack、PDFなど）を順番に呼び出し、処理を実行
コード箇所: ```1545:1564:app/main.py```, ```1490:1543:app/main.py```
Phase 8: ルート分割 🛣️
目的: FastAPIのエンドポイント（URL）を機能ごとに分割
現在のエンドポイント：
/upload (POST)
音声ファイルのアップロード
→ routes/upload.py に移動
/process-drive-file (POST)
Google Driveファイルの処理
→ routes/upload.py に移動
/health (GET)
ヘルスチェック
→ routes/upload.py に移動
/slack/actions (POST)
Slackボタンクリック、モーダル送信などの処理
→ routes/slack.py に移動
/webhook/drive (GET/POST)
Google Driveからの通知を受け取る
→ routes/webhook.py に移動
コード箇所: ```1272:1783:app/main.py```
まとめ
フェーズ	意味	役割
Phase 6: タスクサービス	タスク管理機能	アクションアイテムの解析、リマインド、日付処理
Phase 7: パイプライン	処理の流れ	音声→要約→投稿までの一連の処理を定義
Phase 8: ルート分割	APIエンドポイントの整理	エンドポイントを機能ごとにファイル分割


