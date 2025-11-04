# リマインドタイミングの設定箇所

## 現在の実装状況

### Phase 6実装後

リマインドタイミングは以下の2つのモジュールに記述されています：

#### 1. `config.py` - リマインド時間の設定値

**場所**: `app/config.py` の47行目

```python
DEFAULT_REMIND_HOUR = int(os.getenv("DEFAULT_REMIND_HOUR", "10"))  # 期限日に何時にリマインドするか(ローカル時間)
```

**説明**:
- 環境変数 `DEFAULT_REMIND_HOUR` から読み込み（デフォルト: 10）
- 前日のリマインド時刻に使用される

#### 2. `services/task_service.py` - リマインドタイミングのロジック

**場所**: `app/services/task_service.py` の `schedule_task_reminders()` 関数内（約127-129行目）

```python
# 2回分の候補
dt_prev_day = (due_dt - timedelta(days=1)).replace(hour=DEFAULT_REMIND_HOUR, minute=0)
dt_one_hour = due_dt - timedelta(hours=1)
```

**説明**:
- **前日リマインド**: 期日の前日 `DEFAULT_REMIND_HOUR:00`（デフォルト: 10:00）
- **期日1時間前リマインド**: 期日の1時間前

## リマインドタイミングの詳細

### 現在の設定

1. **前日リマインド**
   - タイミング: 期日の前日 10:00（`DEFAULT_REMIND_HOUR`で設定可能）
   - 設定場所: `config.py` の `DEFAULT_REMIND_HOUR`
   - 実装場所: `services/task_service.py` の128行目

2. **期日1時間前リマインド**
   - タイミング: 期日の1時間前
   - 設定場所: ハードコード（`services/task_service.py` の129行目）

## 変更方法

### 前日リマインドの時刻を変更する場合

環境変数 `DEFAULT_REMIND_HOUR` を変更します（例: 9時にする場合は `9` を設定）

### 期日1時間前のリマインドタイミングを変更する場合

`services/task_service.py` の129行目を変更します：
```python
dt_one_hour = due_dt - timedelta(hours=1)  # 1時間前
# 例: 2時間前にする場合
dt_one_hour = due_dt - timedelta(hours=2)
```

### リマインド回数を変更する場合

`services/task_service.py` の131行目のリストを変更します：
```python
for when_dt in [dt_prev_day, dt_one_hour]:  # 現在は2回
# 例: 前日のみにする場合
for when_dt in [dt_prev_day]:
```

## まとめ

- **リマインドタイミングのロジック**: `services/task_service.py` の `schedule_task_reminders()` 関数
- **リマインド時間の設定値**: `config.py` の `DEFAULT_REMIND_HOUR`
- **Phase 6で実装**: タスクサービスとして分離済み

