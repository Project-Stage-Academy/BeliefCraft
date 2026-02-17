"""
World Builder Module.

This module acts as the central orchestrator (the "General Contractor") for the
data generation process. It coordinates specialized builders to construct a
coherent and interconnected simulation environment, ensuring that dependencies
(e.g., Warehouses must exist before Routes) are respected.
"""

import random

from common.logging import get_logger
from database.models import Product, Route, Supplier, Warehouse
from environment_api.config_load import settings
from environment_api.data_generator.builders.catalog import CatalogBuilder
from environment_api.data_generator.builders.infrastructure import InfrastructureBuilder
from environment_api.data_generator.builders.logistics import LogisticsBuilder
from faker import Faker
from sqlalchemy.orm import Session

logger = get_logger(__name__)


class WorldBuilder:
    """
    The General Contractor.
    Orchestrates specialized builders to construct the world.
    """

    def __init__(self, session: Session, seed: int):
        self.session = session
        self.seed = seed
        self.fake = Faker()
        Faker.seed(seed)
        random.seed(seed)

        # State containers for generated entities
        self.warehouses: list[Warehouse] = []
        self.products: list[Product] = []
        self.suppliers: list[Supplier] = []
        self.routes: list[Route] = []

        # Initialize specialized builders
        self.infra_builder = InfrastructureBuilder(session)
        self.catalog_builder = CatalogBuilder(session)
        self.logistics_builder = LogisticsBuilder(session)

        logger.info("world_builder_initialized", seed=seed, db_session_id=id(session))

    def build_all(self) -> None:
        """
        Orchestrator method.
        Executes the build steps in the specific order required to satisfy
        database foreign key constraints and logical dependencies.
        """
        self.create_warehouses(settings.world.warehouse_count)
        self.create_products(settings.world.product_count)
        self.create_suppliers(settings.world.supplier_count)
        self.create_logistics_network()

        logger.info("world_generation_completed")

    def create_warehouses(self, count: int) -> None:
        """
        Delegates the creation of physical infrastructure (Warehouses, Docks, Zones).
        """
        self.warehouses = self.infra_builder.create_warehouses(count)

        logger.info("warehouses_built", count=len(self.warehouses), target_count=count)

    def create_products(self, count: int) -> None:
        """
        Delegates the creation of the product catalog.
        """
        self.products = self.catalog_builder.create_products(count)

        logger.info("products_built", count=len(self.products), target_count=count)

    def create_suppliers(self, count: int) -> None:
        """
        Delegates the creation of external suppliers.
        """
        self.suppliers = self.catalog_builder.create_suppliers(count)

        logger.info("suppliers_built", count=len(self.suppliers), target_count=count)

    def create_logistics_network(self) -> None:
        """
        Establishes the transportation graph.
        1. Generates global LeadtimeModels (Express, Standard, Ocean).
        2. Connects all generated warehouses with Routes, assigning appropriate
           models and transport modes based on distance.
        """
        lt_models = self.logistics_builder.create_global_leadtime_models()

        self.routes = self.logistics_builder.connect_warehouses(self.warehouses, lt_models)

        logger.info(
            "logistics_network_built",
            routes_count=len(self.routes),
            leadtime_models_count=len(lt_models),
            nodes_connected=len(self.warehouses),
        )
