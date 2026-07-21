"""Формирование и отправка Telegram-сводки."""

from __future__ import annotations

from scripts.ozon_export import ProductReport


def build_summary(products: list[ProductReport], threshold: int) -> str:
    low_stock = [item for item in products if item.stock < threshold]
    lines = [f"📊 Сводка Ozon: {len(products)} товаров"]
    for item in products:
        marker = " ⚠️ заканчивается" if item.stock < threshold else ""
        lines.append(f"• {item.name}\n  Цена: {item.price} | Остаток: {item.stock}{marker}")
    lines.append(f"\n⚠️ Ниже порога {threshold}: {len(low_stock)}")
    return "\n".join(lines)


def split_messages(text: str, limit: int = 4000) -> list[str]:
    """Разделяет длинную сводку по строкам, не превышая лимит Telegram."""
    parts: list[str] = []
    current = ""
    for line in text.splitlines(keepends=True):
        if current and len(current) + len(line) > limit:
            parts.append(current.rstrip())
            current = ""
        while len(line) > limit:
            parts.append(line[:limit])
            line = line[limit:]
        current += line
    if current:
        parts.append(current.rstrip())
    return parts or [text]
