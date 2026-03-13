import logging
import time

import requests
import pandas as pd

from config import DEST, HEADERS, MAX_PAGES, DELAY

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
logger = logging.getLogger(__name__)

_SEARCH_URL = (
    "https://search.wb.ru/exactmatch/ru/common/v18/search"
    "?appType=1&curr=rub&dest={dest}&lang=ru"
    "&page={page}&query={query}&resultset=catalog&sort=popular&spp=30"
)
_CARD_URL_BY_ID = "https://www.wildberries.ru/catalog/{nm_id}/detail.aspx"
_UPSTREAMS_URL = "https://cdn.wbbasket.ru/api/v3/upstreams"


def _load_basket_ranges() -> list[tuple[int, int, str]]:
    """Загружает актуальную таблицу маршрутизации basket-серверов с CDN WB."""
    try:
        resp = requests.get(_UPSTREAMS_URL, timeout=5)
        resp.raise_for_status()
        hosts = resp.json()["recommend"]["mediabasket_route_map"][0]["hosts"]
        return [
            (h["vol_range_from"], h["vol_range_to"], h["host"].removeprefix("basket-").removesuffix(".wbbasket.ru"))
            for h in hosts
        ]
    except Exception as e:
        logger.warning("не удалось загрузить таблицу basket-серверов: %s — используем fallback", e)
        return []


_BASKET_RANGES: list[tuple[int, int, str]] = _load_basket_ranges()


def fetch_search_page(query: str, page: int) -> list[dict]:
    """Функция запрашивает одну страницу поиска и возвращает список товаров"""
    url = _SEARCH_URL.format(dest=DEST, page=page, query=query)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        return resp.json().get("products", [])
    except requests.exceptions.Timeout:
        logger.warning("страница %d — таймаут, пропускаем", page)
    except requests.exceptions.HTTPError as e:
        logger.error("страница %d — HTTP ошибка: %s", page, e)
    except requests.exceptions.RequestException as e:
        logger.error("страница %d — ошибка запроса: %s", page, e)
    return []


def _basket_host(nm_id: int) -> str:
    """Определяет номер basket-сервера по артикулу."""
    vol = nm_id // 100_000
    for lo, hi, num in _BASKET_RANGES:
        if lo <= vol <= hi:
            return num
    logger.warning("nm_id %d (vol %d) вне таблицы basket-диапазонов", nm_id, vol)
    return "01"


def build_image_urls(nm_id: int, pics: int) -> list[str]:
    """Строит список URL изображений товара по артикулу и количеству фото."""
    vol = nm_id // 100_000
    part = nm_id // 1_000
    basket = _basket_host(nm_id)
    base = f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{nm_id}/images/big"
    return [f"{base}/{i}.webp" for i in range(1, pics + 1)]


def _card_json_url(nm_id: int) -> str:
    """Строит URL до card.json на CDN (тот же basket, что и картинки)."""
    vol = nm_id // 100_000
    part = nm_id // 1_000
    basket = _basket_host(nm_id)
    return f"https://basket-{basket}.wbbasket.ru/vol{vol}/part{part}/{nm_id}/info/ru/card.json"


def fetch_card_detail(nm_id: int) -> dict:
    """Запрашивает card.json с CDN и возвращает описание, характеристики, страну."""
    url = _card_json_url(nm_id)
    try:
        resp = requests.get(url, headers=HEADERS, timeout=10)
        resp.raise_for_status()
        data = resp.json()
        options: list[dict] = data.get("options", [])
        country = next(
            (o["value"] for o in options if "страна" in o.get("name", "").lower()),
            None,
        )
        return {
            "description": data.get("description", ""),
            "options": options,
            "country": country,
        }
    except requests.exceptions.Timeout:
        logger.warning("card %d — таймаут", nm_id)
    except requests.exceptions.HTTPError as e:
        logger.error("card %d — HTTP ошибка: %s", nm_id, e)
    except requests.exceptions.RequestException as e:
        logger.error("card %d — ошибка запроса: %s", nm_id, e)
    return {}


def build_record(raw: dict) -> dict:
    """Собирает полную запись товара из сырых данных поиска + card.json."""
    nm_id: int = raw["id"]
    pics: int = raw.get("pics", 0)

    detail = fetch_card_detail(nm_id)
    time.sleep(DELAY)

    sizes = raw.get("sizes", [])
    size_names = [s["name"] for s in sizes if s.get("name")]
    price_raw = sizes[0].get("price", {}).get("product", 0) if sizes else 0
    price = price_raw / 100

    options: list[dict] = detail.get("options", [])
    characteristics = "; ".join(f'{o["name"]}: {o["value"]}' for o in options)

    supplier_id: int = raw.get("supplierId", 0)

    return {
        "Ссылка на товар": _CARD_URL_BY_ID.format(nm_id=nm_id),
        "Артикул": nm_id,
        "Название": raw.get("name", ""),
        "Цена": price,
        "Описание": detail.get("description", ""),
        "Ссылки на изображения": ", ".join(build_image_urls(nm_id, pics)),
        "Характеристики": characteristics,
        "Продавец": raw.get("supplier", ""),
        "Ссылка на продавца": f"https://www.wildberries.ru/seller/{supplier_id}",
        "Размеры": ", ".join(size_names),
        "Остатки": raw.get("totalQuantity", 0),
        "Рейтинг": raw.get("reviewRating", 0),
        "Количество отзывов": raw.get("feedbacks", 0),
        "Страна производства": detail.get("country", ""),
    }


def collect_search_results(query: str) -> list[dict]:
    """Собирает все страницы поиска и возвращает сырой список товаров"""
    all_products = []
    for page in range(1, MAX_PAGES + 1):
        products = fetch_search_page(query, page)
        if not products:
            logger.info("страница %d пустая, завершаем сбор", page)
            break
        all_products.extend(products)
        logger.info("страница %d — получено %d шт. (всего: %d)", page, len(products), len(all_products))
        time.sleep(DELAY)
    return all_products
