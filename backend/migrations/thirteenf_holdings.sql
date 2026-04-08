-- 13F holdings: institutional BDC positions from SEC Form 13F-HR
-- Run once in Supabase SQL editor (or via migration tool).
--
-- Unique key: (filer_cik, period_of_report, cusip)
-- Rows with ria_crd populated are matched to our RIA database.
-- Rows with ria_crd = NULL capture the broader institutional buyer universe.

CREATE TABLE IF NOT EXISTS thirteenf_holdings (
    id                      SERIAL PRIMARY KEY,
    filer_cik               TEXT        NOT NULL,
    filer_name              TEXT,
    period_of_report        DATE,                   -- end of quarter, e.g. 2024-12-31
    filed_at                DATE,
    issuer_name             TEXT        NOT NULL,
    cusip                   TEXT,
    ticker                  TEXT,                   -- BDC ticker or name fragment
    value_usd               BIGINT      NOT NULL,   -- position value in whole dollars
    shares                  BIGINT,
    investment_discretion   TEXT,                   -- "SOLE" | "SHARED" | "OTHER"
    ria_crd                 TEXT,                   -- FK to rias.crd_number (nullable)
    created_at              TIMESTAMPTZ DEFAULT NOW(),
    updated_at              TIMESTAMPTZ DEFAULT NOW(),

    CONSTRAINT thirteenf_holdings_unique
        UNIQUE (filer_cik, period_of_report, cusip)
);

-- Index for the advisors.py join on ria_crd
CREATE INDEX IF NOT EXISTS idx_thirteenf_ria_crd ON thirteenf_holdings (ria_crd)
    WHERE ria_crd IS NOT NULL;

-- Index for the /api/thirteenf/holders aggregation
CREATE INDEX IF NOT EXISTS idx_thirteenf_filer ON thirteenf_holdings (filer_cik, period_of_report);

-- Auto-update updated_at
CREATE OR REPLACE FUNCTION update_thirteenf_updated_at()
RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN
    NEW.updated_at = NOW();
    RETURN NEW;
END;
$$;

CREATE TRIGGER thirteenf_updated_at
    BEFORE UPDATE ON thirteenf_holdings
    FOR EACH ROW EXECUTE FUNCTION update_thirteenf_updated_at();
