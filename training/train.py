"""Train a kitchen YOLOv8 model from photos + YOLO labels in training/dataset.

Usage (repo root, venv with requirements-cv.txt):

    python training/train.py
    python training/train.py --epochs 80 --imgsz 640
    .\\training\\train.bat

Collect images first (optional):

    python training/collect.py cucumber
    python training/collect.py 小黃瓜 --source web --max 40
"""

from __future__ import annotations

import argparse
import os
import random
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent
DATASET = ROOT / "dataset"
IMG_TRAIN = DATASET / "images" / "train"
IMG_VAL = DATASET / "images" / "val"
LBL_TRAIN = DATASET / "labels" / "train"
LBL_VAL = DATASET / "labels" / "val"
YAML = ROOT / "kitchen.yaml"
IMG_EXTS = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
MIN_SPLIT = 5
VAL_RATIO = 0.2


def _ascii_work_dir() -> Path:
    """Ultralytics strips non-ASCII from yaml paths; keep runtime files in LOCALAPPDATA."""
    base = Path(os.environ.get("LOCALAPPDATA") or (Path.home() / "AppData" / "Local"))
    return base / "kitchen-yolo"


def _is_link_dir(path: Path) -> bool:
    return path.is_symlink() or (hasattr(path, "is_junction") and path.is_junction())


def _ensure_dataset_link(link: Path, target: Path) -> None:
    target = target.resolve()
    if _is_link_dir(link):
        try:
            if link.resolve() == target:
                return
        except OSError:
            pass
        link.unlink()
    elif link.exists():
        return

    link.parent.mkdir(parents=True, exist_ok=True)
    try:
        os.symlink(str(target), str(link), target_is_directory=True)
        return
    except OSError:
        pass
    result = subprocess.run(
        ["cmd", "/c", "mklink", "/J", str(link), str(target)],
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "無法建立資料集連結（需要目錄聯結）。"
            f"\n  {result.stdout}{result.stderr}"
        )


def write_runtime_yaml() -> tuple[Path, Path]:
    """Write kitchen.yaml under an ASCII path so Ultralytics can find images."""
    work = _ascii_work_dir()
    work.mkdir(parents=True, exist_ok=True)
    linked = work / "dataset"
    _ensure_dataset_link(linked, DATASET)

    names_block = YAML.read_text(encoding="utf-8")
    idx = names_block.find("names:")
    if idx < 0:
        raise RuntimeError(f"{YAML} 缺少 names:")
    # Do not resolve() the junction — that would expand back to the Chinese repo path.
    text = (
        f"path: {linked.as_posix()}\n"
        "train: images/train\n"
        "val: images/val\n"
        "\n"
        f"{names_block[idx:].rstrip()}\n"
    )
    out = work / "kitchen.yaml"
    out.write_text(text, encoding="utf-8")
    return out, work


def _list_images(folder: Path) -> list[Path]:
    if not folder.exists():
        return []
    return sorted(p for p in folder.iterdir() if p.is_file() and p.suffix.lower() in IMG_EXTS)


def _label_for(image: Path, label_dir: Path) -> Path:
    return label_dir / f"{image.stem}.txt"


def _move_pair(image: Path, src_lbl: Path, dst_img: Path, dst_lbl: Path) -> None:
    dst_img.mkdir(parents=True, exist_ok=True)
    dst_lbl.mkdir(parents=True, exist_ok=True)
    shutil.move(str(image), str(dst_img / image.name))
    if src_lbl.exists():
        shutil.move(str(src_lbl), str(dst_lbl / src_lbl.name))


def ensure_val_split() -> None:
    """If val is empty, move 20% of train into val (or copy when the set is tiny)."""
    train_imgs = _list_images(IMG_TRAIN)
    val_imgs = _list_images(IMG_VAL)
    if val_imgs:
        return
    if not train_imgs:
        return

    if len(train_imgs) < MIN_SPLIT:
        print(
            f"[提示] 訓練圖只有 {len(train_imgs)} 張，先複製到 val 以便能開訓；"
            "正式訓練請至少每類數十張並分開 train/val。"
        )
        IMG_VAL.mkdir(parents=True, exist_ok=True)
        LBL_VAL.mkdir(parents=True, exist_ok=True)
        for img in train_imgs:
            shutil.copy2(img, IMG_VAL / img.name)
            lbl = _label_for(img, LBL_TRAIN)
            if lbl.exists():
                shutil.copy2(lbl, LBL_VAL / lbl.name)
        return

    rng = random.Random(42)
    n_val = max(1, round(len(train_imgs) * VAL_RATIO))
    chosen = sorted(rng.sample(train_imgs, n_val), key=lambda p: p.name)
    for img in chosen:
        _move_pair(img, _label_for(img, LBL_TRAIN), IMG_VAL, LBL_VAL)
    print(f"[資料] val 為空，已從 train 抽出 {n_val} 張到 val（固定 seed=42）。")


