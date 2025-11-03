# AI Daily 2 Video

AI Daily 2 Video は、esa の「AI Daily」記事を読み上げ付きの動画に変換し、必要に応じて YouTube へ自動投稿する FastAPI ベースの自動化パイプラインです。記事取得からスクリプト生成、音声合成、字幕生成、背景画像生成、動画合成、Slack 通知までを一括で処理します。

## 主な機能
- esa API から最新記事を取得（任意の記事 ID での指定も可能）
- OpenAI API を使ったスクリプト生成／音声合成／字幕生成／イメージ生成
- MoviePy/Sync Labs/Hedra を使った動画合成
- YouTube Data API による自動アップロード（タイトルは `AI Daily—YYYY-MM-DD` 形式で固定）
- Slack Incoming Webhook による完了／エラー通知（アップロード成功時は動画 URL を添付）

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

- **背景生成やリップシンクを切り替えたい**  
  Sync Labs と Hedra の設定値は `config/` 配下の JSON で上書き可能です。環境変数の説明はコメントと README の該当セクションを参照してください。

---
Happy automating!
