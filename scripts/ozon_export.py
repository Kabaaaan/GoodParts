from __future__ import annotations

import asyncio
import csv
import logging
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Iterable

import httpx

from scripts.settings import Settings


logger = logging.getLogger(__name__)
PRODUCT_LIST_ENDPOINT = "/v3/product/list"
PRODUCT_INFO_ENDPOINT = "/v3/product/info/list"
RETRYABLE_STATUS_CODES = {429, 500, 502, 503, 504}


@dataclass(frozen=True)
class ProductReport:
    article: str
    name: str
    price: str
    stock: int
    exported_at: datetime


class OzonApiError(RuntimeError):
    """Ozon API returned a non-recoverable error or exhausted retries."""


def _chunks(values: list[int], size: int) -> Iterable[list[int]]:
    for start in range(0, len(values), size):
        yield values[start : start + size]


class OzonClient:
    def __init__(self, client: httpx.AsyncClient, settings: Settings) -> None:
        self.client = client
        self.settings = settings

    async def _post(self, endpoint: str, payload: dict[str, Any]) -> dict[str, Any]:
        for attempt in range(1, self.settings.max_retries + 1):
            try:
                response = await self.client.post(endpoint, json=payload)
                if response.status_code in RETRYABLE_STATUS_CODES:
                    retry_after = response.headers.get("Retry-After")
                    delay = float(retry_after) if retry_after else (
                        self.settings.retry_backoff_seconds * 2 ** (attempt - 1)
                    )
                    logger.warning(
                        "Ozon returned HTTP %s for %s (attempt %s/%s); retry in %.1f s",
                        response.status_code, endpoint, attempt, self.settings.max_retries, delay,
                    )
                    if attempt == self.settings.max_retries:
                        response.raise_for_status()
                    await asyncio.sleep(delay)
                    continue
                response.raise_for_status()
                return response.json()
            except (httpx.TimeoutException, httpx.NetworkError) as error:
                if attempt == self.settings.max_retries:
                    raise OzonApiError(f"Network error calling {endpoint}") from error
                delay = self.settings.retry_backoff_seconds * 2 ** (attempt - 1)
                logger.warning(
                    "Network error for %s: %s (attempt %s/%s); retry in %.1f s",
                    endpoint, error, attempt, self.settings.max_retries, delay,
                )
                await asyncio.sleep(delay)
            except httpx.HTTPStatusError as error:
                raise OzonApiError(
                    f"Ozon API error {error.response.status_code} for {endpoint}: {error.response.text}"
                ) from error
        raise OzonApiError(f"Retries exhausted for {endpoint}")

    async def get_product_ids(self) -> list[int]:
        product_ids: list[int] = []
        last_id = ""
        while True:
            data = await self._post(PRODUCT_LIST_ENDPOINT, {
                "filter": {}, "last_id": last_id, "limit": self.settings.page_size,
            })
            result = data.get("result", {})
            items = result.get("items", [])
            product_ids.extend(int(item["product_id"]) for item in items if item.get("product_id"))
            logger.info("Received catalog page: %s products, total %s", len(items), len(product_ids))
            last_id = result.get("last_id", "")
            if not last_id or not items:
                return product_ids

    async def get_products_info(self, product_ids: list[int]) -> list[dict[str, Any]]:
        products: list[dict[str, Any]] = []
        for number, batch in enumerate(_chunks(product_ids, self.settings.batch_size), start=1):
            data = await self._post(PRODUCT_INFO_ENDPOINT, {"product_id": batch})
            items = data.get("items", [])
            products.extend(items)
            logger.info("Received details batch %s: %s products", number, len(items))
        return products


def normalize_products(items: list[dict[str, Any]], exported_at: datetime) -> list[ProductReport]:
    reports: list[ProductReport] = []
    for item in items:
        stock = sum(int(warehouse.get("present", 0) or 0) for warehouse in item.get("stocks", {}).get("stocks", []))
        reports.append(ProductReport(
            article=str(item.get("offer_id", "")),
            name=str(item.get("name", "Без названия")),
            price=str(item.get("price", "")),
            stock=stock,
            exported_at=exported_at,
        ))
    return reports


def save_to_csv(products: list[ProductReport], reports_dir: Path) -> Path:
    reports_dir.mkdir(parents=True, exist_ok=True)
    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
    path = reports_dir / f"products_{timestamp}.csv"
    with path.open("w", newline="", encoding="utf-8-sig") as file:
        writer = csv.writer(file)
        writer.writerow(["Артикул", "Название", "Цена", "Остаток", "Дата выгрузки"])
        for product in products:
            writer.writerow([product.article, product.name, product.price, product.stock,
                             product.exported_at.strftime("%Y-%m-%d %H:%M:%S")])
    logger.info("CSV report saved: %s", path)
    return path


async def export_products(settings: Settings) -> tuple[list[ProductReport], Path]:
    headers = {"Client-Id": settings.client_id, "Api-Key": settings.api_key}
    async with httpx.AsyncClient(base_url=settings.base_url, headers=headers, timeout=settings.request_timeout) as client:
        ozon = OzonClient(client, settings)
        product_ids = await ozon.get_product_ids()
        logger.info("Catalog contains %s products", len(product_ids))
        raw_products = await ozon.get_products_info(product_ids)
    products = normalize_products(raw_products, datetime.now())
    return products, save_to_csv(products, settings.reports_dir)
