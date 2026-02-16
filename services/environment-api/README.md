# Environment API

Environment API for BeliefCraft services.

## Smart Query endpoints

Base prefix: `/api/v1/smart-query`

- `GET /inventory/current`
- `GET /shipments/delay-summary`
- `GET /observations/compare-balances`
- `GET /orders/at-risk`

Each endpoint returns a unified payload:

- `data`: query result
- `message`: human-readable summary
- `meta`: filters and execution metadata

## Direct SQL examples (PostgreSQL)

These examples mirror current `smart_query_builder` behavior and can be used in psql, BI tools, or notebooks.

### 1) Current inventory by warehouse/location

```sql
SELECT
  l.warehouse_id,
  l.id AS location_id,
  l.code AS location_code,
  p.id AS product_id,
  p.sku,
  ib.on_hand,
  CASE WHEN :include_reserved THEN ib.reserved ELSE 0 END AS reserved,
  ib.on_hand - (CASE WHEN :include_reserved THEN ib.reserved ELSE 0 END) AS available,
  ib.quality_status,
  ib.last_count_at
FROM inventory_balances ib
JOIN products p ON ib.product_id = p.id
JOIN locations l ON ib.location_id = l.id
WHERE
  (:location_id IS NULL OR l.id = :location_id)
  AND (:location_id IS NOT NULL OR :warehouse_id IS NULL OR l.warehouse_id = :warehouse_id)
  AND (:sku IS NULL OR p.sku = :sku)
  AND (:product_id IS NULL OR p.id = :product_id)
ORDER BY available ASC, p.sku ASC
LIMIT :limit OFFSET :offset;
```

### 2) Shipment delay summary + delayed list

```sql
WITH shipment_base AS (
  SELECT
    s.id AS shipment_id,
    s.status,
    s.route_id,
    s.origin_warehouse_id,
    s.destination_warehouse_id,
    s.shipped_at,
    s.arrived_at,
    CASE
      WHEN s.arrived_at IS NOT NULL
      THEN EXTRACT(EPOCH FROM (s.arrived_at - s.shipped_at)) / 3600.0
      ELSE NULL
    END AS transit_hours,
    (
      (s.arrived_at IS NULL AND s.shipped_at < (NOW() AT TIME ZONE 'UTC' - INTERVAL '48 hours'))
      OR
      (
        s.arrived_at IS NOT NULL
        AND EXTRACT(EPOCH FROM (s.arrived_at - s.shipped_at)) / 3600.0 > 48
      )
    ) AS is_delayed
  FROM shipments s
  WHERE
    s.shipped_at IS NOT NULL
    AND s.shipped_at >= :date_from
    AND s.shipped_at <= :date_to
    AND (
      :warehouse_id IS NULL
      OR s.origin_warehouse_id = :warehouse_id
      OR s.destination_warehouse_id = :warehouse_id
    )
    AND (:route_id IS NULL OR s.route_id = :route_id)
    AND (:status IS NULL OR s.status = :status)
)
SELECT
  COUNT(*) AS total_shipments,
  SUM(CASE WHEN arrived_at IS NOT NULL THEN 1 ELSE 0 END) AS delivered_count,
  SUM(CASE WHEN arrived_at IS NULL THEN 1 ELSE 0 END) AS in_transit_count,
  SUM(CASE WHEN is_delayed THEN 1 ELSE 0 END) AS delayed_count,
  AVG(CASE WHEN arrived_at IS NOT NULL THEN transit_hours END) AS avg_transit_hours
FROM shipment_base;
```

```sql
WITH shipment_base AS (
  -- same CTE as above
  SELECT
    s.id AS shipment_id,
    s.status,
    s.route_id,
    s.origin_warehouse_id,
    s.destination_warehouse_id,
    s.shipped_at,
    s.arrived_at,
    CASE
      WHEN s.arrived_at IS NOT NULL
      THEN EXTRACT(EPOCH FROM (s.arrived_at - s.shipped_at)) / 3600.0
      ELSE NULL
    END AS transit_hours,
    (
      (s.arrived_at IS NULL AND s.shipped_at < (NOW() AT TIME ZONE 'UTC' - INTERVAL '48 hours'))
      OR
      (
        s.arrived_at IS NOT NULL
        AND EXTRACT(EPOCH FROM (s.arrived_at - s.shipped_at)) / 3600.0 > 48
      )
    ) AS is_delayed
  FROM shipments s
  WHERE
    s.shipped_at IS NOT NULL
    AND s.shipped_at >= :date_from
    AND s.shipped_at <= :date_to
)
SELECT
  shipment_id,
  status,
  route_id,
  origin_warehouse_id,
  destination_warehouse_id,
  shipped_at,
  arrived_at,
  transit_hours
FROM shipment_base
WHERE is_delayed
ORDER BY shipped_at ASC
LIMIT 20;
```

### 3) Observations vs inventory balances

