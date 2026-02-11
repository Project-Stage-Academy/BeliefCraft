from typing import List

from sqlalchemy.orm import Session
from faker import Faker

from packages.common.logging import get_logger
from packages.database.src.models import Warehouse, Product, Supplier, Route

logger = get_logger(__name__)

class WorldBuilder:
    """
    Architect of the static environment.
    Responsible for creating the physical infrastructure (Warehouses),
    the catalog (Products), and the supply network (Suppliers, Routes).
    """
    def __init__(self, session: Session, seed: int = 42):
        self.session = session
        self.seed = seed

        self.fake = Faker()

        self.warehouses: List[Warehouse] = []
        self.products: List[Product] = []
        self.suppliers: List[Supplier] = []

    def build_all(self) -> None:
        """
        Orchestrator method.
        Calls the sub-methods in the correct order to respect Foreign Key dependencies.
        """
        pass

    def create_warehouses(self, count: int = 3) -> None:
        """
        1. Create 'count' Warehouse records.
        2. For each Warehouse, create the internal Location hierarchy (Zones -> Aisles -> Shelves).
        3. Store created warehouses in self.warehouses.
        """
        pass

    def create_products(self, count: int = 50) -> None:
        """
        1. Create 'count' Product records with realistic categories and shelf life.
        2. Store in self.products.
        """
        pass

    def create_suppliers(self, count: int = 5) -> None:
        """
        1. Create 'count' Supplier records with reliability scores.
        2. Store in self.suppliers.
        """
        pass

    def create_logistics_network(self) -> None:
        """
        1. Create LeadtimeModel (global shipping rules).
        2. Create Routes connecting the self.warehouses.
        """
        pass

