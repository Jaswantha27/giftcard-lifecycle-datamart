# Gift Card Lifecycle Data Mart

A SQL data mart built on top of raw gift card issuance and redemption data,
aggregated to monthly cohort granularity, to answer the core question every
gift card program has to track: how much of what we issue actually gets
redeemed, how fast, and how much becomes breakage (unredeemed value
recognized as revenue once a card expires).

This is a **generalized, fully synthetic** re-implementation of a gift card
lifecycle / cohort analysis workflow I built in a production BI role. No
real customer, card, or transaction data is used — the dataset, currency
mix, and expiration policy are all invented for this project.

## The problem

Gift card data starts as two raw, transaction-grain tables: cards issued,
and redemptions against those cards. Neither table on its own answers the
business questions that matter:

- What % of a given month's issued value has been redeemed after 1, 3, 6,
  12 months?
- How much breakage should we expect to recognize, and when?
- Which issuance cohorts are redeeming slower than others?

Answering these requires reshaping transaction-grain data into a
**monthly-grain cohort fact table** — one row per (issuance cohort month,
calendar activity month) — with cumulative redemption, remaining balance,
and breakage computed correctly despite messy underlying data: refunds,
overdraft errors, voided cards, and cards that just sit dormant for a year
before someone remembers they have one.

## Approach

1. **Generate synthetic data** (`generate_data.py`) — 3,200 gift cards and
   3,556 redemption transactions, built from 8 scenario generators so every
   edge case below shows up at a realistic frequency.
2. **Load into Postgres** (`schema.sql` + `load_data.py`) — raw
   `giftcard_issuance` and `giftcard_redemption` tables, loaded from the
   generated CSVs.
3. **Build the data mart** (`build_mart.sql` + `run_mart_build.py`) — the
   core of this project. Builds a full per-card monthly spine (issuance
   month through the 24-month expiration window, or the data horizon,
   whichever is shorter), joins in redemptions per month, computes a
   **floored-and-capped cumulative redemption** (never below 0 despite
   refunds, never above `issued_amount` despite overdraft errors), then
   rolls up to cohort grain. Breakage is recognized only in a card's
   expiration month, not accumulated early.
4. **Analyze the results** (`analysis.sql`) — cohort-level and portfolio-level
   summary queries.
5. **Visualize the mart** (`make_dashboard.py`) — KPI summary, a cohort
   redemption heatmap (the classic "cohort triangle"), a breakage trend, and
   a currency breakdown.

The resulting `fact_giftcard_cohort_monthly` table is exactly the shape a
BI tool would import for cohort dashboards: one row per cohort per month,
every measure additive and ready to aggregate.

## Edge cases the mart handles

| Edge case | How it's handled |
|---|---|
| Full redemption in one transaction | Card reaches 100% cumulative redemption in a single month |
| Partial redemptions over multiple transactions | Cumulative redemption accumulates correctly across months |
| Never redeemed | Card contributes its full issued value to breakage at expiration |
| Same-month issuance and redemption | Handled naturally — month 0 already reflects full or partial redemption |
| Long dormancy (12+ months) before redemption | Spine includes every month regardless of activity, so dormancy is visible |
| Voided / cancelled cards | Excluded entirely from the mart — never real liability |
| Redemption exceeding remaining balance (overdraft error) | Cumulative redemption is capped at `issued_amount`, remaining balance never goes negative |
| Refund / negative-amount redemption | Cumulative redemption is floored at 0, so a refund can't push it negative |
| Card expiration (24-month policy) | Breakage is recognized exactly once, in the expiration month — not accumulated early as if dormancy itself were breakage |
| Repeat customers (multiple cards per customer) | `customer_id` is preserved in the raw layer for customer-level rollups beyond the cohort grain |

Every design decision above is documented inline in `build_mart.sql` next to
the SQL that implements it, so the reasoning is auditable, not just the output.

## Results (on the synthetic dataset)

- 3,200 cards issued ($292,701 total, across USD/EUR/GBP), 4,444 redemption
  transactions
- 711 cohort-month rows in the resulting data mart
- **11.9%** breakage rate — consistent with typical gift card program
  breakage rates in the 5-15% range
- Cohort redemption typically plateaus between 50-80% of issued value by
  month 12, depending on the cohort

## Tech stack

- **PostgreSQL** (via Docker Compose) — schema, indexing, CTE-based mart
  build using window functions (`SUM() OVER`, `LEAST`/`GREATEST` capping,
  `generate_series` for the monthly spine). Queries are portable to Redshift
  with minor syntax changes.
- **Python** (`psycopg2`, `pandas`, `matplotlib`) — orchestration and
  dashboard visualization.
- **Power BI** — the intended consumption layer for this mart. Because the
  fact table is already at clean monthly cohort grain with fully additive
  measures, it drops directly into a Power BI model for cohort matrix
  visuals, breakage trend cards, and a redemption curve — no additional
  transformation needed on the Power BI side. Suggested DAX measures:
  - `Redemption Rate % = DIVIDE(SUM(cumulative_redeemed_amount), SUM(cohort_issued_amount))`
  - `Breakage Rate % = DIVIDE(SUM(breakage_amount), SUM(cohort_issued_amount))`
  - `Redeemed This Month = SUM(redeemed_amount_this_month)`

## Running it

```bash
# 1. Start Postgres (see docker-compose.yml)
docker compose up -d

# 2. Install dependencies
pip install -r requirements.txt

# 3. Generate the synthetic datasets (already included in data/, re-run to regenerate)
python3 generate_data.py

# 4. Load schema + raw data into Postgres
python3 load_data.py

# 5. Build the monthly cohort data mart
python3 run_mart_build.py

# 6. Generate dashboard visuals
python3 make_dashboard.py
```

Results land in the `fact_giftcard_cohort_monthly` table and
`output/fact_giftcard_cohort_monthly.csv`. Run the queries in `analysis.sql`
against the same database for deeper cohort-level breakdowns.

## Testing without Docker

If Docker isn't available on your machine, `local_test.py` runs the exact
same mart-build logic using [DuckDB](https://duckdb.org/) (a pip-installable,
serverless SQL engine) directly against the local CSVs — no container or
server required.

```bash
pip install duckdb
python3 local_test.py
```

This produces the same `fact_giftcard_cohort_monthly.csv` and totals as the
Postgres path (verified: 711 cohort-month rows / $292,701 total issued /
$34,827 total breakage). It's a convenience path for local testing and
review; the Postgres + Docker Compose setup remains the primary,
production-representative version of this project.

## Repo structure

```
giftcard-lifecycle-datamart/
├── generate_data.py        # synthetic dataset generator (8 edge-case scenarios)
├── data/                     # giftcard_issuance.csv, giftcard_redemption.csv
├── schema.sql                 # raw tables + data mart table definitions
├── docker-compose.yml           # local Postgres instance
├── load_data.py                  # schema creation + raw CSV load
├── build_mart.sql                  # core mart-build logic (monthly cohort fact table)
├── run_mart_build.py                 # runs build_mart.sql + exports the mart to CSV
├── local_test.py                       # no-Docker verification path (DuckDB)
├── analysis.sql                         # cohort/portfolio summary queries
├── make_dashboard.py                      # KPI cards, cohort heatmap, breakage trend, currency chart
├── output/                                 # mart CSV + dashboard visuals
└── requirements.txt
```
