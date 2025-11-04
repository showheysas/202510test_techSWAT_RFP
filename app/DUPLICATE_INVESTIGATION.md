# 重複投稿の原因調査結果

## 調査日
2025年11月4日

## 問題
Slackの投稿で同じものが重複して2つ投稿される

## 調査結果

### 1. 実装の比較

#### 元の実装（main_original_backup.py）
```python
def post_slack_draft(channel_id: str, draft_id: str, title: str, d: Draft):
    # グローバル変数 DRAFT_META を直接参照
    if draft_id in DRAFT_META and DRAFT_META[draft_id].get("ts"):
        print(f"[Slack] Draft {draft_id} already posted, skipping duplicate")
        return DRAFT_META[draft_id]
    
    blocks = build_minutes_preview_blocks(draft_id, d)
    try:
        resp = client_slack.chat_postMessage(channel=channel_id, text="議事録 下書き", blocks=blocks)
        DRAFT_META[draft_id] = {"channel": channel_id, "ts": resp["ts"]}  # グローバル変数を更新
        return resp
    except Exception as e:
        print(f"[Slack] Post draft failed for channel {channel_id}: {e}")
        DRAFT_META[draft_id] = {"channel": "", "ts": ""}  # グローバル変数を更新
        raise
```

#### 新しい実装（services/slack_service.py）
```python
def post_slack_draft(channel_id: str, draft_id: str, title: str, d: Draft, draft_meta: dict):
    # パラメータ draft_meta を参照
    if draft_id in draft_meta and draft_meta[draft_id].get("ts"):
        print(f"[Slack] Draft {draft_id} already posted, skipping duplicate")
        return draft_meta[draft_id]
    
    blocks = build_minutes_preview_blocks(draft_id, d)
    try:
        resp = client_slack.chat_postMessage(channel=channel_id, text="議事録 下書き", blocks=blocks)
        draft_meta[draft_id] = {"channel": channel_id, "ts": resp["ts"]}  # パラメータを更新
        return resp
    except Exception as e:
        print(f"[Slack] Post draft failed for channel {channel_id}: {e}")
        draft_meta[draft_id] = {"channel": "", "ts": ""}  # パラメータを更新
        raise
```

### 2. 主な変更点

**Phase 3での変更**:
- `post_slack_draft`関数を`services/slack_service.py`に分離
- グローバル変数`DRAFT_META`の直接参照を、パラメータ`draft_meta`として受け取るように変更
- 呼び出し側で`DRAFT_META`を引数として渡すように変更

### 3. 重複投稿の原因分析

#### 可能性1: パラメータ渡しの問題（低い可能性）
- Pythonでは辞書は参照渡しなので、`DRAFT_META`を渡せば同じオブジェクトを参照するはず
- しかし、何らかの理由で参照が正しく機能していない可能性

#### 可能性2: 複数ワーカープロセスの問題（高い可能性）
- Azure App Serviceでは`gunicorn --workers 2`で2つのワーカープロセスが実行されている
- 各ワーカープロセスは**独立したメモリ空間**を持つ
- ワーカー1とワーカー2が同時に同じリクエストを処理する場合：
  - ワーカー1: `DRAFT_META`に`draft_id`が存在しない → 投稿実行
  - ワーカー2: `DRAFT_META`に`draft_id`が存在しない（別のメモリ） → 投稿実行
  - 結果: 2つの投稿が発生

#### 可能性3: 同じリクエストが2回処理される（可能性あり）
- ネットワークのリトライやロードバランサーの問題で、同じリクエストが2回処理される
- 両方のリクエストがほぼ同時に処理され、重複チェックが間に合わない

### 4. Phase 3の変更が原因か？

**結論: Phase 3の変更自体が直接的な原因ではない可能性が高い**

理由:
1. 重複チェックのロジックは同じ
2. Pythonの辞書は参照渡しなので、`DRAFT_META`をパラメータとして渡しても同じオブジェクトを参照する
3. ただし、**元のコードでも同じ問題が発生していた可能性がある**

**しかし、Phase 3の変更によって問題が顕在化した可能性**:
- 元のコードではグローバル変数を直接参照していたため、モジュールレベルで定義されていた
- 新しいコードではパラメータとして渡すため、何らかの理由で参照が正しく機能していない可能性

### 5. 確認すべき点

1. **ログの確認**
   - `[Slack] Draft {draft_id} already posted, skipping duplicate` というメッセージが出力されているか
   - このメッセージが出ていない場合、重複チェックが機能していない

2. **ワーカープロセスの確認**
   - Azure App Serviceのログで、同じ`draft_id`が複数のワーカーで処理されていないか

3. **タイミングの問題**
   - 2つの投稿がほぼ同時に発生しているか
   - 時間差がある場合、別の問題の可能性

### 6. 推奨される修正案

#### 案1: グローバル変数を直接参照する（元の実装に戻す）
- `services/slack_service.py`でグローバル変数`DRAFT_META`を直接参照する
- ただし、これはモジュール間の依存関係を増やす

#### 案2: ファイルベースの重複チェック
- メモリ上の`DRAFT_META`ではなく、ファイルシステムに投稿済みフラグを保存
- 複数のワーカープロセス間で共有できる

#### 案3: データベースやRedisを使用
- より堅牢な重複チェックの仕組みを導入

### 7. 次のステップ

1. まず、ログを確認して重複チェックが機能しているか確認
2. 問題が継続する場合、案1（グローバル変数直接参照）を試す
3. それでも解決しない場合、案2（ファイルベース）を検討

