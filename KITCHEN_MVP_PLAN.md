# Smart Kitchen AR Assistant — MVP 開發計畫（主文件）

> **本文件為專案主計畫。** Web demo 工程細節與歷史進度見 [`PROJECT_PLAN.md`](PROJECT_PLAN.md)。

## 產品願景

透過相機辨識料理台食材與狀態，**不使用語音**，純粹以視覺回傳與畫面疊加（輔助線、提示框、工作區）引導使用者完成食譜步驟。

最終形態：固定廚房檯面 + 俯拍相機 + 投影機，即時在食材旁顯示引導；開發過程分兩階段驗證，降低硬體成本。

---

## 專案策略（2026-07 決議）

### 單一 Repo、雙軌並行

不另開新專案。在現有 `廚房1` repo 內：

| 軌道 | 路徑 | 定位 | 狀態 |
|------|------|------|------|
| **A — CV 主線（本文件）** | `src/` | YOLOv8 + OpenCV 即時 AR / 投影 | 🔄 Phase 1 scaffold（Task 1.0–1.5） |
| **B — Web Demo（參考/過渡）** | `main.py` + `static/` | FastAPI + Canvas 投影 demo | ✅ Phase 1–2、4–5 完成；Phase 3 進行中 |
| **C — 食譜匯入** | `recipe-generator/` | 影片/文字 → 結構化 JSON | 🔄 文字 + 影片上傳可用；URL 待做 |

### 視覺技術分工

| 用途 | 技術 | 說明 |
|------|------|------|
| **即時空間 UI**（bbox、切線貼食材、計數、dropzone） | **YOLOv8** 本機 | Phase 1/2 主線；需 bbox，延遲 <100ms |
| **語意完成判斷**（煎好了嗎、醬汁狀態） | **Gemini Vision**（可選） | 低頻、模糊狀態；現有 `services/vision.py` |
| **兜底** | 手動確認 / dropzone 停留 | 信心不足時不自動跳步 |

> Web demo 的 overlay 畫在**固定工作區**；CV 主線的 overlay 畫在**偵測到的食材旁**——體驗差異大，CV 主線是 KITCHEN MVP 核心。

### UI 方向

- **不優先重構**現有三欄 Web UI（`static/index.html`）
- Phase 1 顯示層：**OpenCV `imshow` 或 Streamlit**（即時影像疊加）
- Web UI 降級為：食譜管理、設定、開發除錯（維護模式）
- Phase 2 全螢幕輸出對齊投影機原生解析度（1080p / 720p）

---

## 系統架構

### Phase 1 — 零硬體 AR 預覽

```text
[ 手機 IP Webcam (RTSP/HTTP) ]  或  [ 本地測試影片 ]
              │
              ▼
[ 本地 PC：Python + YOLOv8 + OpenCV ]
              │
              ├── 狀態機 (recipe_manager)
              ├── 遮擋緩衝 (occlusion buffer)
              └── overlay（bbox、切線、dropzone）
              │
              ▼
[ 電腦螢幕 AR 預覽 ]
```

### Phase 2 — 投影實機落地

```text
            [ 正上方：USB 相機 + 投影機 ]
                       │        ▲
      (投影 UI)        │        │ (俯拍)
                       ▼        │
            [ 消光矽膠墊料理台 ]
```

- 相機：Top-down USB WebCam 或樹莓派相機
- 投影機：建議 800–1000 ANSI 流明以上
- 檯面：淺灰/米色消光矽膠墊（提升對比與辨識率）

### Repo 目錄規劃

