"""Collect web images for kitchen classes and optionally auto-label them.

You only specify class names (English id or Chinese). Example:

    python training/collect.py cucumber
    python training/collect.py 小黃瓜 番茄 --max 40
    python training/collect.py cucumber --source web --no-label

Default source is both: Wikimedia Commons categories + CC image search.
`--source web` needs: pip install ddgs.
"""

from __future__ import annotations

import argparse
import io
import json
import random
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parent
YAML = ROOT / "kitchen.yaml"
IMG_TRAIN = ROOT / "dataset" / "images" / "train"
LBL_TRAIN = ROOT / "dataset" / "labels" / "train"

USER_AGENT = "KitchenAR-collect/1.0 (local dataset bootstrap; Wikimedia-friendly)"
MIN_SIDE = 320
MAX_BYTES = 8 * 1024 * 1024

ZH_ALIASES = {
    "小黃瓜": "cucumber",
    "黄瓜": "cucumber",
    "番茄": "tomato",
    "洋蔥": "onion",
    "洋葱": "onion",
    "大蒜": "garlic",
    "胡蘿蔔": "carrot",
    "胡萝卜": "carrot",
    "馬鈴薯": "potato",
    "土豆": "potato",
    "蛋": "egg",
    "雞肉": "chicken",
    "鸡肉": "chicken",
    "牛肉": "beef",
    "碗": "bowl",
    "刀子": "knife",
    "刀": "knife",
    "青椒": "pepper",
    "彩椒": "pepper",
}

ZH_LABEL = {
    "cucumber": "小黃瓜",
    "tomato": "番茄",
    "onion": "洋蔥",
    "garlic": "大蒜",
    "carrot": "胡蘿蔔",
    "potato": "馬鈴薯",
    "egg": "蛋",
    "chicken": "雞肉",
    "beef": "牛肉",
    "bowl": "碗",
    "knife": "刀子",
    "pepper": "青椒",
}

# Extra English prompts that YOLO-World understands better than our short ids.
WORLD_PROMPT = {
    "pepper": "bell pepper",
    "chicken": "raw chicken",
    "beef": "raw beef",
    "egg": "egg",
}

# Commons phrase-search matches PDFs/books; use categories + short names instead.
COMMONS_CATEGORIES = {
    "cucumber": ["Category:Cucumbers", "Category:Cucumis sativus"],
    "tomato": ["Category:Tomatoes", "Category:Cherry tomatoes"],
    "onion": ["Category:Onions", "Category:Allium cepa"],
    "garlic": ["Category:Garlic", "Category:Allium sativum"],
    "carrot": ["Category:Carrots"],
    "potato": ["Category:Potatoes"],
    "egg": ["Category:Chicken eggs", "Category:Eggs as food"],
    "chicken": ["Category:Raw chicken", "Category:Chicken meat"],
    "beef": ["Category:Beef", "Category:Cuts of beef"],
    "bowl": ["Category:Bowls", "Category:Mixing bowls"],
    "knife": ["Category:Kitchen knives"],
    "pepper": ["Category:Bell peppers", "Category:Capsicum annuum"],
}

COMMONS_TERMS = {
    "cucumber": ["Cucumber", "Cucumis sativus"],
    "tomato": ["Tomato"],
    "onion": ["Onion", "Allium cepa"],
    "garlic": ["Garlic", "Allium sativum"],
    "carrot": ["Carrot"],
    "potato": ["Potato"],
    "egg": ["Chicken egg"],
    "chicken": ["Raw chicken"],
    "beef": ["Raw beef"],
    "bowl": ["Mixing bowl"],
    "knife": ["Kitchen knife"],
    "pepper": ["Bell pepper"],
}


def load_class_names() -> dict[int, str]:
    names: dict[int, str] = {}
    in_names = False
    for raw in YAML.read_text(encoding="utf-8").splitlines():
        line = raw.rstrip()
        if line.strip() == "names:":
            in_names = True
            continue
        if not in_names:
            continue
        if not line or line.lstrip().startswith("#"):
            continue
        if not line.startswith((" ", "\t")):
            break
        key, _, value = line.partition(":")
        names[int(key.strip())] = value.strip()
    return names


