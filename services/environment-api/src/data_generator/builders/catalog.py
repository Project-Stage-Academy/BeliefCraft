# file: services/environment-api/src/data_generator/builders/catalog.py
"""
Catalog Builder Module.

This module is responsible for initializing the master data required for the
supply chain simulation. It handles the generation of:
1. Product definitions with category-specific attributes (e.g., shelf life).
2. Supplier entities with associated reliability scores and regional locations.

This data serves as the foundational "static" layer upon which dynamic
transactions (Orders, Shipments) are simulated.
"""
import random
from typing import List
from sqlalchemy.orm import Session
from faker import Faker
from packages.database.src.models import Product, Supplier
from src.config_load import settings


class CatalogBuilder:
    """
    Specialist builder for managing the lifecycle and generation of Products and Suppliers.
    """
    def __init__(self, session: Session):
        """
        Initializes the CatalogBuilder with an active database session.

        Args:
            session (Session): The SQLAlchemy session used to add and flush
                               newly created entities to the database.
        """
        self.session = session
        self.fake = Faker()
        self.rng = random.Random(settings.simulation.seed) # noqa: S311

    def create_products(self, count: int) -> List[Product]:
        """
        Generates a diverse catalog of product entities with realistic attributes.

        Args:
            count (int): The number of unique product records to generate.
                         Defaults to 50.

        Returns:
            List[Product]: A list of the persisted Product SQLAlchemy objects.
        """
        products = []
        available_categories = list(settings.catalog.category_shelf_life.keys())

        for _ in range(count):
            category = self.rng.choice(available_categories)

            shelf_life_range = settings.catalog.category_shelf_life[category]
            shelf_life = self.rng.randint(
                shelf_life_range.min_days,
                shelf_life_range.max_days
            )

            product = Product(
                sku=f"{category[:3].upper()}-{self.fake.unique.ean8()}",
                name=self.fake.catch_phrase(),
                category=category,
                shelf_life_days=shelf_life
            )
            self.session.add(product)
            products.append(product)

        self.session.flush()
        return products

    def create_suppliers(self, count: int = 5) -> List[Supplier]:
        """
        Constructs a network of external suppliers distributed across various regions.

        Args:
            count (int): The number of supplier entities to create. Defaults to 5.

        Returns:
            List[Supplier]: A list of the persisted Supplier SQLAlchemy objects.
        """
        suppliers = []

        for _ in range(count):
            supplier = Supplier(
                name=self.fake.company(),
                reliability_score=round(self.rng.uniform(
                    settings.catalog.supplier_reliability.min,
                    settings.catalog.supplier_reliability.max
                ), 2),
                region=self.rng.choice(settings.catalog.supplier_regions)
            )
            self.session.add(supplier)
            suppliers.append(supplier)

        self.session.flush()
        return suppliers
