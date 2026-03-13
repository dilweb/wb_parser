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
