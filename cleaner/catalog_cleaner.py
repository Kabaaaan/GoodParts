import csv
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Iterable, Optional


RAW_FILE = Path("catalog_raw.csv")
OUTPUT_FILE = Path("catalog_clean.csv")


@dataclass
class CleanRow:
    offer_id: str
    name: str
    brand: str
    oem: str
    quantity: str
    price: Optional[float]
    stock: int


def normalize_spaces(value: str) -> str:
    return re.sub(r"\s+", " ", value or "").strip()


def normalize_offer_id(value: str) -> str:
    value = normalize_spaces(value)
    if not value:
        return ""
    value = value.replace(" ", "")
    value = re.sub(r"\s*-\s*", "-", value)
    return value.upper()


def clean_price(value: str) -> Optional[float]:
    if value is None:
        return None
    text = normalize_spaces(str(value)).lower()
    if not text:
        return None

    text = text.replace("руб.", "руб").replace("rur", "rub")
    match = re.search(r"\d[\d\s]*(?:[.,]\d+)?", text)
    if not match:
        return None

    number = match.group(0).replace(" ", "").replace(",", ".")
    try:
        return float(number)
    except ValueError:
        return None


def parse_quantity(name: str) -> str:
    text = normalize_spaces(name).lower()
    if not text:
        return ""

    if "пара" in text:
        return "2 шт"

    qty_match = re.search(
        r"\b(\d+)\s*(?:шт\.?|штук|pcs|pieces)\b",
        text,
        re.IGNORECASE,
    )
    if qty_match:
        return f"{qty_match.group(1)} шт"

    if re.search(r"\b(комплект|к-?т|компл\.?|набор|set|kit)\b", text):
        qty_match = re.search(r"\b(\d+)\s*(?:шт\.?|штук|pcs|pieces)\b", text)
        if qty_match:
            return f"{qty_match.group(1)} шт"
        return "комплект"

    return "Не указано"


def parse_brand(name: str, offer_id: str = "") -> str:
    text = normalize_spaces(name)
    lowered = text.lower()

    aliases = {
        "mavico": "Mavico",
        "dba": "DBA",
        "деталиус": "Деталиус",
    }
    for needle, brand in aliases.items():
        if needle in lowered:
            return brand

    if offer_id:
        tokens = re.findall(r"[A-Za-zА-Яа-яЁё]{2,}", text)
        if tokens:
            first = tokens[0]
            if first[0].isupper() and not first.isupper():
                return first

    return ""


def extract_oem(name: str) -> tuple[str, str]:
    text = normalize_spaces(name)
    if not text:
        return "", text

    match = re.search(r"\bOEM\s+(\S+)", text, flags=re.IGNORECASE)
    if not match:
        return "", text

    oem = match.group(1)

    cleaned_name = re.sub(
        r"\bOEM\s+\S+",
        "",
        text,
        flags=re.IGNORECASE,
    )
    cleaned_name = normalize_spaces(cleaned_name)
    return oem, cleaned_name


def clean_name(name: str, brand: str = "", oem: str = "", quantity: str = "") -> str:
    if not name:
        return ""

    cleaned = normalize_spaces(name)

    if brand:
        cleaned = re.sub(
            r"\b" + re.escape(brand) + r"\b",
            "",
            cleaned,
            flags=re.IGNORECASE,
        )

    cleaned = re.sub(r"\bOEM\s+\S+", "", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"\b[A-Z0-9-]+\d+[A-Z0-9-]*\b", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\b\d{4,}\b", "", cleaned)   

    qty_patterns = [
        r"\b\d+\s*шт\.?",
        r"\b\d+\s*штук",
        r"\bкомплект",
        r"\bк-?т",
        r"\bкомпл\.?",
        r"\bнабор",
        r"\bset",
        r"\bkit",
        r"\bпара",
        r"\b2\s*шт",
        r"\b\d+шт",
        r"\b\d+мм",
        r"[\(\)]",
    ]
    for pattern in qty_patterns:
        cleaned = re.sub(pattern, "", cleaned, flags=re.IGNORECASE)

    cleaned = re.sub(r"[\s,/-]+$", "", cleaned)
    cleaned = re.sub(r"^\s*[\s,/-]+\s*", "", cleaned)
    cleaned = normalize_spaces(cleaned)

    if cleaned and cleaned[0].islower():
        cleaned = cleaned[0].upper() + cleaned[1:]

    return cleaned


def parse_product(row: Dict[str, str]) -> CleanRow:
    raw_name = normalize_spaces(row.get("name", ""))
    raw_offer = normalize_offer_id(row.get("offer_id", ""))
    name = raw_name or raw_offer

    oem, name = extract_oem(name)
    brand = parse_brand(name, raw_offer)
    quantity = parse_quantity(name)

    name = clean_name(name, brand, oem, quantity)

    price = clean_price(row.get("price", ""))

    stock_raw = normalize_spaces(str(row.get("stock", "")))
    stock = int(stock_raw) if stock_raw.isdigit() else 0

    return CleanRow(
        offer_id=raw_offer or oem or "",
        name=name,
        brand=brand,
        oem=oem,
        quantity=quantity,
        price=price,
        stock=stock,
    )


def dedupe_key(row: CleanRow) -> str:
    if row.oem:
        return f"oem:{row.oem}"
    if row.offer_id:
        return f"offer:{row.offer_id}"
    return f"name:{re.sub(r'\s+', ' ', row.name).strip().lower()}"


def score_row(row: CleanRow) -> tuple[int, int, int, int]:
    return (
        1 if row.brand else 0,
        1 if row.oem else 0,
        1 if row.quantity and row.quantity != "Не указано" else 0,
        1 if row.price is not None else 0,
    )


def choose_better(existing: CleanRow, candidate: CleanRow) -> CleanRow:
    if candidate.stock > existing.stock:
        return candidate
    if candidate.stock < existing.stock:
        return existing

    if score_row(candidate) > score_row(existing):
        return candidate
    if score_row(candidate) < score_row(existing):
        return existing

    if len(candidate.name) > len(existing.name):
        return candidate
    return existing


def load_rows(path: Path) -> Iterable[dict]:
    with path.open("r", encoding="utf-8-sig", newline="") as file:
        yield from csv.DictReader(file)


def save_rows(path: Path, rows: Iterable[CleanRow]) -> None:
    fieldnames = ["offer_id", "name", "brand", "oem", "quantity", "price", "stock"]
    with path.open("w", encoding="utf-8-sig", newline="") as file:
        writer = csv.DictWriter(file, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(
                {
                    "offer_id": row.offer_id,
                    "name": row.name,
                    "brand": row.brand,
                    "oem": row.oem,
                    "quantity": row.quantity,
                    "price": "" if row.price is None else f"{row.price:g}",
                    "stock": row.stock,
                }
            )


def clean_catalog(input_file: Path = RAW_FILE, output_file: Path = OUTPUT_FILE) -> int:
    cleaned: Dict[str, CleanRow] = {}

    for raw_row in load_rows(input_file):
        row = parse_product(raw_row)
        if not row.name and not row.offer_id:
            continue

        key = dedupe_key(row)
        current = cleaned.get(key)
        if current is None:
            cleaned[key] = row
        else:
            cleaned[key] = choose_better(current, row)

    save_rows(output_file, cleaned.values())
    return len(cleaned)


def main() -> None:
    total = clean_catalog()
    print(f"Saved {total} unique rows to {OUTPUT_FILE}")


if __name__ == "__main__":
    main()