def resolve_class(token: str, id_to_name: dict[int, str]) -> str:
    key = token.strip()
    name_set = set(id_to_name.values())
    if key in name_set:
        return key
    if key in ZH_ALIASES:
        return ZH_ALIASES[key]
    lower = key.lower().replace(" ", "_")
    if lower in name_set:
        return lower
    allowed = ", ".join(id_to_name[i] for i in sorted(id_to_name))
    raise SystemExit(f"[錯誤] 未知類別「{token}」。可用：{allowed} 或中文（小黃瓜、番茄…）")


def web_queries_for(cls: str) -> list[str]:
    zh = ZH_LABEL.get(cls, cls)
    return [
        f"{cls} on cutting board top view",
        f"{cls} chopped cutting board overhead",
        f"{zh} 砧板",
        f"{cls} kitchen counter aerial photo",
    ]


def load_kitchen_names() -> tuple[dict[int, str], dict[str, int]]:
    id_to_name = load_class_names()
    name_to_id = {n: i for i, n in id_to_name.items()}
    return id_to_name, name_to_id


def next_index(prefix: str) -> int:
    IMG_TRAIN.mkdir(parents=True, exist_ok=True)
    n = 0
    for p in IMG_TRAIN.iterdir():
        if p.stem.startswith(prefix) and p.suffix.lower() in {".jpg", ".jpeg", ".png", ".webp"}:
            tail = p.stem[len(prefix) :]
            if tail.isdigit():
                n = max(n, int(tail))
    return n + 1


def http_get(url: str, timeout: float = 20.0) -> bytes:
    req = urllib.request.Request(url, headers={"User-Agent": USER_AGENT})
    with urllib.request.urlopen(req, timeout=timeout) as resp:
        length = resp.headers.get("Content-Length")
        if length and int(length) > MAX_BYTES:
            raise ValueError("too large")
        data = resp.read(MAX_BYTES + 1)
        if len(data) > MAX_BYTES:
            raise ValueError("too large")
        return data


def save_image(data: bytes, dest: Path) -> bool:
    try:
        from PIL import Image
    except ImportError as exc:
        raise SystemExit(
            "[錯誤] Pillow 無法載入（常見於 venv 混到舊版 Python）。請執行：\n"
            "  .\\.venv\\Scripts\\python.exe -m pip install --force-reinstall Pillow"
        ) from exc

    try:
        img = Image.open(io.BytesIO(data))
        img = img.convert("RGB")
    except Exception:
        return False
    w, h = img.size
    if min(w, h) < MIN_SIDE:
        return False
    dest.parent.mkdir(parents=True, exist_ok=True)
    img.save(dest, format="JPEG", quality=90)
    return True


def _urls_from_commons_pages(payload: dict) -> list[str]:
    pages = (payload.get("query") or {}).get("pages") or {}
    skip_mime = {"image/svg+xml", "image/gif", "application/pdf"}
    urls: list[str] = []
    for page in pages.values():
        infos = page.get("imageinfo") or []
        if not infos:
            continue
        info = infos[0]
        mime = str(info.get("mime") or "")
        if mime in skip_mime:
            continue
        if not mime.startswith("image/"):
            continue
        urls.append(str(info.get("thumburl") or info.get("url") or ""))
    return [u for u in urls if u]


def search_commons(term: str, limit: int) -> list[str]:
    params = {
        "action": "query",
        "format": "json",
        "generator": "search",
        "gsrsearch": f"filemime:image/jpeg {term}",
        "gsrnamespace": "6",
        "gsrlimit": str(min(max(limit, 1), 50)),
        "prop": "imageinfo",
        "iiprop": "url|mime|size",
        "iiurlwidth": "1280",
    }
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    payload = json.loads(http_get(url).decode("utf-8"))
    return _urls_from_commons_pages(payload)


def search_commons_category(title: str, limit: int) -> list[str]:
    params = {
        "action": "query",
        "format": "json",
        "generator": "categorymembers",
        "gcmtitle": title,
        "gcmtype": "file",
        "gcmlimit": str(min(max(limit, 1), 50)),
        "prop": "imageinfo",
        "iiprop": "url|mime|size",
        "iiurlwidth": "1280",
    }
    url = "https://commons.wikimedia.org/w/api.php?" + urllib.parse.urlencode(params)
    payload = json.loads(http_get(url).decode("utf-8"))
    return _urls_from_commons_pages(payload)


