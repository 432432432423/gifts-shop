import math
import time
from fastapi import FastAPI, Response
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import HTMLResponse
import requests

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

# Основные настройки (можно менять на лету через /api/admin без перезапуска)
CONFIG = {
    "token": "deee1872-59ff-499b-9021-d7c82e40099f",
    "funpay_link": "https://funpay" + ".com/users/6099636/",
    "ton_rate_rub": 1.25 * 84,  # 105 рублей за 1 TON
    "admin_secret": "noobasik228",  # Пароль для быстрой смены настроек
}

EXCLUDED_KEYWORDS = ["pepe", "durov"]

# Кэш для защиты от частых запросов и ускорения сайта
collections_cache = []
gifts_cache = {}  # ключ -> {"time": timestamp, "data": response_dict}
CACHE_TTL = 30  # Время жизни кэша в секундах


def is_excluded(collection_name: str) -> bool:
  if not collection_name:
    return False
  low = collection_name.lower()
  return any(word in low for word in EXCLUDED_KEYWORDS)


def make_tg_nft_link(collection_name: str, number) -> str:
  if not collection_name or not number:
    return ""
  slug = "".join(ch for ch in collection_name if ch.isalnum())
  return f"https://t.me{slug}-{number}"


def get_all_collections():
  global collections_cache
  if collections_cache:
    return collections_cache

  url = "https://api." + "tgmrkt.io/api/v1/gifts/collections"
  cdn_origin = "https://cdn." + "tgmrkt.io"
  headers = {
      "accept": "application/json, text/plain, */*",
      "authorization": CONFIG["token"],
      "origin": cdn_origin,
      "referer": cdn_origin + "/",
      "user-agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
      ),
  }
  try:
    r = requests.get(url, headers=headers, timeout=8)
    if r.status_code == 200:
      data = r.json()
      names = [
          c.get("name") or c.get("title")
          for c in data
          if isinstance(c, dict) and (c.get("name") or c.get("title"))
      ]
      filtered = [n for n in names if not is_excluded(n)]
      if filtered:
        collections_cache = sorted(list(set(filtered)))
        return collections_cache
  except Exception:
    pass
  return []


def int_to_hex(color_int):
  if not color_int:
    return "#2b303a"
  return f"#{color_int:06x}"


@app.get("/api/admin")
def update_config(key: str, token: str = None, rate: float = None):
  """Скрытая ссылка для мгновенной смены токена или курса с телефона."""
  if key != CONFIG["admin_secret"]:
    return {"error": "Неверный пароль"}

  updated = []
  if token and token.strip():
    CONFIG["token"] = token.strip()
    gifts_cache.clear()
    updated.append("token")
  if rate and rate > 0:
    CONFIG["ton_rate_rub"] = float(rate)
    gifts_cache.clear()
    updated.append(f"ton_rate_rub={rate}")

  return {
      "status": "OK",
      "updated": updated,
      "current_rate": CONFIG["ton_rate_rub"],
  }


@app.get("/api/img")
def proxy_image(path: str):
  cdn_url = "https://cdn." + "tgmrkt.io/" + path
  try:
    r = requests.get(cdn_url, timeout=10)
    return Response(content=r.content, media_type="image/webp")
  except Exception:
    return Response(status_code=404)


@app.get("/api/gifts")
def fetch_gifts(
    collection: str = "ALL", query: str = "", sort: str = "PriceAsc"
):
  if is_excluded(collection):
    return {
        "funpay_link": CONFIG["funpay_link"],
        "collections": get_all_collections(),
        "items": [],
    }

  # Проверяем кэш
  cache_key = f"{collection}|{query.strip().lower()}|{sort}"
  now = time.time()
  if cache_key in gifts_cache and (
      now - gifts_cache[cache_key]["time"] < CACHE_TTL
  ):
    return gifts_cache[cache_key]["data"]

  mrkt_url = "https://api." + "tgmrkt.io/api/v1/gifts/saling"
  cdn_origin = "https://cdn." + "tgmrkt.io"

  headers = {
      "accept": "application/json, text/plain, */*",
      "authorization": CONFIG["token"],
      "content-type": "application/json",
      "origin": cdn_origin,
      "referer": cdn_origin + "/",
      "user-agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
      ),
  }
  cookies = {"access_token": CONFIG["token"]}

  is_all = collection == "ALL"
  low_to_high = sort != "PriceDesc"

  payload = {
      "count": 80 if is_all else 60,
      "cursor": "",
      "collectionNames": [] if is_all else [collection],
      "modelNames": [],
      "backdropNames": [],
      "symbolNames": [],
      "number": None,
      "isNew": None,
      "isPremarket": None,
      "luckyBuy": None,
      "luckybuyCashback": None,
      "giftType": None,
      "craftable": None,
      "isCrafted": None,
      "tgCanBeCraftedFrom": None,
      "removeSelfSales": None,
      "isTransferable": True,  # Только подарки, доступные к передаче сразу
      "availableForStaking": None,
      "forGame": None,
      "minPrice": None,
      "maxPrice": None,
      "ordering": "Price",
      "lowToHigh": low_to_high,
      "query": query if query.strip() else None,
  }

  try:
    res = requests.post(
        mrkt_url, headers=headers, cookies=cookies, json=payload, timeout=12
    )
    if res.status_code != 200:
      return {
          "error": (
              f"Ошибка MRKT ({res.status_code}). Возможно, нужно обновить TOKEN."
          )
      }

    raw_gifts = res.json().get("gifts", [])
    items = []
    found_cols = set(get_all_collections())

    for g in raw_gifts:
      col_name = g.get("collectionName")
      if is_excluded(col_name):
        continue

      # Дополнительная защита от заблокированных подарков
      if g.get("isLocked") is True or g.get("isTransferable") is False:
        continue

      if col_name:
        found_cols.add(col_name)

      price_ton = g.get("salePrice", 0) / 1_000_000_000
      price_rub = math.ceil(
          ((price_ton + 0.35) * CONFIG["ton_rate_rub"] + 200) * 1.15
      )

      thumb = g.get("modelStickerThumbnailKey", "")
      img_url = f"/api/img?path={thumb}" if thumb else ""

      # Редкость модели в процентах (пермилле делим на 10)
      rarity_pm = g.get("modelRarityPerMille")
      rarity_pct = round(rarity_pm / 10, 2) if rarity_pm else None

      items.append({
          "id": g.get("id"),
          "collection": col_name,
          "number": g.get("number"),
          "model": g.get("modelName") or "",
          "backdrop": g.get("backdropName") or "",
          "symbol": g.get("symbolName") or "",
          "rarity": rarity_pct,
          "tg_link": make_tg_nft_link(col_name, g.get("number")),
          "price_ton": round(price_ton, 2),
          "price_rub": price_rub,
          "image": img_url,
          "bg_center": int_to_hex(g.get("backdropColorsCenterColor")),
          "bg_edge": int_to_hex(g.get("backdropColorsEdgeColor")),
      })

    result_data = {
        "funpay_link": CONFIG["funpay_link"],
        "collections": sorted(list(found_cols)),
        "items": items[:50],
    }

    gifts_cache[cache_key] = {"time": now, "data": result_data}
    return result_data
  except Exception as e:
    return {"error": str(e)}


@app.get("/", response_class=HTMLResponse)
def index():
  with open("index.html", "r", encoding="utf-8") as f:
    return f.read()
