# Release artifacts

放「給 CV 預覽直接載入」的已訓練權重，不要跟訓練過程產物混在一起。

| 檔案 | 說明 |
|------|------|
| `yolov8n-kitchen.pt` | 廚房食材 YOLO 權重（`train.py` 訓完會複製到這裡） |

執行預覽時，`data/kitchen_detect_profile.json` 的 `yolo_model` 指向：

```text
release/yolov8n-kitchen.pt
```

`release/*.pt` 會進 Git，方便 clone 後直接跑預覽。  
`training/weights/` 與其他路徑的 `.pt` 仍忽略，不提交訓練過程產物。