def search_web(query: str, limit: int) -> list[str]:
    try:
        from ddgs import DDGS
    except ImportError:
        raise SystemExit(
            "[錯誤] --source web 需要套件 ddgs。請執行：pip install ddgs"
        ) from None
    urls: list[str] = []
    with DDGS() as ddgs:
        results = ddgs.images(
            query,
            region="wt-wt",
            safesearch="moderate",
            max_results=limit,
            type_image="photo",
            license_image="any",
        )
        for item in results or []:
            url = item.get("image") or item.get("url")
            if url:
                urls.append(str(url))
    return urls


def _add_urls(seen: set[str], out: list[str], urls: list[str]) -> None:
    for url in urls:
        if url and url not in seen:
            seen.add(url)
            out.append(url)


def collect_urls(cls: str, source: str, per_query: int) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []

    if source in ("commons", "both"):
        for cat in COMMONS_CATEGORIES.get(cls, []):
            try:
                _add_urls(seen, out, search_commons_category(cat, per_query))
            except Exception as exc:
                print(f"[警告] Commons 類別失敗 {cat}: {exc}")
            time.sleep(0.3)
        for term in COMMONS_TERMS.get(cls, [cls]):
            try:
                _add_urls(seen, out, search_commons(term, per_query))
            except Exception as exc:
                print(f"[警告] Commons 搜尋失敗「{term}」: {exc}")
            time.sleep(0.3)

    if source in ("web", "both"):
        try:
            from ddgs import DDGS  # noqa: F401
        except ImportError:
            msg = "[警告] 未安裝 ddgs，略過 web 搜尋。請執行：pip install ddgs"
            if source == "web":
                raise SystemExit("[錯誤] --source web 需要套件 ddgs。請執行：pip install ddgs") from None
            print(msg)
        else:
            for q in web_queries_for(cls):
                try:
                    _add_urls(seen, out, search_web(q, per_query))
                except Exception as exc:
                    print(f"[警告] web 搜尋失敗「{q}」: {exc}")
                time.sleep(0.4)

    random.Random(cls).shuffle(out)
    return out


def download_class(cls: str, urls: list[str], max_keep: int) -> list[Path]:
    prefix = f"web_{cls}_"
    idx = next_index(prefix)
    saved: list[Path] = []
    for url in urls:
        if len(saved) >= max_keep:
            break
        dest = IMG_TRAIN / f"{prefix}{idx:04d}.jpg"
        try:
            data = http_get(url)
            if not save_image(data, dest):
                continue
        except (urllib.error.URLError, TimeoutError, ValueError, OSError):
            continue
        saved.append(dest)
        idx += 1
        time.sleep(0.15)
        print(f"  + {dest.name}")
    return saved


def auto_label(paths: list[Path], class_ids: dict[str, int], conf: float) -> int:
    if not paths:
        return 0
    try:
        from ultralytics import YOLO
    except ImportError as exc:
        print(
            "[錯誤] 無法載入 ultralytics / torch。\n"
            f"  原因：{exc}\n"
            "  請用專案 venv 重裝：\n"
            "  .\\.venv\\Scripts\\python.exe -m pip install --force-reinstall torch torchvision ultralytics"
        )
        return 0

    prompts = []
    prompt_to_id: dict[str, int] = {}
    for name, cid in class_ids.items():
        prompt = WORLD_PROMPT.get(name, name.replace("_", " "))
        prompts.append(prompt)
        prompt_to_id[prompt] = cid

    print("[標註] 載入 YOLO-World（第一次會下載權重）…")
    model = YOLO("yolov8s-worldv2.pt")
    if hasattr(model, "set_classes"):
        model.set_classes(prompts)

    LBL_TRAIN.mkdir(parents=True, exist_ok=True)
    labeled = 0
    results = model.predict(source=[str(p) for p in paths], conf=conf, verbose=False)
    for path, result in zip(paths, results):
        lines: list[str] = []
        boxes = result.boxes
        if boxes is not None:
            names = result.names or {}
            for box in boxes:
                cls_i = int(box.cls.item())
                prompt = str(names.get(cls_i, prompts[cls_i] if cls_i < len(prompts) else ""))
                cid = prompt_to_id.get(prompt)
                if cid is None:
                    continue
                x, y, w, h = [float(v) for v in box.xywhn[0].tolist()]
                lines.append(f"{cid} {x:.6f} {y:.6f} {w:.6f} {h:.6f}")
        txt = LBL_TRAIN / f"{path.stem}.txt"
        if lines:
            txt.write_text("\n".join(lines) + "\n", encoding="utf-8")
            labeled += 1
        else:
            txt.write_text("", encoding="utf-8")
            print(f"  [空框] {path.name}（當成背景圖；可刪或手動補標）")
    return labeled


