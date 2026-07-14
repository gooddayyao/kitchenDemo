# 食譜格式規格（共用參考）

> **本文件是食譜欄位／枚舉的單一來源。**  
> 其他文件（`KITCHEN_MVP_PLAN.md`、`RECIPES.md`、`recipe-generator/ARCHITECTURE.md` 等）請連結到此，勿各自複製一份格式說明。  
> 若要調整格式，**直接改本檔**，再同步對應的 JSON Schema / 範例 JSON。

| 機器可讀 Schema | 路徑 | 說明 |
|-----------------|------|------|
| Web / recipe-generator | [`recipe_schema.json`](recipe_schema.json) | CookingRecipe（投影 Web demo） |
| KITCHEN CV | [`data/kitchen_recipe_schema.json`](data/kitchen_recipe_schema.json) | CV 主線步驟觸發格式 |
| CV 偵測 PoC 對應 | [`data/kitchen_detect_profile.json`](data/kitchen_detect_profile.json) | YOLO 類別映射、門檻（非食譜本體） |

---

## 1. 狀態機（各軌道共用概念）

`pending` → `active` → `awaiting_confirm` → `done`

- Web：`static/step-engine.js`
- CV：`src/recipe_manager.py`

---

## 2. Web Demo 格式（CookingRecipe）

用於：`data/recipes/*.json`（如 steak / pasta）、`recipe-generator` 輸出、`/api/recipes`。

### 必要頂層欄位

| 欄位 | 型別 | 說明 |
|------|------|------|
| `id` | string | 食譜 id |
| `title` | string | 顯示名稱 |
| `ingredients` | array | 材料列表 |
| `zones` | object | 砧板／爐灶／備料正規化座標（0–1） |
| `steps` | array | 步驟 |

### `zones.*`

| 欄位 | 說明 |
|------|------|
| `label` | 顯示名稱 |
| `x`, `y`, `w`, `h` | 正規化矩形 |

常用 key：`cutting_board` / `stove` / `prep`

### `steps[]`

| 欄位 | 枚舉／型別 | 說明 |
|------|------------|------|
| `step` | integer | 步驟編號（通常從 1） |
| `title` | string | 短標題 |
| `instruction` | string | 完整指引 |
| `zone` | string | 對應 `zones` 的 key |
| `guidance_type` | `text` \| `cut_lines` \| `confirm_prep` | 投影提示類型 |
| `timer_seconds` | integer ≥ 0 | 進入 active 才計時；0=不計時 |
| `completion` | `timer` \| `manual_confirm` \| `marker_detect` \| `vision_heuristic` | 完成規則 |
| `guide_lines` | object \| null | 切線模板（`cut_lines` 時使用） |
| `substeps` | array（可選） | 子步驟，MVP 以顯示為主 |

### 簡例

```json
{
  "id": "steak",
  "title": "香煎牛排",
  "ingredients": [{ "name": "厚切牛排", "quantity": "1 塊", "prep": null }],
  "zones": {
    "cutting_board": { "label": "砧板區", "x": 0.08, "y": 0.18, "w": 0.38, "h": 0.52 }
  },
  "steps": [
    {
      "step": 1,
      "title": "準備",
      "instruction": "…",
      "zone": "prep",
      "guidance_type": "confirm_prep",
      "timer_seconds": 0,
      "completion": "manual_confirm",
      "guide_lines": null
    }
  ]
}
```

實例與人類可讀對照：見 [`RECIPES.md`](RECIPES.md)、[`data/recipes/`](data/recipes/)。

---

## 3. KITCHEN CV 格式（CV 主線優先）

用於：相機 AR 預覽（`src/phone_test.py`），實例如 [`data/recipes/cucumber_cv.json`](data/recipes/cucumber_cv.json)。

### 必要頂層欄位

| 欄位 | 型別 | 說明 |
|------|------|------|
| `recipe_name` | string | 顯示名稱 |
| `steps` | array | 步驟（至少 1） |
| `current_step_index` | integer（可選，預設 0） | 起始步驟 |
| `dropzone` | object（可選） | 暫存／確認區；缺省則用 detect profile 預設 |

### `dropzone`

| 欄位 | 說明 |
|------|------|
| `x`, `y`, `w`, `h` | 正規化（0–1） |
| `label` | 顯示名稱 |

### `steps[]`

| 欄位 | 枚舉／型別 | 說明 |
|------|------------|------|
| `step_id` | integer ≥ 0 | 步驟 id（建議從 0） |
| `instruction` | string | HUD／投影指引 |
| `target_ingredient` | string \| null | 邏輯食材名（再映射到 YOLO） |
| `expected_status` | string（可選） | 語意註記：`sliced` / `placed` / `done`… |
| `trigger_condition` | 見下表 | 自動／手動完成條件 |
| `timer_seconds` | number（可選） | 僅 `timer` 觸發時使用 |
| `guide_lines` | boolean | 是否在目標 bbox 畫切線 |

### `trigger_condition`

| 值 | 行為 | 實作 |
|----|------|------|
| `target_count_increase` | 目標數量 1 → **>3** 且持續約 2 秒 | YOLO 計數（門檻見 detect profile） |
| `enter_dropzone` | 目標 bbox ∩ dropzone，停留 ≥2 秒 | YOLO |
| `timer` | 倒數結束 | 計時器 |
| `manual_confirm` | 使用者確認 | 鍵盤、或確認物件（預設實體滑鼠）進 dropzone |

### 簡例

```json
{
  "recipe_name": "涼拌小黃瓜",
  "current_step_index": 0,
  "steps": [
    {
      "step_id": 0,
      "instruction": "請將小黃瓜放置於砧板中央，並依提示切片",
      "target_ingredient": "cucumber",
      "expected_status": "sliced",
      "trigger_condition": "target_count_increase",
      "guide_lines": true
    },
    {
      "step_id": 1,
      "instruction": "請將切好的小黃瓜推至右上角暫存區，並放上大蒜",
      "target_ingredient": "garlic",
      "expected_status": "placed",
      "trigger_condition": "enter_dropzone",
      "guide_lines": false
    }
  ],
  "dropzone": {
    "x": 0.72,
    "y": 0.08,
    "w": 0.22,
    "h": 0.22,
    "label": "暫存確認區"
  }
}
```

PoC 階段 `target_ingredient` → YOLO 類別映射寫在 [`data/kitchen_detect_profile.json`](data/kitchen_detect_profile.json)（例如 cucumber→banana），**不是**本格式的一部分。

---

## 4. Web ↔ KITCHEN 橋接

CV 透過 `src/recipe_manager.py` 的 adapter 轉換 Web 食譜；**不修改**既有 `recipe_schema.json`。

| Web (CookingRecipe) | KITCHEN CV |
|---------------------|------------|
| `completion: timer` | `trigger_condition: timer` |
| `completion: manual_confirm` | `trigger_condition: manual_confirm` |
| `completion: vision_heuristic` / `marker_detect` | 目前多映射為 `manual_confirm`（語意判斷可選 Gemini） |
| `guidance_type: cut_lines` / `guide_lines` | `guide_lines: true` |
| `zones.prep`（或其他區） | 可填入 `dropzone` |

---

## 5. 修改格式時請同步

1. 改本檔的欄位／枚舉說明  
2. 更新對應 JSON Schema（`recipe_schema.json` 或 `data/kitchen_recipe_schema.json`）  
3. 必要時更新範例（`data/recipes/*.json`）與程式（`recipe_manager` / `step-engine` / parser）  
4. 其他 MD 只保留連結，不另行複製表格
