# file: services/environment-api/src/data_generator/builders/logistics.py
"""
Logistics Builder Module.

This module is responsible for constructing the transportation network that connects
discrete infrastructure nodes (Warehouses). It defines the "edges" of the supply
chain graph by creating Route entities and assigning probabilistic timing models
(LeadtimeModels) to them.

The module handles:
1.  Definition of statistical lead time models (Express, Standard, Ocean) to simulate realistic
    transit time variability and delay risks.
2.  Creation of a mesh network of Routes between warehouses, automatically selecting
    the appropriate Transport Mode (Air, Truck, Sea) based on geographical distance.
"""

import random
from typing import List
from sqlalchemy.orm import Session
from packages.database.src.models import Warehouse, Route, LeadtimeModel
from packages.database.src.enums import LeadtimeScope, DistFamily, TransportMode
from src.config_load import settings


class LogisticsBuilder:
    """
    Specialist builder for the logistics network layer.

    This class manages the creation of LeadtimeModel definitions and the
    subsequent routing logic that links warehouses together. It ensures that
    simulation entities have valid paths for inventory movement with
    associated cost/time attributes.
    """

    def __init__(self, session: Session):
        self.session = session
        self.rng = random.Random(settings.simulation.random_seed) # noqa: S311

    def create_global_leadtime_models(self) -> List[LeadtimeModel]:
        """
        Initializes the standard set of global shipping performance definitions.

        This method creates three distinct statistical models representing different
        tiers of logistics service. These models are used by the simulation engine
        to sample random transit times for shipments.

        The created models are:
        1.  Express (Air): Low variance, Normal distribution (Mean ~2 days).
        2.  Standard (Truck): Medium variance, Normal distribution (Mean ~5 days).
        3.  Ocean Freight: High variance, Lognormal distribution (Long tail risk).

        Returns:
            List[LeadtimeModel]: A list containing the three persisted LeadtimeModel objects
                                 in the order [Express, Standard, Ocean].
        """
        cfg = settings.logistics.models
        models = [
            # Express Model (Air Freight)
            LeadtimeModel(
                scope=LeadtimeScope.GLOBAL,
                dist_family=DistFamily.NORMAL,
                p1=cfg.express.p1,
                p2=cfg.express.p2,
                p_rare_delay=cfg.express.p_rare_delay,
                rare_delay_add_days=cfg.express.rare_delay_add_days
            ),
            # Standard Model (Truck/Ground)
            LeadtimeModel(
                scope=LeadtimeScope.GLOBAL,
                dist_family=DistFamily.NORMAL,
                p1=cfg.standard.p1,
                p2=cfg.standard.p2,
                p_rare_delay=cfg.standard.p_rare_delay,
                rare_delay_add_days=cfg.standard.rare_delay_add_days
            ),
            # Bulk Model (Ocean Freight)
            LeadtimeModel(
                scope=LeadtimeScope.GLOBAL,
                dist_family=DistFamily.LOGNORMAL,
                p1=cfg.ocean.p1,
                p2=cfg.ocean.p2,
                p_rare_delay=cfg.ocean.p_rare_delay,
                rare_delay_add_days=cfg.ocean.rare_delay_add_days
            )
        ]
        self.session.add_all(models)
        self.session.flush()
        return models

    def connect_warehouses(self, warehouses: List[Warehouse], models: List[LeadtimeModel]) -> List[Route]:
        """
        Constructs a fully connected mesh network between the provided warehouses.

        This method iterates through every pair of warehouses to create a Route entity.
        It simulates a decision-making process where the Transport Mode is selected
        based on the distance between the origin and destination.

        Logic Tiers:
        -   Short Range (< 800km): Assigned 'TRUCK' mode and linked to the Standard lead time model.
        -   Medium Range (< 5000km): Assigned 'AIR' mode and linked to the Express lead time model.
        -   Long Range (> 5000km): Assigned 'SEA' mode and linked to the Ocean lead time model.

        Args:
            warehouses (List[Warehouse]): The list of warehouse nodes to connect.
            models (List[LeadtimeModel]): The available performance models, expected in the
                                          order [Express, Standard, Ocean].

        Returns:
            List[Route]: A list of all created Route entities connecting the warehouses.
        """
        routes: List[Route] = []
        if len(warehouses) < 2:
            return routes

        express_model = models[0]
        standard_model = models[1]
        ocean_model = models[2]

        for i in range(len(warehouses)):
            for j in range(len(warehouses)):
                if i == j:
                    continue

                dist = self.rng.randint(
                    settings.logistics.distance.min_km,
                    settings.logistics.distance.max_km
                )

                if dist < settings.logistics.thresholds.truck_max_km:
                    mode = TransportMode.TRUCK
                    selected_model = standard_model

                elif dist < settings.logistics.thresholds.air_max_km:
                    mode = TransportMode.AIR
                    selected_model = express_model

                else:
                    mode = TransportMode.SEA
                    selected_model = ocean_model

                route = Route(
                    origin_warehouse_id=warehouses[i].id,
                    destination_warehouse_id=warehouses[j].id,
                    leadtime_model_id=selected_model.id,
                    distance_km=dist,
                    mode=mode
                )
                self.session.add(route)
                routes.append(route)

        self.session.flush()
        return routes
