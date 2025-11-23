# AI Daily 2 Video

AI Daily 2 Video は、esa の「AI Daily」記事を読み上げ付きの動画に変換し、必要に応じて YouTube へ自動投稿する FastAPI ベースの自動化パイプラインです。記事取得からスクリプト生成、音声合成、字幕生成、背景画像生成、動画合成、Slack 通知までを一括で処理します。

## 主な機能
- esa API から最新記事を取得（任意の記事 ID での指定も可能）
- OpenAI API を使ったスクリプト生成／音声合成／字幕生成／イメージ生成
- MoviePy/Sync Labs/Hedra を使った動画合成
- YouTube Data API による自動アップロード（タイトルは `AI Daily—YYYY-MM-DD` 形式で固定）
- 同日内の再実行時は YouTube アップロードを自動スキップ（1日1本運用）
- Slack Incoming Webhook による完了／エラー通知（アップロード成功時は動画 URL を添付、同日再実行時は通知なし）

## ディレクトリ構成

```
src/daily2video/
├── app.py                 # FastAPI エントリーポイント
├── core/                  # 設定読み込み・共通コンポーネント
├── domain/                # エンティティと抽象インターフェース
├── application/           # ユースケース（パイプライン実装）
├── infrastructure/        # 外部サービス実装（OpenAI/Google/esa など）
└── presentation/          # FastAPI ルーターや依存性注入
```

生成物はすべて `data/` 配下に保存されます（`scripts/`、`audio/`、`subtitles/`、`images/`、`videos/`、`metadata/`）。

