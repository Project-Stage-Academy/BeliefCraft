# file: services/environment-api/src/data_generator/builders/catalog.py
"""
Catalog Builder Module.

Handles the creation of the static product catalog and the supplier network.
This provides the "what" (Products) and the "from whom" (Suppliers) for the
simulation engine.
"""

import random
from typing import List
from sqlalchemy.orm import Session
from faker import Faker
from packages.database.src.models import Product, Supplier


class CatalogBuilder:
    """
    Specialist builder for Products and Suppliers.
    """

    def __init__(self, session: Session):
        """
        Args:
            session (Session): The active SQLAlchemy database session.
        """
        self.session = session
        self.fake = Faker()

    def create_products(self, count: int = 50) -> List[Product]:
        """
        Generates a variety of products across different categories.

        Args:
            count (int): Number of unique products to create.

        Returns:
            List[Product]: List of persisted Product entities.
        """
        categories = ["Electronics", "Food", "Pharmacy", "Clothing", "Home"]
        products = []

        for _ in range(count):
            category = random.choice(categories)
            # Higher shelf life for electronics, lower for food
            shelf_life = random.randint(3, 14) if category == "Food" else random.randint(180, 720)

            product = Product(
                sku=f"{category[:3].upper()}-{self.fake.unique.ean8()}",
                name=self.fake.catch_phrase(),
                category=category,
                unit_cost=round(random.uniform(5.0, 500.0), 2),
                shelf_life_days=shelf_life
            )
            self.session.add(product)
            products.append(product)

        self.session.flush()
        return products

    def create_suppliers(self, count: int = 5) -> List[Supplier]:
        """
        Generates suppliers with varying reliability scores.

        Args:
            count (int): Number of suppliers to create.
        """
        suppliers = []
        for _ in range(count):
            supplier = Supplier(
                name=self.fake.company(),
                contact_email=self.fake.company_email(),
                reliability=round(random.uniform(0.7, 0.99), 2)
            )
            self.session.add(supplier)
            suppliers.append(supplier)

        self.session.flush()
        return suppliers
