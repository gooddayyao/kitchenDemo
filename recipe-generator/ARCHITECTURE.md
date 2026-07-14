# Recipe Generator — 目標架構

## 產品定位

`recipe-generator` 是 **kitchenDemo 生態系中的獨立微服務**，負責把「食譜來源」（影片、URL、文字）轉成 **CookingRecipe JSON**，供以下系統共用：

| 消費者 | 用途 |
|--------|------|
| 手機 App（未來） | 錄影/選影片 → 取得結構化食譜 → 進入 AR 料理 Demo |
| kitchenDemo 主專案 | 匯入外部食譜、取代或補強 `/api/parse-recipe` |
| 其他服務 | 任何需要結構化料理步驟的應用 |

**核心契約：** 輸出必須符合 `schemas/recipe_schema.json`，與主專案 `data/recipes/*.json` 格式一致。  
欄位規格文件：主專案 [`RECIPE_FORMAT.md`](../RECIPE_FORMAT.md)（Web CookingRecipe 一節）。

---

## 系統全景

```text
┌─────────────────────────────────────────────────────────────────┐
│                        手機 App / PWA（未來）                      │
│  ┌──────────────┐    ┌──────────────────────────────────────┐   │
│  │ 食譜匯入      │    │ 料理 Demo（重用 kitchenDemo 前端邏輯）  │   │
│  │ 錄影/相簿/URL │    │ 全螢幕相機 + StepEngine + Vision      │   │
│  └──────┬───────┘    └──────────────────┬───────────────────┘   │
└─────────┼───────────────────────────────┼─────────────────────────┘
          │ HTTP                         │ HTTP
          ▼                              ▼
┌─────────────────────┐        ┌─────────────────────────┐
│  recipe-generator   │        │  kitchenDemo (main)      │
│  :8100              │        │  :8000                   │
│                     │        │                          │
│  POST /v1/parse-*   │        │  GET  /api/recipes       │
│  GET  /health       │        │  POST /api/vision/analyze│
└──────────┬──────────┘        │  投影 / 校正 / 步驟引擎    │
           │                   └─────────────────────────┘
           ▼
┌─────────────────────┐
│  Google Gemini API  │
│  - File API (影片)   │
│  - generateContent  │
└─────────────────────┘
```

---

## 服務邊界

### recipe-generator 負責

- 接收食譜影片（multipart upload）
- 接收 YouTube / 公開影片 URL（可選）
- 接收純文字食譜（開發/測試用）
- 呼叫 Gemini 做內容理解
- 將模型輸出 **正規化** 為 CookingRecipe JSON
- 補齊預設 `zones`、驗證 enum、推斷 `timer_seconds` / `completion`

### recipe-generator 不負責

- 步驟狀態機（`pending` → `active` → `done`）
- 投影校正、空間 overlay
- 相機即時監控、`/api/vision/analyze`
- 食譜持久化儲存（MVP 由客戶端或主專案決定是否存檔）

---

## API 設計（v1）

### `GET /health`

健康檢查與設定狀態。

```json
{
  "status": "ok",
  "service": "recipe-generator",
  "gemini_configured": true,
  "version": "0.1.0"
}
```

### `POST /v1/parse-recipe/text`

**Request**

```json
{ "text": "### 食譜名稱：測試\n#### 材料：\n..." }
```

**Response：** 完整 `CookingRecipe` 物件。

### `POST /v1/parse-recipe/video`

**Request：** `multipart/form-data`

| 欄位 | 類型 | 說明 |
|------|------|------|
| `video` | file | mp4 / mov / webm |
| `title_hint` | string (可選) | 協助模型命名 |
| `language` | string (可選) | 預設 `zh-TW` |

**Response：** 完整 `CookingRecipe` 物件。

**實作路徑（待完成）：**

1. 儲存暫存檔或串流上傳
2. Gemini File API 上傳並等待 `ACTIVE`
3. `generateContent` + 結構化 prompt
4. `_normalize_recipe()` 後回傳

### `POST /v1/parse-recipe/url`

**Request**

```json
{ "url": "https://www.youtube.com/watch?v=..." }
```

**Response：** 完整 `CookingRecipe` 物件。

> 公開 YouTube URL 可由 Gemini 直接分析；私有影片需改走 `/video` 上傳。

---

## 資料流：影片 → 食譜

```text
[手機選影片]
      │
      ▼
POST /v1/parse-recipe/video
      │
      ├─► gemini_files.upload(video_bytes)
      │         │
      │         ▼
      │   file_uri (Gemini File API)
      │
      ├─► gemini_client.generate_with_file(file_uri, RECIPE_PROMPT)
      │         │
      │         ▼
      │   raw JSON (可能不完整)
      │
      └─► recipe_normalizer.normalize(raw)
                │
                ▼
          CookingRecipe JSON
                │
                ▼
      [App 顯示 / 存本地 / POST 到 kitchenDemo]
```

