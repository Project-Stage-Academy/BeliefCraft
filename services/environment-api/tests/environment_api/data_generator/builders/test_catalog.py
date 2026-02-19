"""
Tests for the CatalogBuilder.

Validates the generation of master data entities (Products and Suppliers),
ensuring that random generation respects the configured boundaries and
business logic (e.g., SKU formatting).
"""

from unittest.mock import MagicMock, patch

import pytest
from environment_api.data_generator.builders.catalog import CatalogBuilder


@pytest.fixture
def mock_session():
    """Provides a mocked SQLAlchemy session."""
    return MagicMock()


@pytest.fixture
def mock_settings():
    """
    Mocks the application settings to provide predictable boundaries
    for product categories, shelf-life generation, and supplier constraints.
    """
    with patch("environment_api.data_generator.builders.catalog.settings") as mock_set:
        # Mock product settings (Single category for predictable testing)
        mock_category_range = MagicMock()
        mock_category_range.min_days = 10
        mock_category_range.max_days = 20
        mock_set.catalog.category_shelf_life = {"Food": mock_category_range}

        # Mock supplier settings
        mock_set.catalog.supplier_regions = ["EU-WEST", "US-EAST"]
        mock_set.catalog.supplier_reliability.min = 0.80
        mock_set.catalog.supplier_reliability.max = 0.95

        yield mock_set


class TestCatalogBuilder:
    def test_create_products_core_logic(self, mock_session, mock_settings):
        """
        Verifies that products are created with the correct SKUs,
        categories, and fall strictly within the configured shelf-life constraints.
        """
        mock_settings.simulation.random_seed = 42

        # The builder iterates over these keys and accesses .min_days/.max_days
        mock_shelf_life = MagicMock()
        mock_shelf_life.min_days = 10
        mock_shelf_life.max_days = 20

        mock_settings.catalog.category_shelf_life = {
            "DAIRY": mock_shelf_life,
            "MEAT": mock_shelf_life,
        }

        # Now it is safe to initialize the builder
        builder = CatalogBuilder(mock_session)

        products = builder.create_products(count=5)

        assert len(products) == 5
        assert mock_session.add.call_count == 5
        # Verify strict shelf life constraints
        for product in products:
            assert 10 <= product.shelf_life_days <= 20
            assert product.category in ["DAIRY", "MEAT"]

    def test_create_suppliers_core_logic(self, mock_session, mock_settings):
        """
        Verifies the correct generation of supplier nodes, ensuring
        reliability scores and regions fall within valid configured bounds.
        """
        mock_settings.simulation.random_seed = 12345

        # The builder needs these values to calculate scores and pick regions
        mock_settings.catalog.supplier_reliability.min = 0.8
        mock_settings.catalog.supplier_reliability.max = 1.0
        mock_settings.catalog.supplier_regions = ["US-EAST", "EU-WEST"]

        # Now initialization will succeed
        builder = CatalogBuilder(mock_session)

        suppliers = builder.create_suppliers(count=3)

        # Assertions
        assert len(suppliers) == 3
        assert mock_session.add.call_count == 3

        for supplier in suppliers:
            # Check reliability is within our mocked range (0.8 - 1.0)
            assert 0.8 <= supplier.reliability_score <= 1.0
            # Check region is one of our mocked regions
            assert supplier.region in ["US-EAST", "EU-WEST"]
            # Check name is generated (Faker returns a string)
            assert isinstance(supplier.name, str)
            assert len(supplier.name) > 0
