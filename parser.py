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

TOKEN = "deee1872-59ff-499b-9021-d7c82e40099f"
FUNPAY_LINK = "https://funpay" + ".com/"

COLLECTIONS = [
    "Snake Box",
    "Lunar Snake",
    "Lol Pop",
    "Xmas Stocking",
    "Pool Float",
    "Vice Cream",
    "Big Year",
    "Chill Flame",
    "Tama Gadget",
    "Mirage Lamp",
    "Instant Ramen",
    "Candy Cane",
    "Whip Cupcake",
    "Ice Cream",
    "Pet Snake",
    "Jester Hat",
    "Easter Egg",
    "Hypno Lollipop",
    "Star Notepad",
    "Happy Brownie",
    "Mood Pack",
    "Timeless Book",
    "Hex Pot",
    "Holiday Drink",
    "Spiced Wine",
    "Money Pot",
    "B-Day Candle",
    "Jack-in-the-Box",
    "Victory Medal",
]

ton_rate_cache = {"rate": 500.0, "updated_at": 0}


def get_ton_to_rub():
  now = time.time()
  if now - ton_rate_cache["updated_at"] > 300:
    try:
      cg_url = (
          "https://api."
          + "://coingecko.com"
      )
      r = requests.get(cg_url, timeout=5)
      if r.status_code == 200:
        ton_rate_cache["rate"] = float(r.json()["the-open-network"]["rub"])
        ton_rate_cache["updated_at"] = now
    except Exception:
      pass
  return ton_rate_cache["rate"]


def int_to_hex(color_int):
  if not color_int:
    return "#2b303a"
  return f"#{color_int:06x}"


@app.get("/api/img")
def proxy_image(path: str):
  cdn_url = "https://cdn." + "tgmrkt.io/" + path
  try:
    r = requests.get(cdn_url, timeout=10)
    return Response(content=r.content, media_type="image/webp")
  except Exception:
    return Response(status_code=404)


@app.get("/api/gifts")
def fetch_gifts(collection: str = "Snake Box"):
  mrkt_url = "https://api." + "tgmrkt.io/api/v1/gifts/saling"
  cdn_origin = "https://cdn." + "tgmrkt.io"

  headers = {
      "accept": "application/json, text/plain, */*",
      "authorization": TOKEN,
      "content-type": "application/json",
      "origin": cdn_origin,
      "referer": cdn_origin + "/",
      "user-agent": (
          "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36"
      ),
  }
  cookies = {"access_token": TOKEN}

  payload = {
        "count": 30,
        "cursor": "",
        "collectionNames": [collection] if collection != "ALL" else COLLECTIONS,
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
        "isTransferable": None,
        "availableForStaking": None,
        "forGame": None,
        "minPrice": None,
        "maxPrice": None,
        "ordering": "Price",
        "lowToHigh": True,
        "query": None,
    }

  try:
    res = requests.post(
        mrkt_url, headers=headers, cookies=cookies, json=payload, timeout=10
    )
    if res.status_code != 200:
      return {
          "error": (
              f"Ошибка MRKT ({res.status_code}). Возможно, нужно обновить TOKEN."
          )
      }

    raw_gifts = res.json().get("gifts", [])
    ton_rate = get_ton_to_rub()
    items = []

    for g in raw_gifts:
      price_ton = g.get("salePrice", 0) / 1_000_000_000
      price_rub = math.ceil(((price_ton + 0.35) * ton_rate + 200) * 1.15)

      thumb = g.get("modelStickerThumbnailKey", "")
      img_url = f"/api/img?path={thumb}" if thumb else ""

      items.append({
          "id": g.get("id"),
          "collection": g.get("collectionName"),
          "number": g.get("number"),
          "model": g.get("modelName"),
          "backdrop": g.get("backdropName"),
          "symbol": g.get("symbolName"),
          "price_ton": round(price_ton, 2),
          "price_rub": price_rub,
          "image": img_url,
          "bg_center": int_to_hex(g.get("backdropColorsCenterColor")),
          "bg_edge": int_to_hex(g.get("backdropColorsEdgeColor")),
      })

    return {
        "ton_rate": ton_rate,
        "funpay_link": FUNPAY_LINK,
        "collections": COLLECTIONS,
        "items": items,
    }
  except Exception as e:
    return {"error": str(e)}


@app.get("/", response_class=HTMLResponse)
def index():
  with open("index.html", "r", encoding="utf-8") as f:
    return f.read()
