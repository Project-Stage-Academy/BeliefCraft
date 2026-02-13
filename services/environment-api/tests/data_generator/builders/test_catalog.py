"""
Tests for the CatalogBuilder.

Validates the generation of master data entities (Products and Suppliers),
ensuring that random generation respects the configured boundaries and
business logic (e.g., SKU formatting).
"""

from unittest.mock import MagicMock, patch

import pytest
from src.data_generator.builders.catalog import CatalogBuilder

from packages.database.src.models import Product, Supplier


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
    with patch("src.data_generator.builders.catalog.settings") as mock_set:
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
        builder = CatalogBuilder(mock_session)
        count = 5

        products = builder.create_products(count)

        assert len(products) == count
        assert mock_session.add.call_count == count
        assert mock_session.flush.call_count == 1

        for product in products:
            assert isinstance(product, Product)
            # Verify SKU logic: First 3 letters of category, uppercased + '-'
            assert product.sku.startswith("FOO-")
            assert product.category == "Food"

            # Verify shelf life honors the config bounds
            assert 10 <= product.shelf_life_days <= 20

            # Verify Faker generated a string for the name
            assert len(product.name) > 0

    def test_create_suppliers_core_logic(self, mock_session, mock_settings):
        """
        Verifies the correct generation of supplier nodes, ensuring
        reliability scores and regions fall within valid configured bounds.
        """
        builder = CatalogBuilder(mock_session)
        count = 3

        suppliers = builder.create_suppliers(count)

        assert len(suppliers) == count
        assert mock_session.add.call_count == count
        assert mock_session.flush.call_count == 1

        for supplier in suppliers:
            assert isinstance(supplier, Supplier)
            # Verify region is selected from the allowed mock list
            assert supplier.region in ["EU-WEST", "US-EAST"]

            # Verify reliability score falls within the mocked 0.80 - 0.95 range
            assert 0.80 <= supplier.reliability_score <= 0.95

            # Verify Faker generated a string for the company name
            assert len(supplier.name) > 0
