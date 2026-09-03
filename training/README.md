# 廚房食材 YOLOv8 訓練

放好**照片**和 **YOLO 標註**就能開訓。權重接回 `src/phone_test.py` 即可辨識小黃瓜、番茄等 COCO 沒有的類別。

## 目錄

```text
training/
├── kitchen.yaml          # Ultralytics 資料集設定（類別在這裡）
├── classes.txt           # 給 LabelImg 用，順序必須與 kitchen.yaml 相同
├── train.py / train.bat  # 一鍵訓練
├── dataset/
│   ├── images/train/     # 把照片放這裡
│   ├── images/val/       # 可空；開訓時會自動從 train 抽 20%
│   ├── labels/train/     # 同檔名的 .txt 標註
│   └── labels/val/
└── weights/              # 訓完會複製 yolov8n-kitchen.pt（不進 git）
```

第一期 12 類（`kitchen.yaml` `names`）：

| id | name | 中文 |
|----|------|------|
| 0 | cucumber | 小黃瓜 |
| 1 | tomato | 番茄 |
| 2 | onion | 洋蔥 |
| 3 | garlic | 大蒜 |
| 4 | carrot | 胡蘿蔔 |
| 5 | potato | 馬鈴薯 |
| 6 | egg | 蛋 |
| 7 | chicken | 雞肉 |
| 8 | beef | 牛肉 |
| 9 | bowl | 碗 |
| 10 | knife | 刀子 |
| 11 | pepper | 青椒／彩椒 |

標註開始後**不要改順序**。新類別請接在 `names` 最後，並同步 `classes.txt`。

## 0. 指定類別、讓腳本蒐集網圖

你只要說要訓什麼。腳本會搜圖、下載到 `dataset/images/train/`，再用 YOLO-World 自動標 bbox。

```powershell
.\.venv\Scripts\python.exe training\collect.py cucumber
python training\collect.py 小黃瓜 番茄 --max 40
python training\collect.py cucumber --source web   # 圖較多，需：pip install ddgs
```

或：`training\collect.bat 小黃瓜`

| 參數 | 說明 |
|------|------|
| `--source both` | 預設。Commons 類別圖 + CC 圖片搜尋 |
| `--source commons` | 只走 Wikimedia（短關鍵字／分類，不要用長句） |
| `--source web` | CC 圖片搜尋，料理台圖較多（授權仍以單張為準；需 `pip install ddgs`） |
| `--no-label` | 只下載，自己用 LabelImg 標 |
| `--label-only` | 不下載，只對已有照片自動標框 |
| `--dry-run` | 只印搜尋詞 |

網圖**不能取代**自己拍的砧板俯拍；自動標框也會漏標／誤標，開訓前請抽查。商用請以自有照片為主。

## 1. 拍照

建議每類 **100～300 張**（Demo 可先每類 30～50 張試跑）。盡量用**真實料理台俯拍**：

- 光線：白天窗邊、黃燈、投影開／關
- 角度：正上方為主，略側拍幾張
- 狀態：整條／切片、單顆／多顆、手部遮擋
- 背景：砧板、矽膠墊、金屬盆

支援副檔名：`.jpg` `.jpeg` `.png` `.webp` `.bmp`。

## 2. 標註（YOLO txt）

每張圖對應一個同名 `.txt`，例如：

```text
dataset/images/train/cuc_001.jpg
dataset/labels/train/cuc_001.txt
```

每行一個框，數值皆為 **0～1 相對座標**：

```text
class_id  x_center  y_center  width  height
```

例（小黃瓜 + 刀子）：

```text
0 0.52 0.48 0.31 0.12
10 0.70 0.55 0.40 0.08
```

工具（匯出選 **YOLO** / **YOLOv8**）：

- [LabelImg](https://github.com/HumanSignal/labelImg) — 開啟時載入本目錄的 `classes.txt`
- [Roboflow](https://roboflow.com) — 匯出 YOLOv8，把 `images/`、`labels/` 拷進 `dataset/`
- [CVAT](https://www.cvat.ai) / Label Studio — 同樣匯出 YOLO txt

沒有物件的背景圖可放空的 `.txt`（0 byte），有助減少誤檢。

## 3. 訓練

在 repo 根目錄（已有 `.venv` 並裝過 `requirements-cv.txt`）：

```powershell
.\.venv\Scripts\Activate.ps1
pip install -r requirements-cv.txt
python training\train.py
```

或雙擊 `training\train.bat`。

常用參數：

```powershell
python training\train.py --epochs 80 --imgsz 640
python training\train.py --model yolov8s.pt --device 0
python training\train.py --no-split   # val 已自己分好時
```

- 有 NVIDIA GPU 會自動用 CUDA；沒有則走 CPU（會慢很多）。
- `val/` 為空且 train ≥ 5 張時，腳本會固定 seed 抽 20% 到 val。
- 輸出：`training/runs/detect/kitchen/weights/best.pt`，並複製為 `training/weights/yolov8n-kitchen.pt`。

也可直接用 Ultralytics CLI：

```powershell
yolo detect train data=training/kitchen.yaml model=yolov8n.pt epochs=100 imgsz=640 project=training/runs name=kitchen
```

## 4. 接回 CV 預覽

1. 編輯 `data/kitchen_detect_profile.json`：

```json
"yolo_model": "training/weights/yolov8n-kitchen.pt"
```

2. 把 `data/ingredient_catalog.json` 裡已訓練的項目改成 YOLO，例如：

```json
{"id": "cucumber", "label": "小黃瓜", "detect": "yolo", "yolo": "cucumber", "category": "vegetable"}
{"id": "tomato", "label": "番茄", "detect": "yolo", "yolo": "tomato", "category": "vegetable"}
```

`yolo` 字串必須與 `kitchen.yaml` 的 `names` 完全一致。

3. 啟動預覽：`.\start-webcam.bat`

## Git

照片、標註、`.pt`、`runs/` 已在 `training/.gitignore`（根目錄也忽略 `*.pt`）。只提交 yaml、腳本與 README，不要把資料集推進 GitHub。
