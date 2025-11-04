# ワーカー数設定変更について

## 変更内容

ワーカー数を2から1に減らしました。

### 変更理由

- 複数のワーカープロセスが独立したメモリ空間を持つため、`DRAFT_META`が共有されない
- 同じファイルが2つのワーカーで同時に処理され、重複投稿が発生していた
- ワーカーを1つにすることで、重複投稿の問題を解決

### 変更ファイル

**`startup.sh`**
- `--workers 2` → `--workers 1` に変更

### Azure App Serviceでの設定確認

Azure Portalで以下の設定も確認してください：

1. **Azure Portal → App Service → 設定 → 一般設定**
   - **Startup Command** が以下のようになっているか確認：
     ```
     gunicorn --bind 0.0.0.0:8000 --workers 1 --timeout 300 --worker-class uvicorn.workers.UvicornWorker app.main:app
     ```

2. **環境変数の確認**
   - `WEBSITES_COMMAND` や `SCM_DO_BUILD_DURING_DEPLOYMENT` などの環境変数で起動コマンドが指定されている場合は、それも変更が必要

### 影響

- **ポーリング処理**: 正常に動作します（非同期タスクとして実行されるため）
- **パフォーマンス**: 若干低下する可能性がありますが、通常の用途では問題ありません
- **重複投稿**: 解決されます

### デプロイ後の確認

デプロイ後、ログで以下を確認してください：

```
[INFO] Booting worker with pid: XXXX
```

ワーカーが1つだけ起動していることを確認してください。

