SEARCH_QUERY = "пальто из натуральной шерсти"
DEST = "-1257786" # регион (Москва)
MAX_PAGES = 50
DELAY = 0.5 # пауза между запросами в секундах

OUTPUT_ALL = "catalog_all.xlsx"
OUTPUT_FILTERED = "catalog_filtered.xlsx"

FILTER_MIN_RATING = 4.5
FILTER_MAX_PRICE = 10000
FILTER_COUNTRY = "Россия"

HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "*/*",
}