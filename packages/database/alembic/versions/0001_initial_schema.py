"""Initial warehouse schema for environment simulation."""

from __future__ import annotations

from alembic import op

# revision identifiers, used by Alembic.
revision = "0001_initial_schema"
down_revision = None
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Keep each DDL step small to avoid provider statement timeout on giant SQL blobs.
    op.execute("SET LOCAL statement_timeout = '0'")
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")

    op.execute(
        """
        DO $$
        BEGIN
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'quality_status') THEN
                CREATE TYPE quality_status AS ENUM ('ok', 'damaged', 'expired', 'quarantine');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'move_type') THEN
                CREATE TYPE move_type AS ENUM ('inbound', 'outbound', 'transfer', 'adjustment');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'location_type') THEN
                CREATE TYPE location_type AS ENUM ('shelf', 'bin', 'pallet_pos', 'dock', 'virtual');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'order_status') THEN
                CREATE TYPE order_status AS ENUM ('new', 'allocated', 'picked', 'shipped', 'cancelled');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'po_status') THEN
                CREATE TYPE po_status AS ENUM ('draft', 'submitted', 'partial', 'received', 'closed');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'device_type') THEN
                CREATE TYPE device_type AS ENUM ('camera', 'rfid_reader', 'weight_sensor', 'scanner');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'device_status') THEN
                CREATE TYPE device_status AS ENUM ('active', 'offline', 'maintenance');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'shipment_status') THEN
                CREATE TYPE shipment_status AS ENUM ('planned', 'in_transit', 'delivered', 'exception');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'shipment_direction') THEN
                CREATE TYPE shipment_direction AS ENUM ('inbound', 'outbound', 'transfer');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'route_mode') THEN
                CREATE TYPE route_mode AS ENUM ('truck', 'air', 'rail', 'sea');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'leadtime_scope') THEN
                CREATE TYPE leadtime_scope AS ENUM ('supplier', 'route', 'global');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'dist_family') THEN
                CREATE TYPE dist_family AS ENUM ('normal', 'lognormal', 'poisson');
            END IF;
            IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'obs_type') THEN
                CREATE TYPE obs_type AS ENUM ('scan', 'image_recog', 'manual_count');
            END IF;
        END
        $$;
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS warehouses (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL UNIQUE,
            region TEXT NOT NULL,
            tz TEXT NOT NULL
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS suppliers (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            name TEXT NOT NULL UNIQUE,
            reliability_score DOUBLE PRECISION NOT NULL DEFAULT 0.5,
            region TEXT NOT NULL,
            CONSTRAINT suppliers_reliability_score_range CHECK (reliability_score >= 0 AND reliability_score <= 1)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS leadtime_models (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            scope leadtime_scope NOT NULL,
            dist_family dist_family NOT NULL,
            p1 DOUBLE PRECISION,
            p2 DOUBLE PRECISION,
            p_rare_delay DOUBLE PRECISION NOT NULL DEFAULT 0,
            rare_delay_add_days DOUBLE PRECISION NOT NULL DEFAULT 0,
            fitted_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT leadtime_models_p_rare_delay_range CHECK (p_rare_delay >= 0 AND p_rare_delay <= 1),
            CONSTRAINT leadtime_models_rare_delay_non_negative CHECK (rare_delay_add_days >= 0)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS products (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            sku TEXT NOT NULL UNIQUE,
            name TEXT NOT NULL,
            category TEXT NOT NULL,
            shelf_life_days INTEGER,
            CONSTRAINT products_shelf_life_non_negative CHECK (shelf_life_days IS NULL OR shelf_life_days >= 0)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS locations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            warehouse_id UUID NOT NULL REFERENCES warehouses(id),
            parent_location_id UUID REFERENCES locations(id),
            code TEXT NOT NULL,
            type location_type NOT NULL,
            capacity_units INTEGER NOT NULL,
            CONSTRAINT locations_capacity_units_non_negative CHECK (capacity_units >= 0),
            CONSTRAINT uq_locations_warehouse_code UNIQUE (warehouse_id, code)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS routes (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            origin_warehouse_id UUID NOT NULL REFERENCES warehouses(id),
            destination_warehouse_id UUID NOT NULL REFERENCES warehouses(id),
            mode route_mode NOT NULL,
            distance_km DOUBLE PRECISION NOT NULL,
            leadtime_model_id UUID REFERENCES leadtime_models(id),
            CONSTRAINT routes_distance_km_non_negative CHECK (distance_km >= 0),
            CONSTRAINT routes_distinct_warehouses CHECK (origin_warehouse_id <> destination_warehouse_id),
            CONSTRAINT uq_routes_origin_destination_mode UNIQUE (origin_warehouse_id, destination_warehouse_id, mode)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_balances (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            product_id UUID NOT NULL REFERENCES products(id),
            location_id UUID NOT NULL REFERENCES locations(id),
            on_hand DOUBLE PRECISION NOT NULL DEFAULT 0,
            reserved DOUBLE PRECISION NOT NULL DEFAULT 0,
            last_count_at TIMESTAMPTZ,
            quality_status quality_status NOT NULL DEFAULT 'ok',
            CONSTRAINT check_on_hand_positive CHECK (on_hand >= 0),
            CONSTRAINT check_reserved_positive CHECK (reserved >= 0),
            CONSTRAINT uq_inventory_balances_product_location UNIQUE (product_id, location_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS orders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            customer_name TEXT NOT NULL,
            status order_status NOT NULL DEFAULT 'new',
            promised_at TIMESTAMPTZ,
            sla_priority DOUBLE PRECISION NOT NULL DEFAULT 0.5,
            requested_ship_from_region TEXT,
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
            CONSTRAINT orders_sla_priority_range CHECK (sla_priority >= 0 AND sla_priority <= 1)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS order_lines (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            order_id UUID NOT NULL REFERENCES orders(id) ON DELETE CASCADE,
            product_id UUID NOT NULL REFERENCES products(id),
            qty_ordered DOUBLE PRECISION NOT NULL,
            qty_allocated DOUBLE PRECISION NOT NULL DEFAULT 0,
            qty_shipped DOUBLE PRECISION NOT NULL DEFAULT 0,
            service_level_penalty DOUBLE PRECISION NOT NULL DEFAULT 0,
            CONSTRAINT check_qty_ordered_pos CHECK (qty_ordered > 0),
            CONSTRAINT check_qty_allocated_pos CHECK (qty_allocated >= 0),
            CONSTRAINT check_qty_shipped_pos CHECK (qty_shipped >= 0),
            CONSTRAINT check_penalty_pos CHECK (service_level_penalty >= 0),
            CONSTRAINT uq_order_lines_order_product UNIQUE (order_id, product_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS purchase_orders (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            supplier_id UUID NOT NULL REFERENCES suppliers(id),
            destination_warehouse_id UUID NOT NULL REFERENCES warehouses(id),
            status po_status NOT NULL DEFAULT 'draft',
            expected_at TIMESTAMPTZ,
            leadtime_model_id UUID REFERENCES leadtime_models(id),
            created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS po_lines (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            purchase_order_id UUID NOT NULL REFERENCES purchase_orders(id) ON DELETE CASCADE,
            product_id UUID NOT NULL REFERENCES products(id),
            qty_ordered DOUBLE PRECISION NOT NULL,
            qty_received DOUBLE PRECISION NOT NULL DEFAULT 0,
            CONSTRAINT check_po_qty_ordered_pos CHECK (qty_ordered > 0),
            CONSTRAINT check_po_qty_received_pos CHECK (qty_received >= 0),
            CONSTRAINT uq_po_lines_po_product UNIQUE (purchase_order_id, product_id)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS shipments (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            direction shipment_direction NOT NULL,
            origin_warehouse_id UUID REFERENCES warehouses(id),
            destination_warehouse_id UUID REFERENCES warehouses(id),
            order_id UUID REFERENCES orders(id),
            purchase_order_id UUID REFERENCES purchase_orders(id),
            route_id UUID REFERENCES routes(id),
            status shipment_status NOT NULL DEFAULT 'planned',
            shipped_at TIMESTAMPTZ,
            arrived_at TIMESTAMPTZ
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS inventory_moves (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            product_id UUID NOT NULL REFERENCES products(id),
            from_location_id UUID REFERENCES locations(id),
            to_location_id UUID REFERENCES locations(id),
            move_type move_type NOT NULL,
            qty DOUBLE PRECISION NOT NULL,
            occurred_at TIMESTAMPTZ NOT NULL,
            reason_code TEXT,
            reported_qty DOUBLE PRECISION,
            actual_qty DOUBLE PRECISION,
            CONSTRAINT check_qty_positive CHECK (qty > 0),
            CONSTRAINT check_reported_qty_positive CHECK (reported_qty IS NULL OR reported_qty >= 0),
            CONSTRAINT check_actual_qty_positive CHECK (actual_qty IS NULL OR actual_qty >= 0)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS sensor_devices (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            warehouse_id UUID NOT NULL REFERENCES warehouses(id),
            device_type device_type NOT NULL,
            noise_sigma DOUBLE PRECISION NOT NULL DEFAULT 0,
            missing_rate DOUBLE PRECISION NOT NULL DEFAULT 0,
            bias DOUBLE PRECISION NOT NULL DEFAULT 0,
            status device_status NOT NULL DEFAULT 'active',
            CONSTRAINT check_noise_positive CHECK (noise_sigma >= 0),
            CONSTRAINT check_missing_rate_valid CHECK (missing_rate >= 0 AND missing_rate <= 1)
        )
        """
    )

    op.execute(
        """
        CREATE TABLE IF NOT EXISTS observations (
            id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            observed_at TIMESTAMPTZ NOT NULL,
            device_id UUID NOT NULL REFERENCES sensor_devices(id),
            product_id UUID NOT NULL REFERENCES products(id),
            location_id UUID NOT NULL REFERENCES locations(id),
            obs_type obs_type NOT NULL,
            observed_qty DOUBLE PRECISION,
            confidence DOUBLE PRECISION NOT NULL DEFAULT 1.0,
            is_missing BOOLEAN NOT NULL DEFAULT FALSE,
            reported_noise_sigma DOUBLE PRECISION,
            related_move_id UUID REFERENCES inventory_moves(id),
            related_shipment_id UUID REFERENCES shipments(id),
            CONSTRAINT check_obs_qty_pos CHECK (observed_qty IS NULL OR observed_qty >= 0),
            CONSTRAINT check_confidence_valid CHECK (confidence >= 0 AND confidence <= 1),
            CONSTRAINT check_noise_sigma_pos CHECK (reported_noise_sigma IS NULL OR reported_noise_sigma >= 0)
        )
        """
    )

    index_statements = [
        "CREATE INDEX IF NOT EXISTS idx_locations_warehouse_id ON locations (warehouse_id)",
        "CREATE INDEX IF NOT EXISTS idx_locations_parent_location_id ON locations (parent_location_id)",
        "CREATE INDEX IF NOT EXISTS idx_routes_origin_warehouse_id ON routes (origin_warehouse_id)",
        "CREATE INDEX IF NOT EXISTS idx_routes_destination_warehouse_id ON routes (destination_warehouse_id)",
        "CREATE INDEX IF NOT EXISTS idx_routes_leadtime_model_id ON routes (leadtime_model_id)",
        "CREATE INDEX IF NOT EXISTS idx_inventory_balances_product_id ON inventory_balances (product_id)",
        "CREATE INDEX IF NOT EXISTS idx_inventory_balances_location_id ON inventory_balances (location_id)",
        "CREATE INDEX IF NOT EXISTS idx_orders_status ON orders (status)",
        "CREATE INDEX IF NOT EXISTS idx_orders_created_at ON orders (created_at)",
        "CREATE INDEX IF NOT EXISTS idx_order_lines_order_id ON order_lines (order_id)",
        "CREATE INDEX IF NOT EXISTS idx_order_lines_product_id ON order_lines (product_id)",
        "CREATE INDEX IF NOT EXISTS idx_purchase_orders_supplier_id ON purchase_orders (supplier_id)",
        "CREATE INDEX IF NOT EXISTS idx_purchase_orders_destination_warehouse_id ON purchase_orders (destination_warehouse_id)",
        "CREATE INDEX IF NOT EXISTS idx_purchase_orders_leadtime_model_id ON purchase_orders (leadtime_model_id)",
        "CREATE INDEX IF NOT EXISTS idx_purchase_orders_status ON purchase_orders (status)",
        "CREATE INDEX IF NOT EXISTS idx_po_lines_purchase_order_id ON po_lines (purchase_order_id)",
        "CREATE INDEX IF NOT EXISTS idx_po_lines_product_id ON po_lines (product_id)",
        "CREATE INDEX IF NOT EXISTS idx_shipments_origin_warehouse_id ON shipments (origin_warehouse_id)",
        "CREATE INDEX IF NOT EXISTS idx_shipments_destination_warehouse_id ON shipments (destination_warehouse_id)",
        "CREATE INDEX IF NOT EXISTS idx_shipments_order_id ON shipments (order_id)",
        "CREATE INDEX IF NOT EXISTS idx_shipments_purchase_order_id ON shipments (purchase_order_id)",
        "CREATE INDEX IF NOT EXISTS idx_shipments_route_id ON shipments (route_id)",
        "CREATE INDEX IF NOT EXISTS idx_shipments_status_arrived_at ON shipments (status, arrived_at)",
        "CREATE INDEX IF NOT EXISTS idx_inventory_moves_product_id ON inventory_moves (product_id)",
        "CREATE INDEX IF NOT EXISTS idx_inventory_moves_from_location_id ON inventory_moves (from_location_id)",
        "CREATE INDEX IF NOT EXISTS idx_inventory_moves_to_location_id ON inventory_moves (to_location_id)",
        "CREATE INDEX IF NOT EXISTS idx_inventory_moves_occurred_at ON inventory_moves (occurred_at)",
        "CREATE INDEX IF NOT EXISTS idx_inventory_moves_move_type ON inventory_moves (move_type)",
        "CREATE INDEX IF NOT EXISTS idx_sensor_devices_warehouse_id ON sensor_devices (warehouse_id)",
        "CREATE INDEX IF NOT EXISTS idx_sensor_devices_status ON sensor_devices (status)",
        "CREATE INDEX IF NOT EXISTS idx_observations_device_id ON observations (device_id)",
        "CREATE INDEX IF NOT EXISTS idx_observations_product_id ON observations (product_id)",
        "CREATE INDEX IF NOT EXISTS idx_observations_location_id ON observations (location_id)",
        "CREATE INDEX IF NOT EXISTS idx_observations_observed_at ON observations (observed_at)",
        "CREATE INDEX IF NOT EXISTS idx_observations_related_move_id ON observations (related_move_id)",
        "CREATE INDEX IF NOT EXISTS idx_observations_related_shipment_id ON observations (related_shipment_id)",
    ]

    for statement in index_statements:
        op.execute(statement)


