# Azure App Service デプロイ手順

## 前提条件

- Azure CLIがインストールされていること
- Azureにログインしていること
- リソースグループが作成済みであること

## ステップ1: App Service Planの作成

```bash
# リソースグループ名を指定（既存のものを使用）
RESOURCE_GROUP="your-resource-group-name"
PLAN_NAME="techswat-appservice-plan"
LOCATION="japaneast"  # または "japanwest"

# App Service Planを作成（Linux版、Basic B1）
az appservice plan create \
  --name $PLAN_NAME \
  --resource-group $RESOURCE_GROUP \
  --sku B1 \
  --is-linux
```

**価格レベルの選択:**
- `B1` (Basic): 約¥1,500-2,000/月 - 開発・テスト用
- `S1` (Standard): 約¥6,000-7,000/月 - 本番推奨

## ステップ2: App Serviceの作成

```bash
# App Service名（グローバルで一意である必要がある）
APP_NAME="techswat-rfp-app"  # 変更してください

# App Serviceを作成
az webapp create \
  --resource-group $RESOURCE_GROUP \
  --plan $PLAN_NAME \
  --name $APP_NAME \
  --runtime "PYTHON:3.11"
```

## ステップ3: スタートアップコマンドの設定

```bash
# uvicornでFastAPIアプリを起動するコマンドを設定
az webapp config set \
  --resource-group $RESOURCE_GROUP \
  --name $APP_NAME \
  --startup-file "gunicorn --bind 0.0.0.0:8000 --workers 2 --timeout 300 app.main:app"
```

**または、uvicornを使用する場合:**
```bash
az webapp config set \
  --resource-group $RESOURCE_GROUP \
  --name $APP_NAME \
  --startup-file "uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 2"
```

## ステップ4: 環境変数の設定

```bash
# 既存の環境変数を設定（.envファイルから取得）
az webapp config appsettings set \
  --resource-group $RESOURCE_GROUP \
  --name $APP_NAME \
  --settings \
    OPENAI_API_KEY="your_openai_api_key" \
    SLACK_BOT_TOKEN="xoxb-your-token" \
    SLACK_SIGNING_SECRET="your_signing_secret" \
    SLACK_CHANNEL_ID="C1234567890" \
    GMAIL_USER="your_email@gmail.com" \
    GMAIL_PASS="your_app_password" \
    GOOGLE_CREDENTIALS_PATH="client_secret_825853050725-pnarvt7cdvbh6dl402fcee0kdko4voum.apps.googleusercontent.com.json" \
    GOOGLE_DRIVE_FOLDER_ID="your_folder_id"
```

## ステップ5: デプロイ方法の選択

### 方法A: Azure CLIで直接デプロイ（簡単）

```bash
# プロジェクトディレクトリに移動
cd "C:\Users\shohey sasaki\Documents\202510_techSWAT\20251025_叩き上げRFP\202510test_techSWAT_RFP_clone"

# ローカルファイルをデプロイ
az webapp up \
  --resource-group $RESOURCE_GROUP \
  --name $APP_NAME \
  --runtime "PYTHON:3.11"
```

### 方法B: ZIPデプロイ（推奨）

```bash
# 現在のディレクトリをZIPに圧縮（PowerShell）
Compress-Archive -Path * -DestinationPath deploy.zip -Force

# ZIPをデプロイ
az webapp deployment source config-zip \
  --resource-group $RESOURCE_GROUP \
  --name $APP_NAME \
  --src deploy.zip
```

### 方法C: GitHub Actions（継続的デプロイ）

GitHubリポジトリに接続して自動デプロイを設定

## ステップ6: 動作確認

```bash
# App ServiceのURLを確認
az webapp show \
  --resource-group $RESOURCE_GROUP \
  --name $APP_NAME \
  --query defaultHostName \
  --output tsv

# ブラウザで確認
# https://<APP_NAME>.azurewebsites.net/health
```

## ステップ7: ログの確認

```bash
# リアルタイムログの確認
az webapp log tail \
  --resource-group $RESOURCE_GROUP \
  --name $APP_NAME

# または、Azure Portalから「ログストリーム」を確認
```

## 注意事項

1. **ファイルパス**: Azure App Serviceでは `D:\home\site\wwwroot\` がルートディレクトリです
2. **永続ストレージ**: `data/` フォルダは `D:\home\site\wwwroot\data\` に保存されます
3. **環境変数**: 機密情報は環境変数として設定し、コードに直接書き込まないでください
4. **Google認証情報**: `client_secret_*.json` と `token.json` もデプロイに含める必要があります

## トラブルシューティング

### アプリが起動しない場合

```bash
# ログを確認
az webapp log download \
  --resource-group $RESOURCE_GROUP \
  --name $APP_NAME \
  --log-file app-logs.zip
```

### モジュールが見つからないエラー

```bash
# requirements.txtが正しく認識されているか確認
az webapp config show \
  --resource-group $RESOURCE_GROUP \
  --name $APP_NAME \
  --query linuxFxVersion
```


