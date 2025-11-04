"""
Azure App Service環境でのインポートテスト
プロジェクトルートから実行する想定
"""
import sys
from pathlib import Path

# プロジェクトルートをパスに追加
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

print("=" * 70)
print("Azure App Service環境でのインポートテスト")
print("=" * 70)

try:
    print("\n[1] app.config のインポート")
    from app.config import client_oa, client_slack, SUMM_DIR
    print("  ✓ app.config のインポート成功")
    
    print("\n[2] app.models のインポート")
    from app.models import Draft
    print("  ✓ app.models のインポート成功")
    
    print("\n[3] app.utils.storage のインポート")
    from app.utils.storage import save_json
    print("  ✓ app.utils.storage のインポート成功")
    
    print("\n[4] app.services.openai_service のインポート")
    from app.services.openai_service import transcribe_audio, summarize_to_structured
    print("  ✓ app.services.openai_service のインポート成功")
    
    print("\n[5] app.main のインポート")
    from app.main import app
    print("  ✓ app.main のインポート成功")
    
    print("\n" + "=" * 70)
    print("✓ すべてのインポートが成功しました！")
    print("=" * 70)
    print("\nAzure App Service環境での動作確認完了。")
    
except ImportError as e:
    print(f"\n✗ インポートエラー: {e}")
    import traceback
    traceback.print_exc()
    sys.exit(1)

