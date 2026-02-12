from typing import List
from sqlalchemy.orm import Session
from faker import Faker
from packages.common.logging import get_logger
from packages.database.src.models import Warehouse, Product, Supplier
from src.data_generator.builders.catalog import CatalogBuilder
from src.data_generator.builders.infrastructure import InfrastructureBuilder

logger = get_logger(__name__)


class WorldBuilder:
    """
    The General Contractor.
    Orchestrates specialized builders to construct the world.
    """

    def __init__(self, session: Session, seed: int = 42):
        self.session = session
        self.seed = seed
        self.fake = Faker()

        self.warehouses: List[Warehouse] = []
        self.products: List[Product] = []
        self.suppliers: List[Supplier] = []

        self.infra_builder = InfrastructureBuilder(session)
        self.catalog_builder = CatalogBuilder(session)

        logger.info('world_builder_initialized')

    def build_all(self) -> None:
        """
        Orchestrator method.
        """
        self.create_warehouses()
        self.create_products()

    def create_warehouses(self, count: int = 3) -> None:
        self.warehouses = self.infra_builder.create_warehouses(count)

        logger.info("warehouses_built", count=len(self.warehouses))

    def create_products(self, count: int = 50) -> None:
        """
        1. Create 'count' Product records with realistic categories and shelf life.
        2. Store in self.products.
        """
        self.products = self.catalog_builder.create_products(count)
        logger.info("products_built", count=len(self.products))

    def create_suppliers(self, count: int = 5) -> None:
        """
        1. Create 'count' Supplier records with reliability scores.
        2. Store in self.suppliers.
        """
        self.suppliers = self.catalog_builder.create_suppliers(count)
        logger.info("suppliers_built", count=len(self.suppliers))

    def create_logistics_network(self) -> None:
        """
        1. Create LeadtimeModel (global shipping rules).
        2. Create Routes connecting the self.warehouses.
        """
        pass
