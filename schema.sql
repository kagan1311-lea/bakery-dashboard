-- Tables for the bakery dashboard. Run by load_data.py; safe to run again.
-- See architecture.md → Storage.

CREATE TABLE IF NOT EXISTS sales (
    id            serial PRIMARY KEY,
    sold_at       timestamp     NOT NULL,
    ticket_number integer       NOT NULL,
    article       text          NOT NULL,
    category      text          NOT NULL,
    quantity      integer       NOT NULL,  -- negative = return
    unit_price    numeric(8, 2) NOT NULL   -- ILS
);

CREATE INDEX IF NOT EXISTS sales_sold_at_idx ON sales (sold_at);

CREATE TABLE IF NOT EXISTS agent_runs (
    id            serial PRIMARY KEY,
    asked_at      timestamptz   NOT NULL DEFAULT now(),
    session_id    text          NOT NULL,
    question      text          NOT NULL,
    tool_calls    jsonb         NOT NULL,
    answer        text          NOT NULL,
    input_tokens  integer       NOT NULL,
    output_tokens integer       NOT NULL,
    cost_usd      numeric(8, 5) NOT NULL
);

CREATE INDEX IF NOT EXISTS agent_runs_asked_at_idx ON agent_runs (asked_at);

CREATE TABLE IF NOT EXISTS weather (
    date          date PRIMARY KEY,
    cloud_cover   integer,
    temperature_c numeric(5, 2),
    wind_speed    integer,
    weather_code  integer
);
