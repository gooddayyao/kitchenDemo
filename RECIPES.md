# 食譜範例（人類可讀 + 機器可讀對照）

> **欄位與枚舉定義見 [`RECIPE_FORMAT.md`](RECIPE_FORMAT.md)。** 本檔只放具體食譜對照，不維護格式規格。

結構化 JSON 位於 `data/recipes/`。Web 步驟常用欄位摘要：
- `zone`：投影區域（`cutting_board` / `stove` / `prep`）
- `guidance_type`：`text` | `cut_lines` | `confirm_prep`
- `timer_seconds`：進入步驟後才開始計時（0 表示不計時）
- `completion`：`timer` | `manual_confirm` | `marker_detect` | `vision_heuristic`
- `guide_lines`：切菜線條提示（orientation, spacing_px, count, label）

---

## 食譜名稱：香煎牛排
> JSON: `data/recipes/steak.json`

### 材料：
- [ ] 厚切牛排 1 塊
- [ ] 鹽 適量
- [ ] 黑胡椒 適量
- [ ] 橄欖油 適量
- [ ] 大蒜 2 瓣 (拍扁)
- [ ] 迷迭香 1 支
- [ ] 無鹽奶油 20 克

### 步驟：

| 步驟 | 說明 | zone | guidance | timer | completion |
|------|------|------|----------|-------|------------|
| 1 | 靜置室溫、擦乾、調味 | prep | confirm_prep | — | manual_confirm |
| 2 | 大火煎 2-3 分鐘，翻面淋油 | stove | text | 180s | timer |
| 2.1 | 翻面加蒜、迷迭香、奶油淋油 | stove | — | — | vision_heuristic |
| 2.2 | 側邊煎上色 | stove | — | — | manual_confirm |
| 3 | 靜置 5-10 分鐘 | cutting_board | text | 300s | timer |
| 4 | 切片（約 1.5cm） | cutting_board | cut_lines | — | manual_confirm |

- [ ] **步驟 1：** 將牛排從冰箱取出，靜置室溫 30 分鐘，用廚房紙巾擦乾表面水分，撒上鹽和黑胡椒調味。
- [ ] **步驟 2：** 熱鍋，加入橄欖油，待油熱後放入牛排，大火煎 2-3 分鐘，直到表面金黃酥脆。
  - [ ] 子步驟 2.1：翻面，加入拍扁的大蒜、迷迭香和奶油，用勺子不斷將融化的奶油淋在牛排上，約 2-3 分鐘。
  - [ ] 子步驟 2.2：將牛排側邊也煎至上色。
- [ ] **步驟 3：** 將牛排取出，放在砧板上靜置 5-10 分鐘，讓肉汁回流。
- [ ] **步驟 4：** 切片即可享用。

---

## 食譜名稱：番茄義大利麵
> JSON: `data/recipes/pasta.json`

### 材料：
- [ ] 義大利麵 200 克
- [ ] 熟透番茄 3 顆 (去皮切塊)
- [ ] 洋蔥 半顆 (切丁)
- [ ] 大蒜 2 瓣 (切末)
- [ ] 橄欖油 適量
- [ ] 番茄糊 2 大匙
- [ ] 羅勒葉 少許 (切碎)
- [ ] 鹽 適量
- [ ] 黑胡椒 適量
- [ ] 帕瑪森起司粉 適量

### 步驟：

| 步驟 | 說明 | zone | guidance | timer | completion |
|------|------|------|----------|-------|------------|
| 1 | 番茄切塊、洋蔥切丁、蒜切末 | cutting_board | cut_lines | — | manual_confirm |
| 2 | 煮麵至七分熟 | stove | text | 480s | timer |
| 3 | 炒香洋蔥與蒜末 | stove | text | 120s | vision_heuristic |
| 4 | 煮番茄醬 | stove | text | 300s | timer |
| 5 | 拌炒調味盛盤 | stove | confirm_prep | — | manual_confirm |

- [ ] **步驟 1：** 鍋中燒水，加入少許鹽，水滾後放入義大利麵，按照包裝說明煮至七分熟，撈起備用並保留少許煮麵水。
- [ ] **步驟 2：** 另起一鍋，倒入橄欖油，放入洋蔥丁炒香，再加入大蒜末炒香。
- [ ] **步驟 3：** 加入番茄塊和番茄糊，翻炒均勻，加入少量煮麵水，煮至番茄軟爛成醬。
- [ ] **步驟 4：** 放入煮好的義大利麵，拌炒均勻，加入羅勒葉、鹽和黑胡椒調味。
- [ ] **步驟 5：** 盛盤後撒上帕瑪森起司粉即可。