```text
kitchenDemo/
├── KITCHEN_MVP_PLAN.md       # 本文件（主計畫）
├── PROJECT_PLAN.md           # Web demo 工程進度
├── requirements-cv.txt       # CV 主線依賴
├── src/                      # 【CV 主線 — Phase 1】
│   ├── config.py
│   ├── recipe_manager.py
│   ├── phone_test.py         # Phase 1 主程式
│   ├── stream_reader.py      # RTSP + 斷線重連
│   ├── detector.py           # YOLOv8
│   ├── overlay_renderer.py   # 切線、bbox、buffer
│   └── calibration.py        # Phase 2（尚未）
├── main.py + static/         # Web demo（維護）
├── services/vision.py        # Gemini/heuristic（輔助軌道）
├── recipe-generator/         # 食譜匯入微服務
├── data/
│   ├── recipes/              # 食譜實例（steak.json、cucumber_cv.json…）
│   ├── kitchen_recipe_schema.json
│   └── kitchen_detect_profile.json
├── RECIPE_FORMAT.md          # 【食譜格式單一來源】各 MD 請連結此檔
└── recipe_schema.json        # Web CookingRecipe schema
```

---

## 核心資料結構

狀態機與**完整食譜欄位／枚舉／範例**以共用規格為準，請直接編輯並參考：

→ **[`RECIPE_FORMAT.md`](RECIPE_FORMAT.md)**（Web CookingRecipe + KITCHEN CV、`trigger_condition`、與 Web 橋接）

實例：`data/recipes/cucumber_cv.json`（CV）、`data/recipes/steak.json`（Web）。

機器可讀 Schema：`recipe_schema.json`、`data/kitchen_recipe_schema.json`。

---

## Phase 1：純手機 AR 預覽測試

**目的：** 驗證 YOLOv8 精準度、遮擋緩衝、狀態自動跳轉、切線/提示框直覺性。  
使用者對著電腦螢幕即可做切菜測試，無需投影機。

### 硬體

- **輸入：** 手機 + IP Webcam App（RTSP/HTTP）；開發期可用本地影片檔
- **運算：** 本地 PC，Python + ultralytics (YOLOv8) + OpenCV
- **輸出：** 電腦螢幕（OpenCV 或 Streamlit）

### 任務清單

- [x] **Task 1.0** — 建立 `src/config.py`、`src/recipe_manager.py`（涼拌小黃瓜範例）
- [x] **Task 1.1** — 串流讀取：`VideoCapture` RTSP/HTTP + 斷線重連；支援本地影片
- [x] **Task 1.2** — YOLOv8 核心：載入 `yolov8n.pt`；PoC 可用 banana/apple 代替；輸出 bbox
- [x] **Task 1.3** — 視覺疊加 + 遮擋緩衝：
  - 食材周圍橘/綠提示框
  - 依 bbox 中心繪製 3 條綠色虛線（切線）
  - 未偵測到時保留 UI **1.5 秒（45 幀 @30fps）** 再消失
- [x] **Task 1.4** — 狀態觸發：數量 1 → >3 持續 2 秒 → 自動下一步
- [x] **Task 1.5** — `phone_test.py` 主程式：整合上述模組，可從影片或 RTSP 啟動

### Phase 1 驗收標準

1. 本地影片或 RTSP 串流穩定讀取（斷線可重連）
2. 食材 bbox 即時顯示，手部遮擋時提示不閃爍（buffer 生效）
3. 切線跟隨食材中心移動
4. 數量觸發可自動切換步驟
5. 無投影機、無 Gemini API 亦可完成 demo

### 無相機開發方式

1. 用本地影片檔代替 RTSP
2. PoC 階段用 COCO 類別（apple/banana）代替食材
3. 手動鍵盤觸發下一步（debug 用）

