# Recipe Generator

獨立 FastAPI 微服務：將食譜影片、URL 或文字解析為 **CookingRecipe JSON**，供 kitchenDemo 與未來手機 App 使用。

詳細目標架構見 [ARCHITECTURE.md](./ARCHITECTURE.md)。

## 快速開始

```powershell
cd recipe-generator
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
copy .env.example .env
# 編輯 .env，填入 GEMINI_API_KEY
uvicorn main:app --reload --host 127.0.0.1 --port 8100
```

或使用 `start.bat`。

## API

| 方法 | 路徑 | 說明 |
|------|------|------|
| GET | `/health` | 健康檢查 |
| POST | `/v1/parse-recipe/text` | 文字食譜 → JSON |
| POST | `/v1/parse-recipe/video` | 影片上傳 → JSON（待實作） |
| POST | `/v1/parse-recipe/url` | 影片 URL → JSON（待實作） |

互動文件：`http://127.0.0.1:8100/docs`

## 範例

```powershell
# 健康檢查
curl http://127.0.0.1:8100/health

# 文字解析
curl -X POST http://127.0.0.1:8100/v1/parse-recipe/text `
  -H "Content-Type: application/json" `
  -d "{\"text\": \"### 食譜名稱：測試\n#### 材料：\n- [ ] 蛋 1 顆\n#### 步驟：\n- [ ] **步驟 1：** 打蛋 2 分鐘\"}"
```

## 測試

```powershell
# 需先啟動服務
python tests/test_health.py
```

## 與主專案關係

- 輸出格式與 `../recipe_schema.json` 一致
- 主專案 `kitchenDemo` 繼續負責投影、步驟引擎、相機監控
- 本子專案專注「來源 → 結構化食譜」