```sql
WITH observation_summary AS (
  SELECT
    w.id AS warehouse_id,
    l.id AS location_id,
    p.sku,
    p.id AS product_id,
    SUM(o.observed_qty * COALESCE(o.confidence, 0.0))
      / NULLIF(SUM(COALESCE(o.confidence, 0.0)), 0) AS observed_estimate,
    ib.on_hand,
    ib.reserved,
    (ib.on_hand - ib.reserved) AS available,
    COUNT(o.id) AS obs_count,
    AVG(o.confidence) AS avg_confidence
  FROM observations o
  JOIN products p ON o.product_id = p.id
  JOIN locations l ON o.location_id = l.id
  JOIN warehouses w ON l.warehouse_id = w.id
  JOIN inventory_balances ib
    ON ib.product_id = o.product_id
   AND ib.location_id = o.location_id
  WHERE
    o.observed_at >= :observed_from
    AND o.observed_at <= :observed_to
    AND o.is_missing = FALSE
    AND o.observed_qty IS NOT NULL
    AND (:warehouse_id IS NULL OR w.id = :warehouse_id)
    AND (:location_id IS NULL OR l.id = :location_id)
    AND (:sku IS NULL OR p.sku = :sku)
    AND (:product_id IS NULL OR p.id = :product_id)
  GROUP BY w.id, l.id, p.sku, p.id, ib.on_hand, ib.reserved
)
SELECT
  warehouse_id,
  location_id,
  sku,
  product_id,
  observed_estimate,
  on_hand,
  reserved,
  available,
  (observed_estimate - on_hand) AS discrepancy,
  obs_count,
  avg_confidence
FROM observation_summary
ORDER BY ABS(observed_estimate - on_hand) DESC, sku ASC
LIMIT :limit OFFSET :offset;
```

### 4) At-risk orders + top missing SKUs

```sql
WITH params AS (
  SELECT
    (NOW() AT TIME ZONE 'UTC') AS now_utc,
    (:horizon_hours || ' hours')::interval AS horizon_ivl
),
aggregates AS (
  SELECT
    o.id AS order_id,
    o.status,
    o.promised_at,
    o.sla_priority,
    COUNT(ol.id) AS total_lines,
    COALESCE(SUM(CASE WHEN GREATEST(ol.qty_ordered - ol.qty_allocated, 0) > 0
      THEN GREATEST(ol.qty_ordered - ol.qty_allocated, 0) ELSE 0 END), 0) AS total_open_qty,
    COALESCE(SUM(CASE WHEN GREATEST(ol.qty_ordered - ol.qty_allocated, 0) > 0
      THEN ol.service_level_penalty * GREATEST(ol.qty_ordered - ol.qty_allocated, 0) ELSE 0 END), 0)
      AS total_penalty_exposure,
    SUM(CASE
      WHEN GREATEST(ol.qty_ordered - ol.qty_allocated, 0) > 0
        OR (ol.qty_shipped < ol.qty_ordered AND o.promised_at <= p.now_utc + INTERVAL '24 hours')
      THEN 1 ELSE 0 END) AS risk_line_count
  FROM orders o
  JOIN order_lines ol ON ol.order_id = o.id
  JOIN params p ON TRUE
  WHERE
    o.promised_at IS NOT NULL
    AND o.promised_at <= p.now_utc + p.horizon_ivl
    AND o.sla_priority >= :min_sla_priority
    AND (:status IS NULL OR o.status = :status)
  GROUP BY o.id, o.status, o.promised_at, o.sla_priority
  HAVING SUM(CASE
    WHEN GREATEST(ol.qty_ordered - ol.qty_allocated, 0) > 0
      OR (ol.qty_shipped < ol.qty_ordered AND o.promised_at <= p.now_utc + INTERVAL '24 hours')
    THEN 1 ELSE 0 END) > 0
),
ranked_missing AS (
  SELECT
    o.id AS order_id,
    pr.sku,
    GREATEST(ol.qty_ordered - ol.qty_allocated, 0) AS open_qty,
    ROW_NUMBER() OVER (
      PARTITION BY o.id
      ORDER BY GREATEST(ol.qty_ordered - ol.qty_allocated, 0) DESC, pr.sku ASC
    ) AS rn
  FROM orders o
  JOIN order_lines ol ON ol.order_id = o.id
  JOIN products pr ON pr.id = ol.product_id
  JOIN params p ON TRUE
  WHERE
    o.promised_at IS NOT NULL
    AND o.promised_at <= p.now_utc + p.horizon_ivl
    AND o.sla_priority >= :min_sla_priority
    AND (:status IS NULL OR o.status = :status)
    AND GREATEST(ol.qty_ordered - ol.qty_allocated, 0) > 0
),
top_missing AS (
  SELECT
    order_id,
    ARRAY_AGG(sku ORDER BY rn ASC) AS top_missing_skus
  FROM ranked_missing
  WHERE rn <= 5
  GROUP BY order_id
)
SELECT
  a.order_id,
  a.status,
  a.promised_at,
  a.sla_priority,
  a.total_lines,
  a.total_open_qty,
  a.total_penalty_exposure,
  tm.top_missing_skus
FROM aggregates a
LEFT JOIN top_missing tm ON tm.order_id = a.order_id
ORDER BY a.total_penalty_exposure DESC, a.promised_at ASC
LIMIT :limit OFFSET :offset;
```
