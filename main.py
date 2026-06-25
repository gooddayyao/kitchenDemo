from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from pathlib import Path

app = FastAPI()
static_dir = Path(__file__).parent / "static"
app.mount("/static", StaticFiles(directory=static_dir), name="static")

@app.get("/")
async def root():
    return FileResponse(static_dir / "index.html")

@app.get("/api/health")
async def health():
    return {"status": "ok", "phase": "1"}

@app.post("/api/parse-recipe")
async def parse_recipe():
    # Placeholder response for Phase 1.
    return {
        "title": "咖哩飯",
        "ingredients": [
            "洋蔥 1 顆",
            "馬鈴薯 2 顆",
            "胡蘿蔔 1 根",
            "咖哩塊 4 塊",
            "雞肉 300g"
        ],
        "steps": [
            {"step": 1, "title": "準備食材", "instruction": "切洋蔥、馬鈴薯和胡蘿蔔。", "duration": 5},
            {"step": 2, "title": "炒香食材", "instruction": "加熱鍋子，放入洋蔥炒至透明。", "duration": 4},
            {"step": 3, "title": "加入咖哩", "instruction": "加入咖哩塊和水煮滾，轉小火燉煮。", "duration": 15}
        ]
    }
