# Antenna

Antenna 是一個本機執行的 FastAPI Web 服務，用來掃描設定好的 X/Twitter 帳號，從 timeline 中擷取 YouTube 連結，補上影片 metadata 與縮圖，並提供一個瀏覽器介面的 review queue。

此專案適合用來追蹤特定帳號分享過的 YouTube 影片，將新影片集中整理到本機 SQLite 資料庫，再透過 Web UI 進行瀏覽、封存與後續管理。

## 功能

- 掃描 `config.toml` 中設定的 X/Twitter 帳號清單
- 從推文內容擷取 YouTube URL
- 透過 YouTube metadata 補齊影片標題、頻道、影片類型等資訊
- 下載並快取影片縮圖
- 使用 SQLite 儲存影片資料、掃描紀錄與帳號狀態
- 提供 Dashboard、帳號狀態、影片清單與設定檢視頁面
- 支援 `new` / `archived` 影片狀態
- 支援自動排程掃描、手動掃描與強制掃描
- 提供基本 REST API 供其他工具整合

## 技術棧

- Python 3.13+
- FastAPI
- Uvicorn
- SQLite
- Jinja2
- Pydantic / pydantic-settings
- yt-dlp
- tweety-ns
- uv
- pytest
- ruff

## 安裝

先確認已安裝 `uv`，接著在專案根目錄執行：

```powershell
uv sync
```

## 設定

建立本機設定檔：

```powershell
Copy-Item config.toml.example config.toml
Copy-Item .env.example .env
```

主要設定位於 `config.toml`：

- `[lists].follow`：要追蹤的 X/Twitter 帳號清單
- `[scheduler].auto_scan_interval_minutes`：自動掃描檢查間隔
- `[scheduler].minimum_scan_interval_minutes`：同一帳號最短掃描間隔
- `[scheduler].active_account_interval_minutes`：活躍帳號掃描間隔
- `[scheduler].inactive_account_interval_minutes`：非活躍帳號掃描間隔
- `[scheduler].inactive_after_days`：幾天沒有新推文後視為非活躍
- `[scheduler].rate_limit_pause_minutes`：遇到 rate limit 後暫停多久
- `[scheduler].new_account_max_tweets`：新帳號初次掃描最多讀取幾則推文
- `[app].database_url`：SQLite 資料庫位置，預設 `sqlite:///data/antenna.db`
- `[app].thumbnail_dir`：縮圖快取目錄
- `[app].host` / `[app].port`：Web 服務監聽位置

Twitter/X cookies 放在 `.env`：

```env
ANTENNA_TWITTER_COOKIES=""
```

如果要實際掃描 X/Twitter timeline，通常需要填入有效 cookies。

## 啟動

使用專案入口啟動：

```powershell
uv run python -m antenna
```

開發時也可以使用 reload 模式：

```powershell
uv run uvicorn antenna.app:create_app --factory --reload
```

啟動後開啟：

```text
http://127.0.0.1:8000
```

## Web 頁面

- `/`：Dashboard，顯示新影片數、封存影片數、最近掃描與下次掃描時間
- `/accounts`：帳號掃描狀態，可查看每個帳號的最近掃描、最近推文與下次掃描時間
- `/videos?state=new`：新影片 review queue
- `/videos?state=archived`：已封存影片
- `/settings`：目前載入的設定與排程暫停狀態

## API

### Health

```http
GET /api/health
```

回傳服務、資料庫與版本狀態。

### Scans

```http
POST /api/scans
GET /api/scans/latest
GET /api/scans/{scan_id}
```

`POST /api/scans` 可建立掃描任務，request body 範例：

```json
{
  "force": false,
  "limit_accounts": null
}
```

若要只掃描特定帳號：

```json
{
  "force": true,
  "limit_accounts": ["example_user"]
}
```

### Videos

```http
GET /api/videos
GET /api/videos/counts
PATCH /api/videos/{url}/state
PATCH /api/videos/state
```

`GET /api/videos` 支援 query string：

- `state`：`new` 或 `archived`
- `page`：頁碼，預設 `1`
- `per_page`：每頁筆數，預設 `50`，最多 `200`

批次更新影片狀態：

```json
{
  "urls": ["https://www.youtube.com/watch?v=..."],
  "state": "archived"
}
```

## 掃描與排程

Antenna 啟動後會建立背景自動掃描服務。排程器會根據帳號狀態決定是否掃描：

- 從未掃描過的帳號會優先進入掃描流程
- 活躍帳號使用較短的掃描間隔
- 長時間沒有新推文的帳號會改用較長的掃描間隔
- 如果遇到 X/Twitter rate limit，會暫停掃描一段時間
- 手動強制掃描可以略過一般排程限制

## 開發

執行測試：

```powershell
uv run pytest
```

執行 lint：

```powershell
uv run ruff check .
```

格式化：

```powershell
uv run ruff format .
```

## 專案結構

```text
src/antenna/
  app.py                 FastAPI app factory 與 Web UI 掛載
  config.py              TOML / .env 設定載入與驗證
  db.py                  SQLite 存取層
  models.py              domain constants
  schemas.py             API request / response schemas
  routers/               HTTP routes
  services/              掃描、排程、Twitter、YouTube、縮圖與 library 邏輯
  templates/             Jinja2 templates
  static/                CSS 與縮圖靜態檔
tests/                   pytest 測試
config.toml.example      設定範例
.env.example             環境變數範例
```

## 資料位置

預設資料與輸出位置：

- SQLite database：`data/antenna.db`
- 縮圖快取：`src/antenna/static/thumbnails`
- Log 目錄：`log/`

以上路徑都可以透過 `config.toml` 調整。

## 注意事項

- 目前只支援 `sqlite:///` database URL。
- `.env` 可能包含敏感 cookies，不應提交到版本控制。
- `config.toml` 可能包含個人追蹤清單，公開前請確認內容是否適合分享。
- 此服務預設作為本機工具使用，若要公開部署，請自行補上認證、反向代理與存取控制。