### 啟動（本機）

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements-cv.txt
python -m src.phone_test --source path\to\fruit.mp4   # 建議含 banana/apple
# 或 webcam：
python -m src.phone_test --source 0
# 或 IP Webcam RTSP：
python -m src.phone_test --source rtsp://PHONE_IP:8080/h264_ulaw.sdp
```

鍵盤：`N` / `Space` 手動下一步；`Q` / `ESC` 結束。

---

## Phase 2：投影機 + 相機實機落地

**目的：** 將 Phase 1 驗證的視覺與邏輯落地；解決環境光、相機–投影視野錯位。

### 任務清單

- [ ] **Task 2.1** — 投影映射校正（`src/calibration.py`）：
  - 投影機投出 4 角紅點
  - 相機畫面點選 4 點
  - `cv2.getPerspectiveTransform` + `warpPerspective` 計算 homography
  - （可參考 Web demo `static/calibration.js` 流程，改為 OpenCV 實作）
- [ ] **Task 2.2** — 全螢幕輸出：無邊框視窗，解析度與投影機原生對齊，避免拉伸
- [ ] **Task 2.3** — Virtual Dropzone：
  - 投影邊角固定綠色確認框
  - YOLO 偵測手或食材進入且停留 ≥2 秒 → 判定步驟完成
- [ ] **Task 2.4** — 整合 Phase 1 管線至投影輸出（相機座標 → 投影座標）

### Phase 2 驗收標準

1. 四點校正後，切線/dropzone 在檯面上對齊誤差可接受
2. 全螢幕投影無拉伸
3. dropzone 互動可推進食譜
4. 環境光變化下 YOLO + buffer 仍可用（或記錄失敗條件）

---

## 既有 Web Demo 資產（軌道 B）

以下已完成，供 Phase 2 參考或輔助，**非 KITCHEN MVP 主線**：

| 項目 | 狀態 | 路徑 |
|------|------|------|
| FastAPI 後端 | ✅ | `main.py` |
| 結構化食譜 + API | ✅ | `data/recipes/`, `/api/recipes` |
| Step Engine | ✅ | `static/step-engine.js` |
| 計時器 | ✅ | Phase 4 |
| Canvas overlay（固定 zone） | 🔄 | `static/overlay.js` |
| 瀏覽器四點校正 | 🔄 | `static/calibration.js` |
| Gemini Vision API | ✅ | `services/vision.py` |
| 語音互動 | 📋 暫緩 | 原 Phase 6，KITCHEN 明確排除 |

Web MVP 驗收（牛排 demo）見 `PROJECT_PLAN.md` MVP Demo Acceptance。

---

## 子專案：recipe-generator

- **路徑：** `recipe-generator/`（port 8100）
- **用途：** 食譜影片 / URL / 文字 → CookingRecipe JSON
- **消費者：** CV 主線、Web demo、未來手機 App
- **詳細：** `recipe-generator/ARCHITECTURE.md`

---

## 開發優先級（給 Cursor Agent）

1. 建立 `src/config.py`、`src/recipe_manager.py`
2. 實作 `phone_test.py`（**先支援本地影片**，再加 RTSP）
3. 完成 Task 1.2–1.4（YOLO + buffer + 觸發）
4. Phase 1 驗收通過後，才開發 `src/calibration.py`（Phase 2）
5. Web UI 重構、語音、Gemini 擴充 — **排在 Phase 1 之後**

---

## 依賴套件（CV 主線新增）

```
ultralytics          # YOLOv8
opencv-python-headless
numpy
# 可選：streamlit
```

既有 `requirements.txt` 保留 Web demo 依賴；CV 依賴可另列 `requirements-cv.txt` 或合併。

---

## Git 同步

1. 開工前 `git pull origin main`
2. 完成任務後更新本文件任務 checkbox
3. `PROJECT_PLAN.md` 僅更新 Web 軌道狀態
4. commit → push → 另一台機器 pull 後繼續

---

## 相關文件

- [`RECIPE_FORMAT.md`](RECIPE_FORMAT.md) — **食譜格式規格（共用，請在此改格式）**
- [`PROJECT_PLAN.md`](PROJECT_PLAN.md) — Web demo 工程 Phase 與完成狀態
- [`recipe-generator/ARCHITECTURE.md`](recipe-generator/ARCHITECTURE.md) — 食譜匯入服務
- [`RECIPES.md`](RECIPES.md) — 食譜範例說明
- [`README.md`](README.md) — 快速啟動（Web demo）