def check_dataset() -> int:
    train_imgs = _list_images(IMG_TRAIN)
    val_imgs = _list_images(IMG_VAL)
    if not train_imgs:
        print(
            "[錯誤] 找不到訓練照片。\n"
            f"  請放到：{IMG_TRAIN}\n"
            f"  標註放到：{LBL_TRAIN}（檔名與照片相同、副檔名 .txt）\n"
            "  格式見 training/README.md"
        )
        return 0

    missing = [p.name for p in train_imgs if not _label_for(p, LBL_TRAIN).exists()]
    if missing:
        preview = ", ".join(missing[:8])
        extra = f" …共 {len(missing)} 張" if len(missing) > 8 else ""
        print(
            f"[警告] {len(missing)} 張訓練圖沒有對應 .txt 標註（{preview}{extra}）。"
            " Ultralytics 會當成背景圖；請確認不是漏標。"
        )

    print(f"[資料] train={len(train_imgs)} 張  val={len(val_imgs)} 張")
    return len(train_imgs)


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="Train kitchen YOLOv8 from training/dataset")
    p.add_argument("--epochs", type=int, default=100)
    p.add_argument("--imgsz", type=int, default=640)
    p.add_argument("--batch", type=int, default=-1, help="-1 = auto")
    p.add_argument("--model", default="yolov8n.pt", help="pretrained weights to fine-tune")
    p.add_argument("--device", default="", help="e.g. 0, cpu, or empty for auto")
    p.add_argument("--no-split", action="store_true", help="do not auto-fill val from train")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not YAML.exists():
        print(f"[錯誤] 找不到 {YAML}")
        return 1

    if not args.no_split:
        ensure_val_split()
    if check_dataset() == 0:
        return 1

    try:
        from ultralytics import YOLO
    except ImportError as exc:
        print(
            "[錯誤] 無法載入 ultralytics / torch。\n"
            f"  原因：{exc}\n"
            "  .\\.venv\\Scripts\\python.exe -m pip install --force-reinstall torch torchvision ultralytics"
        )
        return 1

    try:
        data_yaml, work = write_runtime_yaml()
    except RuntimeError as exc:
        print(f"[錯誤] {exc}")
        return 1

    print(f"[訓練] model={args.model}  data={data_yaml}  epochs={args.epochs}  imgsz={args.imgsz}")
    model = YOLO(args.model)
    kwargs = {
        "data": str(data_yaml),
        "epochs": args.epochs,
        "imgsz": args.imgsz,
        "project": str(work / "runs"),
        "name": "kitchen",
        "exist_ok": True,
    }
    if args.batch != -1:
        kwargs["batch"] = args.batch
    if args.device:
        kwargs["device"] = args.device

    model.train(**kwargs)

    best = work / "runs" / "detect" / "kitchen" / "weights" / "best.pt"
    if not best.exists():
        best = work / "runs" / "kitchen" / "weights" / "best.pt"
    if best.exists():
        dest_dir = ROOT / "weights"
        dest_dir.mkdir(exist_ok=True)
        dest = dest_dir / "yolov8n-kitchen.pt"
        shutil.copy2(best, dest)
        print(
            f"\n[完成] 最佳權重：{best}\n"
            f"       已複製到：{dest}\n\n"
            "接回 CV 預覽：把權重路徑寫進 data/kitchen_detect_profile.json 的 yolo_model，例如：\n"
            '  "yolo_model": "training/weights/yolov8n-kitchen.pt"\n'
            "並把 data/ingredient_catalog.json 裡已訓練類別的 detect 改成 yolo（yolo 欄位與 names 一致）。"
        )
    else:
        print(f"[警告] 訓練結束但找不到 best.pt，請到 {work / 'runs'} 查看輸出。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
