# Azure App Service デプロイ手順（ZIPデプロイ）

## ZIPファイルの作成手順

### Windows PowerShellで実行

```powershell
# プロジェクトディレクトリに移動
cd "C:\Users\shohey sasaki\Documents\202510_techSWAT\20251025_叩き上げRFP\202510test_techSWAT_RFP_clone"

# デプロイに必要なファイルを含むZIPを作成
# 注意: token.jsonは機密情報なので含めない（後で手動で配置）
Compress-Archive `
  -Path app,requirements.txt,Procfile,runtime.txt,startup.sh,client_secret_*.json `
  -DestinationPath deploy.zip `
  -Force

Write-Host "deploy.zip が作成されました"
```

## Azure Portalでのデプロイ手順

1. App Serviceのページに戻る
2. 左メニューから「デプロイ センター」を選択
3. 「ローカルGit」または「外部Git」を選択（既に設定されている場合はスキップ）
4. または、左メニューから「高度なツール」→「移動」を選択
5. 「Kudu」→「デバッグ コンソール」→「CMD」を選択
6. `site/wwwroot` フォルダに移動
7. 「ZIP デプロイ」タブを選択
8. 「フォルダーの参照」で作成した `deploy.zip` を選択
9. 「デプロイ」ボタンをクリック

## または、デプロイ センターを使用する場合

1. App Serviceのページで、左メニュー「デプロイ センター」を選択
2. 「ソース」を選択
3. 「ローカルGit」を選択（まだ設定していない場合）
4. 「承認して続行」
5. Gitリポジトリが作成される
6. ローカルでGitリポジトリを初期化してプッシュするか、ZIPデプロイを使用