---

## CookingRecipe 輸出規則

與主專案 `recipe_schema.json` 對齊；人類可讀規格見 [`../RECIPE_FORMAT.md`](../RECIPE_FORMAT.md)：

| 欄位 | 規則 |
|------|------|
| `zones` | 缺省時補 `cutting_board` / `stove` / `prep` 預設座標 |
| `steps[].zone` | `cutting_board` \| `stove` \| `prep` |
| `steps[].guidance_type` | `text` \| `cut_lines` \| `confirm_prep` |
| `steps[].completion` | `timer` \| `manual_confirm` \| `marker_detect` \| `vision_heuristic` |
| `steps[].timer_seconds` | 從「N 分鐘/秒」推斷；無則 `0` |
| `steps[].guide_lines` | `guidance_type=cut_lines` 時補切線模板 |

**Prompt 要點（給 Gemini）：**

- 從影片語音 + 畫面辨識材料與步驟順序
- 不確定時長 → `completion=manual_confirm`，不要亂填 timer
- 炒菜/煎鍋動作 → 考慮 `vision_heuristic`
- 只回 JSON，不要 markdown

---

## 與 kitchenDemo 主專案的整合方式

### 階段 1（目前骨架）

- 子專案獨立運行於 `:8100`
- 主專案維持現有 `/api/parse-recipe`（文字解析）
- 手動用 curl / Postman 測試子服務

### 階段 2（Proxy 整合）

主專案 `main.py` 新增可選 proxy：

```text
POST /api/parse-recipe/video  →  轉發  recipe-generator:8100/v1/parse-recipe/video
```

環境變數：`RECIPE_GENERATOR_URL=http://127.0.0.1:8100`

### 階段 3（手機 Demo）

手機 App 直接呼叫 `recipe-generator` 取得 JSON，再：

1. 本地顯示材料與步驟預覽
2. 呼叫 `engine.loadRecipe(recipe)` 進入全螢幕 AR 模式
3. Vision 仍打主專案 `/api/vision/analyze`（或日後再拆 vision 服務）

---

## 手機 AR Demo 模式（目標，非本子專案實作）

本子專案只產出 JSON；手機 Demo 由未來 `kitchen-demo-mobile` 或主專案 mobile 模式負責：

```text
[全螢幕後鏡頭 video]
        +
[Canvas overlay：zones / 切線 / 計時]
        +
[StepEngine + VisionMonitor → kitchenDemo API]
```

| Demo 層級 | 功能 |
|-----------|------|
| L1 最小 | 步驟卡 + 計時 + 手動確認 |
| L2 核心 | + Vision 送 frame、低信心提示 |
| L3 完整 | + 四點校正、工作區 overlay |

---

## 目錄結構

```text
recipe-generator/
├── ARCHITECTURE.md      # 本文件
├── README.md
├── .env.example
├── requirements.txt
├── main.py              # FastAPI 入口
├── start.bat
├── schemas/
│   └── recipe_schema.json
├── services/
│   ├── gemini_client.py    # REST generateContent（文字/JSON）
│   ├── gemini_files.py     # File API 上傳（影片）
│   ├── recipe_normalizer.py # 輸出正規化
│   ├── text_parser.py      # 文字 → 食譜
│   └── video_parser.py     # 影片/URL → 食譜（待實作）
└── tests/
    └── test_health.py
```

---

## 環境變數

| 變數 | 必填 | 說明 |
|------|------|------|
| `GEMINI_API_KEY` | 是（影片/AI 解析） | Google AI API key |
| `GEMINI_MODEL` | 否 | 預設 `gemini-2.0-flash` |
| `HOST` | 否 | 預設 `127.0.0.1` |
| `PORT` | 否 | 預設 `8100` |
| `MAX_VIDEO_MB` | 否 | 上傳大小上限，預設 `100` |

---

## 實作階段

| 階段 | 內容 | 狀態 |
|------|------|------|
| 0 | 子專案骨架、架構文件、health API | 進行中 |
| 1 | 文字解析（`/v1/parse-recipe/text`） | 骨架已接線 |
| 2 | 影片上傳 + Gemini File API | 待實作 |
| 3 | YouTube URL 解析 | 待實作 |
| 4 | Schema 驗證、錯誤碼、timeout 重試 | 待實作 |
| 5 | 主專案 proxy、手機 App 串接 | 待實作 |

---

## 安全與部署注意事項

- **API Key 只放伺服器端**，不可寫入手機 App
- 手機瀏覽器相機需 **HTTPS**；開發可用 ngrok
- 影片暫存應有大小限制與定期清理
- 生產環境建議加 rate limit 與 API key 認證（本子專案 MVP 尚未包含）

---

## 相關文件

- 主專案計畫：`../PROJECT_PLAN.md`
- 食譜範例：`../RECIPES.md`、`../data/recipes/`
- Schema 來源：`schemas/recipe_schema.json`（與主專案同步）