def parse_args() -> argparse.Namespace:
    p = argparse.ArgumentParser(description="依類別名稱蒐集網圖並自動標註")
    p.add_argument("classes", nargs="+", help="kitchen.yaml 類別名或中文，例如 cucumber 或 小黃瓜")
    p.add_argument("--max", type=int, default=40, help="每類最多留下幾張")
    p.add_argument(
        "--source",
        choices=("commons", "web", "both"),
        default="both",
        help="both=Commons 類別 + CC 搜尋（預設）；commons=維基共享；web=需 pip install ddgs",
    )
    p.add_argument("--no-label", action="store_true", help="只下載，不跑 YOLO-World")
    p.add_argument(
        "--label-only",
        action="store_true",
        help="不下載，只對已有的 web_<class>_*.jpg 自動標框",
    )
    p.add_argument("--conf", type=float, default=0.25, help="自動標註信心門檻")
    p.add_argument("--dry-run", action="store_true", help="只印搜尋詞，不下載")
    return p.parse_args()


def main() -> int:
    args = parse_args()
    if not YAML.exists():
        print(f"[錯誤] 找不到 {YAML}")
        return 1

    id_to_name, name_to_id = load_kitchen_names()
    classes = []
    for token in args.classes:
        name = resolve_class(token, id_to_name)
        if name not in classes:
            classes.append(name)

    if args.dry_run:
        for cls in classes:
            print(f"[{cls}] commons categories:")
            for cat in COMMONS_CATEGORIES.get(cls, []):
                print(f"  {cat}")
            print("  commons terms:", ", ".join(COMMONS_TERMS.get(cls, [cls])))
            print("  web queries:")
            for q in web_queries_for(cls):
                print(f"    {q}")
        return 0

    print(
        "注意：網圖多半不是你們料理台俯拍，只能當冷啟動。"
        "正式 Demo 仍應補自己拍的砧板照片。授權以各圖來源為準。"
    )

    if args.label_only:
        exts = {".jpg", ".jpeg", ".png", ".webp", ".bmp"}
        all_saved = []
        for cls in classes:
            prefix = f"web_{cls}_"
            found = sorted(
                p
                for p in IMG_TRAIN.iterdir()
                if p.is_file() and p.suffix.lower() in exts and p.stem.startswith(prefix)
            )
            print(f"[{cls}] 既有照片 {len(found)} 張，開始自動標框…")
            all_saved.extend(found)
        if not all_saved:
            print("[錯誤] 找不到已下載的照片。請先不加 --label-only 跑一次蒐集。")
            return 1
        wanted = {name: name_to_id[name] for name in classes}
        n = auto_label(all_saved, wanted, args.conf)
        print(f"\n[完成] 圖 {len(all_saved)} 張，有框 {n} 張。請抽幾張檢查再 python training\\train.py")
        return 0

    per_query = max(8, args.max // 2)
    all_saved: list[Path] = []
    for cls in classes:
        print(f"\n[{cls}] 搜尋 {args.source}，目標 {args.max} 張…")
        urls = collect_urls(cls, args.source, per_query)
        print(f"  候選 URL {len(urls)} 筆")
        if not urls:
            print("  [提示] 0 筆時可改：python training\\collect.py cucumber --source web")
        saved = download_class(cls, urls, args.max)
        print(f"  下載成功 {len(saved)} 張")
        all_saved.extend(saved)

    if not args.no_label:
        wanted = {name: name_to_id[name] for name in classes}
        n = auto_label(all_saved, wanted, args.conf)
        print(f"\n[完成] 圖 {len(all_saved)} 張，有框 {n} 張。請抽幾張用 LabelImg 檢查再 train。")
    else:
        print(f"\n[完成] 已下載 {len(all_saved)} 張，尚未標註。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