def downgrade() -> None:
    op.execute("SET LOCAL statement_timeout = '0'")

    for statement in [
        "DROP TABLE IF EXISTS observations",
        "DROP TABLE IF EXISTS sensor_devices",
        "DROP TABLE IF EXISTS inventory_moves",
        "DROP TABLE IF EXISTS shipments",
        "DROP TABLE IF EXISTS po_lines",
        "DROP TABLE IF EXISTS purchase_orders",
        "DROP TABLE IF EXISTS order_lines",
        "DROP TABLE IF EXISTS orders",
        "DROP TABLE IF EXISTS inventory_balances",
        "DROP TABLE IF EXISTS routes",
        "DROP TABLE IF EXISTS locations",
        "DROP TABLE IF EXISTS products",
        "DROP TABLE IF EXISTS leadtime_models",
        "DROP TABLE IF EXISTS suppliers",
        "DROP TABLE IF EXISTS warehouses",
        "DROP TYPE IF EXISTS obs_type",
        "DROP TYPE IF EXISTS dist_family",
        "DROP TYPE IF EXISTS leadtime_scope",
        "DROP TYPE IF EXISTS route_mode",
        "DROP TYPE IF EXISTS shipment_direction",
        "DROP TYPE IF EXISTS shipment_status",
        "DROP TYPE IF EXISTS device_status",
        "DROP TYPE IF EXISTS device_type",
        "DROP TYPE IF EXISTS po_status",
        "DROP TYPE IF EXISTS order_status",
        "DROP TYPE IF EXISTS location_type",
        "DROP TYPE IF EXISTS move_type",
        "DROP TYPE IF EXISTS quality_status",
    ]:
        op.execute(statement)
