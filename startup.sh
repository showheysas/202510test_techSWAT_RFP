#!/bin/bash

# Azure App Service用のスタートアップスクリプト
# Python仮想環境をアクティベート（Azure App Serviceで自動的に作成される）
source /antenv/bin/activate

# 依存関係のインストール（必要な場合）
# pip install -r requirements.txt

# GunicornでFastAPIアプリを起動
# Azure App Serviceは環境変数PORTを使用するため、自動的にポートを設定
exec gunicorn --bind 0.0.0.0:8000 --workers 1 --timeout 300 --worker-class uvicorn.workers.UvicornWorker app.main:app


