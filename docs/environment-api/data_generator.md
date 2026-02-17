# Warehouse Simulation & Data Generator

This system is a high-fidelity synthetic data generator designed to simulate a global supply chain and warehouse IoT environment. It creates a "Digital Twin" of a logistics network, simulating physical movements, demand patterns, and imperfect sensor observations.

---

## 1. System Architecture

The project is structured into two primary execution phases managed by the `SimulationRunner`.

### Phase A: World Building (Static Initialization)

Managed by the `WorldBuilder`, this phase constructs the "physical" world before any time-series data is generated. It handles:

- **Infrastructure**: Creating warehouses, internal zones, aisles, and staging docks.
- **Catalog**: Generating a master list of products with category-specific shelf lives and a network of suppliers.
- **Logistics Network**: Building a transportation mesh between warehouses, assigning transport modes (Air, Truck, Sea) based on distance.

### Phase B: Simulation Engine (Dynamic Execution)

The `SimulationEngine` advances a global clock day-by-day. Every "tick" (1 day) triggers a sequence of managers to maintain logical causality:

1. **InboundManager**: Processes arriving shipments and increases stock.
2. **OutboundManager**: Generates customer demand and fulfills orders.
3. **ReplenishmentManager**: Reviews stock levels and orders from suppliers if levels are low.
4. **SensorManager**: Scans the final state of the warehouse to produce noisy observation data.

---

## 2. Core Logical Models

### Stochastic Demand (Poisson Distribution)

The `OutboundManager` uses a Poisson distribution to simulate natural variability in customer orders. Instead of a flat rate, it samples a distribution where the probability of $k$ orders occurring in a day is defined by a configurable mean ($\lambda$).

### Stochastic Lead Times (Gaussian & Lognormal)

Logistics transit times are not fixed. The `LogisticsBuilder` assigns models where:

- **Express/Standard**: Use Gaussian (Normal) distributions (Mean/StdDev) to simulate minor delays.
- **Ocean**: Uses Lognormal distributions to simulate the "long tail" of significant maritime delays.

### Inventory Policy (s, S)

The `ReplenishmentManager` implements a classic (s, S) inventory policy:

- **s (Reorder Point)**: The threshold that triggers a new order.
- **S (Target Level)**: The quantity the system aims to reach when restocking.

### The Observation Layer (Sensor Noise)

The `SensorManager` creates the gap between "Ground Truth" and "System Reality":

- **Missing Rate**: A Bernoulli trial determines if a sensor fails to see an item.
- **Noise Model**: Applies Gaussian noise to the actual quantity to simulate imperfect sensor calibration, controlled by `noise_sigma`.

---

## 3. Configuration System

The project uses a hierarchical configuration system. A `ConfigLoader` reads YAML files and validates them against the Pydantic schemas found in `src/config_schema.py` and `src/config_simulation_schema.py`.

### YAML Structure Mapping

Your YAML configuration files should align with these key sections:

| YAML Section | Pydantic Class | Description |
|--------------|----------------|-------------|
| world        | WorldConfig    | Counts for warehouses, products, and suppliers. |
| layout       | LayoutConfig   | Min/Max capacities for docks, zones, and aisles. |
| outbound     | OutboundConfig | Customer names and Poisson mean for demand. |
| sensors      | SensorsConfig  | Probabilities for scans and noise model parameters. |
| logistics    | LogisticsConfig| Distance thresholds for mode selection (Truck/Air/Sea). |

---

## 4. Database Integrity: The Ledger

The system uses an `InventoryLedger` to ensure data consistency.

- **Atomic Updates**: Every change to `InventoryBalance` is paired with an `InventoryMove` record.
- **Audit Trail**: The `InventoryMove` table acts as the source of truth for every stock increase (Receipt) or decrease (Issuance).
- **Causality**: The `SimulationEngine` ensures receipts happen before shipments each day to prevent negative inventory balances.

---

## 5. How to Run the Project

### Prerequisites

- Python 3.9+
- A configured database (PostgreSQL/MySQL/SQLite) via the `packages.database` connection utility.

### Step 1: Configuration

Ensure your environment-specific YAML file (e.g., `config/dev.yaml`) is populated. You can override the configuration path using the `ENVIRONMENT_API_CONFIG` environment variable.

### Step 2: Run the Generator

Execute the seeding script to reset the database and simulate history:

```bash

# Execute the module
uv run python -m environment_api.data_generator.generate_seed_data
