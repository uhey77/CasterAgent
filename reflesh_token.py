from google_auth_oauthlib.flow import InstalledAppFlow

SCOPES = ["https://www.googleapis.com/auth/youtube.upload"]

flow = InstalledAppFlow.from_client_secrets_file(
    "credentials/youtube_client_secret.json",  # デスクトップアプリ用 JSON
    scopes=SCOPES,
)

# ブラウザを自動で開きたくない場合は open_browser=False にする
creds = flow.run_local_server(
    port=0,                 # 任意の空きポート（例: 8080でも可）
    access_type="offline",
    prompt="consent",
    open_browser=True       # False にすると URL がターミナルに表示される
)

print("Refresh Token:", creds.refresh_token)
print("Access Token:", creds.token)
