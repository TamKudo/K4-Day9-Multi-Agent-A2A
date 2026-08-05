"""Read-only indexed access to the nine Olist source CSV files.

This module is the data boundary for every domain agent.  Agents must not
open CSV files themselves: doing so makes joins, null handling, and source
ordering inconsistent across the pipeline.
"""

from __future__ import annotations

import csv
from collections import defaultdict
from copy import deepcopy
from dataclasses import dataclass
from decimal import Decimal
from pathlib import Path
from typing import Any, Iterable


Row = dict[str, Any]


@dataclass(frozen=True)
class DatasetCounts:
    """Number of source records loaded from each required dataset."""

    customers: int
    geolocations: int
    orders: int
    order_items: int
    order_payments: int
    order_reviews: int
    products: int
    sellers: int
    category_translations: int


class DataRepository:
    """In-memory, read-only indexes over the supplied Olist data.

    IDs and timestamps remain strings. Empty CSV cells are represented by
    ``None``. Financial amounts are :class:`decimal.Decimal` to keep payment
    reconciliation exact until a domain agent rounds its final output.

    Every public method returns a defensive copy, and list queries preserve
    their source CSV order. This directly supports the output-schema rule that
    arrays have a stable data-source order.
    """

    _FILES = {
        "customers": "olist_customers_dataset.csv",
        "geolocations": "olist_geolocation_dataset.csv",
        "orders": "olist_orders_dataset.csv",
        "order_items": "olist_order_items_dataset.csv",
        "order_payments": "olist_order_payments_dataset.csv",
        "order_reviews": "olist_order_reviews_dataset.csv",
        "products": "olist_products_dataset.csv",
        "sellers": "olist_sellers_dataset.csv",
        "category_translations": "product_category_name_translation.csv",
    }

    def __init__(self, data_dir: str | Path) -> None:
        self.data_dir = Path(data_dir)
        self._ensure_required_files()

        customers = self._read("customers", int_fields=("customer_zip_code_prefix",))
        orders = self._read("orders")
        items = self._read(
            "order_items",
            int_fields=("order_item_id",),
            decimal_fields=("price", "freight_value"),
        )
        payments = self._read(
            "order_payments",
            int_fields=("payment_sequential", "payment_installments"),
            decimal_fields=("payment_value",),
        )
        reviews = self._read("order_reviews")
        products = self._read(
            "products",
            int_fields=(
                "product_name_lenght", "product_description_lenght",
                "product_photos_qty", "product_weight_g", "product_length_cm",
                "product_height_cm", "product_width_cm",
            ),
        )
        sellers = self._read("sellers", int_fields=("seller_zip_code_prefix",))
        translations = self._read("category_translations")
        geolocations = self._read("geolocations", int_fields=("geolocation_zip_code_prefix",))

        self._customers_by_id = self._index_unique(customers, "customer_id")
        self._orders_by_id = self._index_unique(orders, "order_id")
        self._items_by_order = self._index_many(items, "order_id")
        self._payments_by_order = self._index_many(payments, "order_id")
        self._reviews_by_order = self._index_many(reviews, "order_id")
        self._products_by_id = self._index_unique(products, "product_id")
        self._sellers_by_id = self._index_unique(sellers, "seller_id")
        self._translations_by_category = self._index_unique(translations, "product_category_name")
        self._geolocations_by_zip = self._index_many(geolocations, "geolocation_zip_code_prefix")

        self._orders_by_customer_unique_id: dict[str, list[Row]] = defaultdict(list)
        # Dict insertion order equals orders CSV order, so history is stable.
        for order in self._orders_by_id.values():
            customer = self._customers_by_id.get(order["customer_id"])
            if customer is not None:
                self._orders_by_customer_unique_id[customer["customer_unique_id"]].append(order)

        self.counts = DatasetCounts(
            customers=len(customers), geolocations=len(geolocations), orders=len(orders),
            order_items=len(items), order_payments=len(payments), order_reviews=len(reviews),
            products=len(products), sellers=len(sellers), category_translations=len(translations),
        )

    # Core queries used by Customer, Order/Product, Payment, and Delivery agents.
    def get_order(self, order_id: str) -> Row | None:
        return self._copy_one(self._orders_by_id.get(order_id))

    def get_customer(self, customer_id: str) -> Row | None:
        return self._copy_one(self._customers_by_id.get(customer_id))

    def get_orders_by_customer_unique_id(self, customer_unique_id: str) -> list[Row]:
        return self._copy_many(self._orders_by_customer_unique_id.get(customer_unique_id, []))

    def get_items_by_order(self, order_id: str) -> list[Row]:
        return self._copy_many(self._items_by_order.get(order_id, []))

    def get_payments_by_order(self, order_id: str) -> list[Row]:
        return self._copy_many(self._payments_by_order.get(order_id, []))

    # Remaining source datasets are exposed for complete repository coverage.
    def get_reviews_by_order(self, order_id: str) -> list[Row]:
        return self._copy_many(self._reviews_by_order.get(order_id, []))

    def get_product(self, product_id: str) -> Row | None:
        return self._copy_one(self._products_by_id.get(product_id))

    def get_seller(self, seller_id: str) -> Row | None:
        return self._copy_one(self._sellers_by_id.get(seller_id))

    def get_category_translation(self, category_name: str) -> Row | None:
        return self._copy_one(self._translations_by_category.get(category_name))

    def get_geolocations_by_zip(self, zip_code_prefix: int | str) -> list[Row]:
        return self._copy_many(self._geolocations_by_zip.get(int(zip_code_prefix), []))

    def _ensure_required_files(self) -> None:
        missing = [name for name in self._FILES.values() if not (self.data_dir / name).is_file()]
        if missing:
            raise FileNotFoundError(f"Missing required Olist CSV file(s): {', '.join(missing)}")

    def _read(
        self,
        dataset: str,
        *,
        int_fields: tuple[str, ...] = (),
        decimal_fields: tuple[str, ...] = (),
    ) -> list[Row]:
        # utf-8-sig accepts ordinary UTF-8 and strips the BOM in the supplied
        # category translation CSV, preventing a malformed first header.
        path = self.data_dir / self._FILES[dataset]
        with path.open("r", encoding="utf-8-sig", newline="") as source:
            result: list[Row] = []
            for raw in csv.DictReader(source):
                row: Row = {key: (value if value != "" else None) for key, value in raw.items()}
                for field in int_fields:
                    if row[field] is not None:
                        row[field] = int(row[field])
                for field in decimal_fields:
                    if row[field] is not None:
                        row[field] = Decimal(row[field])
                result.append(row)
            return result

    @staticmethod
    def _index_unique(rows: Iterable[Row], key: str) -> dict[Any, Row]:
        index: dict[Any, Row] = {}
        for row in rows:
            value = row[key]
            if value in index:
                raise ValueError(f"Duplicate unique key {key}: {value}")
            index[value] = row
        return index

    @staticmethod
    def _index_many(rows: Iterable[Row], key: str) -> dict[Any, list[Row]]:
        index: dict[Any, list[Row]] = defaultdict(list)
        for row in rows:
            index[row[key]].append(row)
        return dict(index)

    @staticmethod
    def _copy_one(row: Row | None) -> Row | None:
        return deepcopy(row) if row is not None else None

    @staticmethod
    def _copy_many(rows: Iterable[Row]) -> list[Row]:
        return deepcopy(list(rows))