## 前提条件
- macOS/Linux/WSL 上で Python 3.12 以上が実行できること
- パッケージマネージャーとして [uv](https://github.com/astral-sh/uv) を使用
- OpenAI API キー（GPT-4o、Audio API、Image API を利用できる権限）
- esa API トークン／チーム／カテゴリ情報
- （任意）YouTube アップロード用の Google OAuth クライアント & リフレッシュトークン
- （任意）Slack Incoming Webhook URL
- （任意）Sync Labs API キー、参照動画（リップシンク用）
- （任意）Hedra API キー、キャラクター ID（アバター動画用）

## セットアップ手順

```bash
# 依存パッケージのインストール
uv sync

# 環境変数ファイルのコピー
cp .env.example .env
```

1. `.env` を開き、必要なキーを設定します（下記「環境変数一覧」を参照）。
2. esa、OpenAI、Google などの資格情報ファイル（JSON）が必要な場合は `credentials/` など任意の場所に配置し、パスを `.env` に指定します。
3. Slack 通知を使う場合は、Slack ワークスペースで「Incoming Webhooks」アプリを追加し、通知したいチャンネルを選択して発行された URL を `SLACK_WEBHOOK_URL` に設定します。

> Slack Webhook の取得手順  
> 1. [Slack App Directory](https://slack.com/apps) から「Incoming Webhooks」を追加  
> 2. ワークスペースと通知チャンネルを選択  
> 3. 生成された `https://hooks.slack.com/services/...` を `.env` に貼り付け  
> （必要に応じてワークスペース管理者の承認が求められます）

## 環境変数一覧（抜粋）

| 必須 | 変数名 | 説明 |
|------|--------|------|
| ✅ | `OPENAI_API_KEY` | OpenAI API キー |
| ✅ | `ESA_API_TOKEN` / `ESA_TEAM` / `ESA_CATEGORY` | esa 記事の取得に使用 |
| ✅ | `OUTPUT_ROOT` | 生成物の保存先（既定値: `data`） |
| 任意 | `GOOGLE_CLIENT_ID` / `GOOGLE_CLIENT_SECRET` / `GOOGLE_REFRESH_TOKEN` | YouTube アップロードに必須 |
| 任意 | `SLACK_WEBHOOK_URL` | Slack 通知（未設定の場合はアプリログへフォールバック） |
| 任意 | `SYNC_LABS_*` | Sync Labs リップシンク機能を有効化する場合 |
| 任意 | `HEDRA_*` | Hedra アバター機能を有効化する場合 |

詳細は `.env.example` と `src/daily2video/core/settings.py` を参照してください。

## サーバーの起動

```bash
uv run python main.py
# または
uv run uvicorn daily2video.app:app --reload
```

エンドポイント:
- `GET /health` – 動作確認用
- `POST /pipeline/run` – 動画生成パイプラインの実行（`{"article_id": 123}` で記事指定、未指定なら最新記事）

## 動画生成の流れ
1. esa から記事を取得
2. OpenAI でスクリプト生成
3. Text-to-Speech で音声化し、Whisper で字幕生成
4. 画像生成（または外部サービス）で背景を作成
5. MoviePy/Sync Labs/Hedra で動画を合成
6. `AI Daily—YYYY-MM-DD` のタイトルでメタデータを調整し JSON に保存
7. Google 資格情報があれば YouTube にアップロード
8. Slack Webhook が設定されていれば、完了ステータスと YouTube URL を通知

生成されたファイルは `data/` 配下に保存され、YouTube へアップロードした場合は Slack 通知で共有リンクが送信されます。

## アーキテクチャ概要
- クリーンアーキテクチャを意識し、`domain`（抽象）、`application`（ユースケース）、`infrastructure`（各種 API 実装）が疎結合になるよう分離しています。
- 設定は `AppSettings`（Pydantic BaseSettings）が一元管理し、`.env` と `config/*.json` を読み込みます。
- 実行面では FastAPI からも CLI（`main.py`）からも同じユースケース `GenerateDailyVideo` を呼び出すため、インターフェースの差し替えが容易です。

| レイヤー | 役割 | 主なモジュール |
|----------|------|----------------|
| `domain` | エンティティ (`Article`, `VideoAsset` 等) とインターフェース (`ScriptGenerator` など) を定義 | `src/daily2video/domain` |
| `application` | ビジネスユースケース（パイプライン制御） | `application/use_cases/generate_daily_video.py` |
| `infrastructure` | OpenAI/Google/esa/Hedra/Sync Labs/YouTube/Slack/ffmpeg との接続 | `infrastructure/clients`, `infrastructure/services` |
| `presentation` | FastAPI のエンドポイントと DI | `presentation/api.py`, `presentation/dependencies.py` |

## モジュール別概要
- **core/settings (`src/daily2video/core/settings.py`)**: 環境変数を読み込み、`StoragePaths` で `data/` 配下のサブディレクトリを保証します。`get_settings()` は DI の起点です。
- **domain/models & interfaces**: 記事メタデータ、スクリプト、音声、字幕、動画などパイプライン中間成果物を型安全に扱います。例: `VideoComposer` は `AudioAsset` と `SubtitleAsset` を受け取り `VideoAsset` を返します。
- **application/services/pipeline_service.py**: 実行時に利用するコンクリート実装（OpenAI, Google TTS, Sync Labs, Hedra, MoviePy, Slack, YouTube）を条件付きで組み立て、`GenerateDailyVideo` に注入します。ここで API キーの有無に応じたフォールバック（例: Hedra→MoviePy）が決まります。
- **application/use_cases/generate_daily_video.py**: 取得→生成→合成→通知→アップロードまでを逐次実行し、各ステップで `PipelineLogger` に JSON ログを書き込みます。YouTube の「1日1本」制限もここで管理し、`data/state/last_upload.json` に状態を保存します。
- **infrastructure/services/topic_overlay.py**: esa 記事やスクリプトからトピックリスト画像を自動生成し、ffmpeg で動画にオーバーレイします。最新トピック一覧の文字詰まり防止ロジックもここで管理されます。
- **tests/**: 代表的なユースケースと外部サービスのスタブテストを収録（例: `test_topic_overlay.py` は折り返し・レイアウトを検証）。

## パイプライン詳細
| ステージ | 入力 | 出力 | 主なクラス |
|----------|------|------|-----------|
| 記事取得 | esa API (`EsaRestClient`) | `Article` | `ArticleRepository` 実装 |
| スクリプト生成 | `Article` | `ScriptAsset` | `OpenAIScriptService`（GPT-4o） |
| 音声合成 | `ScriptAsset` | `AudioAsset` | `GoogleTextToSpeechService` |
| 字幕生成 | `ScriptAsset`, `AudioAsset` | `SubtitleAsset` (SRT) | `OpenAISubtitleService`（Whisper API） |
| メタデータ生成 | `Article`, `ScriptAsset` | `VideoMetadata` | `OpenAIScriptService` 再利用 |
| 画像/トピック | `Article`, `ScriptAsset` | 背景 + トピック画像 | 画像生成（外部）+ `topic_overlay` |
| 動画合成 | 音声/字幕/背景 | `VideoAsset` | MoviePy or Sync Labs/Hedra コンポーザー |
| 通知 / 公開 | `VideoAsset`, `VideoMetadata` | Slack 通知, YouTube ID | `SlackNotifier`, `YouTubePublisher` |

## 生成アセットと保存先
- `data/scripts/{id}.txt`: OpenAI が生成した読み上げ用スクリプト
- `data/audio/{id}.wav`: Google TTS 音声
- `data/subtitles/{id}.srt`: 字幕
- `data/images/{id}.png`: サムネイル・背景、`*_topics.png` はトピック一覧
- `data/videos/{date}.mp4`: 合成後動画
- `data/metadata/{date}.json`: YouTube 投稿用メタデータ
- `data/state/last_upload.json`: 当日投稿済みかを記録

## API / 実行方法（詳細）
- **FastAPI**: `uv run uvicorn daily2video.app:app --reload` で起動。`POST /pipeline/run` に `{ "article_id": 201 }` のような JSON を送れば、その記事 ID で動画を生成します。未指定時は esa の最新記事を取得します。
- **CLI 実行**: `uv run python -m daily2video.application.scripts.run_pipeline --article-id 201` のような開発用スクリプトを追加する場合も、`pipeline_service.build_pipeline_use_case()` を再利用すれば統一的に動作します（既定では `main.py` 経由で FastAPI を起動）。
- **ロギング**: `src/daily2video/infrastructure/services/logging_service.py` が JSON 形式で標準出力や `server.log` に記録します。各イベントには `event` フィールドを付与しているため、`jq` での解析が容易です。

## Google Cloud へのデプロイ
`Dockerfile` と FastAPI エンドポイントをそのまま Cloud Run（fully managed）に載せる構成が最もシンプルです。以下は代表的な手順です。

1. **プロジェクト設定と Artifact Registry の作成**
   ```bash
   gcloud config set project YOUR_PROJECT_ID
   gcloud artifacts repositories create ai-daily \
     --repository-format=docker --location=asia-northeast1 \
     --description="AI Daily 2 Video images"
   ```
2. **コンテナのビルドと登録**
   ```bash
   gcloud builds submit --region=asia-northeast1 \
     --tag asia-northeast1-docker.pkg.dev/YOUR_PROJECT_ID/ai-daily/ai-daily2video:latest
   ```
3. **Cloud Run へデプロイ**
   ```bash
   gcloud run deploy ai-daily2video \
     --image asia-northeast1-docker.pkg.dev/YOUR_PROJECT_ID/ai-daily/ai-daily2video:latest \
     --region asia-northeast1 \
     --platform=managed \
     --cpu=2 --memory=4Gi \
     --timeout=900 \
     --port=8080 \
     --set-env-vars="OUTPUT_ROOT=/tmp/data" \
     --no-allow-unauthenticated
   ```
   - `.env` の値は `--set-env-vars` で直接指定するか、[Secret Manager](https://cloud.google.com/secret-manager) に保存して `--update-secrets` で参照してください。
   - ファイル生成先を Cloud Storage に置きたい場合は、`gcsfuse` 付きコンテナで `/tmp/data` の代わりにバケットをマウントします。

### 3時間ごとの自動実行（Cloud Scheduler）
1. Cloud Scheduler 用のサービスアカウント（例: `scheduler-ai-daily@...`）を作成し、`roles/run.invoker` を付与します。
2. 以下のように HTTP ターゲットのジョブを作成します（3時間おき、JST ベース）。
   ```bash
   SERVICE_URL=$(gcloud run services describe ai-daily2video \
     --region=asia-northeast1 --format='value(status.url)')

   gcloud scheduler jobs create http ai-daily-run \
     --schedule="0 */3 * * *" \
     --time-zone="Asia/Tokyo" \
     --http-method=POST \
     --uri="${SERVICE_URL}/pipeline/run" \
     --oidc-service-account-email="scheduler-ai-daily@YOUR_PROJECT_ID.iam.gserviceaccount.com" \
     --oidc-token-audience="${SERVICE_URL}" \
     --headers="Content-Type=application/json" \
     --message-body='{}'
   ```
   `message-body` を `{"article_id": 201}` のようにすれば特定記事を指定できます。`{}` のままなら esa 最新記事が選ばれます。

### デイリー投稿の重複防止
`GenerateDailyVideo._should_upload_video` が `data/state/last_upload.json` を確認し、当日分が既にマークされていれば `already_uploaded_today` でアップロードをスキップします（`src/daily2video/application/use_cases/generate_daily_video.py:169-192`）。アップロード完了時は `_mark_uploaded_today()` が同ファイルを当日の日付で更新します（`src/daily2video/application/use_cases/generate_daily_video.py:224-248`）。Cloud Scheduler を 3 時間毎に動かしても、この仕組みが働くため当日1本を維持できます。
テストで重複投稿を試したい場合は、CLI から以下を実行してください。
```bash
uv run python -m daily2video.application.scripts.run_pipeline --force-upload --article-id 210
```
`--article-id` 未指定なら esa 最新記事を使います。`--force-upload` を付けなければ従来どおり重複チェックが働きます。

## テスト & Lint

```bash
uv run pytest            # 単体テスト
uv run ruff check src    # コードスタイルチェック
```

CI やローカル開発中に外部 API へアクセスしたくない場合は、適宜モックを利用してください。

## よくある質問

- **Slack に通知が来ない**  
  `SLACK_WEBHOOK_URL` が空または無効のときは、ログにのみメッセージを出力します。URL が正しいか、Webhook アプリがチャンネルへ投稿できる権限を持っているか確認してください。

- **YouTube へのアップロードに失敗する**  
  リフレッシュトークンの失効が考えられます。Google Cloud Console 上で OAuth クライアントを再度承認し、新しい `GOOGLE_REFRESH_TOKEN` を `.env` に設定してください。Slack 通知にはエラー内容が含まれます。

- **同じ日に複数回パイプラインを走らせたい**  
 2回目以降の実行では `data/state/last_upload.json` を確認し、当日分が既に投稿済みなら YouTube アップロードと Slack 通知を自動でスキップします。どうしても再投稿したい場合は `uv run python -m daily2video.application.scripts.run_pipeline --force-upload` を利用してください（旧来どおりファイル削除でも可）。

- **背景生成やリップシンクを切り替えたい**  
  Sync Labs と Hedra の設定値は `config/` 配下の JSON で上書き可能です。環境変数の説明はコメントと README の該当セクションを参照してください。
