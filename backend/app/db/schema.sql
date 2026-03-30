-- pcIQ — initial schema
-- Run against your Supabase project via the SQL editor or psql.
-- Tables are designed for Phase 1; columns marked TODO will be added in later phases.

-- -----------------------------------------------------------------------
-- entities
-- Resolved, deduplicated fund/firm records.
-- "Blue Owl Capital LLC" and "Blue Owl Capital Inc." → same entity.
-- Populated by entity resolution layer (Phase 1, week 3-4).
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS entities (
    id              BIGSERIAL PRIMARY KEY,
    canonical_name  TEXT NOT NULL,
    cik             TEXT,                        -- SEC CIK, if known
    entity_type     TEXT,                        -- 'fund', 'ria', 'gp', 'platform'
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    updated_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE UNIQUE INDEX IF NOT EXISTS entities_cik_idx ON entities (cik) WHERE cik IS NOT NULL;
CREATE INDEX IF NOT EXISTS entities_name_idx ON entities (canonical_name);


-- -----------------------------------------------------------------------
-- form_d_filings
-- One row per Form D (or D/A amendment) filing from EDGAR.
-- This is the raw signal table — the fact that a filing appeared is the event.
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS form_d_filings (
    id                          BIGSERIAL PRIMARY KEY,
    cik                         TEXT NOT NULL,
    accession_no                TEXT NOT NULL UNIQUE,
    entity_name                 TEXT NOT NULL,          -- raw name from filing
    entity_id                   BIGINT REFERENCES entities(id),  -- resolved entity
    filed_at                    DATE,
    date_of_first_sale          DATE,                   -- THE signal date
    industry_group_type         TEXT,
    investment_fund_type        TEXT,
    total_offering_amount       NUMERIC,
    total_amount_sold           NUMERIC,
    total_investors             INT,
    has_non_accredited          BOOLEAN DEFAULT FALSE,
    is_amendment                BOOLEAN DEFAULT FALSE,
    city                        TEXT,
    state_or_country            TEXT,
    federal_exemptions          TEXT[],                 -- e.g. ['06b']
    raw_xml                     TEXT,                   -- stored for reprocessing
    created_at                  TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS form_d_filed_at_idx       ON form_d_filings (filed_at DESC);
CREATE INDEX IF NOT EXISTS form_d_first_sale_idx     ON form_d_filings (date_of_first_sale DESC);
CREATE INDEX IF NOT EXISTS form_d_fund_type_idx      ON form_d_filings (investment_fund_type);
CREATE INDEX IF NOT EXISTS form_d_state_idx          ON form_d_filings (state_or_country);


-- -----------------------------------------------------------------------
-- rias
-- Registered Investment Advisors, sourced from Form ADV (Phase 1, week 5-6).
-- These are the firms wholesalers call.
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS rias (
    id                  BIGSERIAL PRIMARY KEY,
    crd_number          TEXT UNIQUE,                -- FINRA CRD# — the stable identifier
    cik                 TEXT,
    firm_name           TEXT NOT NULL,
    entity_id           BIGINT REFERENCES entities(id),
    aum                 NUMERIC,                    -- assets under management ($)
    total_accounts      INT,
    num_advisors        INT,
    city                TEXT,
    state               TEXT,
    zip_code            TEXT,
    website             TEXT,
    is_active           BOOLEAN DEFAULT TRUE,
    adv_filed_at        DATE,                       -- date of most recent ADV filing
    created_at          TIMESTAMPTZ DEFAULT NOW(),
    updated_at          TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS rias_firm_name_idx ON rias (firm_name);
CREATE INDEX IF NOT EXISTS rias_state_idx     ON rias (state);
CREATE INDEX IF NOT EXISTS rias_aum_idx       ON rias (aum DESC);


-- -----------------------------------------------------------------------
-- ria_fund_allocations
-- Links an RIA to a Form D filing — i.e., evidence that the RIA
-- allocated capital to this fund. This is the core signal table.
-- Phase 1: derived from sales compensation disclosures in Form D.
-- Phase 2+: enriched from iCapital/CAIS platform data.
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ria_fund_allocations (
    id              BIGSERIAL PRIMARY KEY,
    ria_id          BIGINT NOT NULL REFERENCES rias(id),
    filing_id       BIGINT NOT NULL REFERENCES form_d_filings(id),
    signal_date     DATE NOT NULL,                  -- when we detected this
    source          TEXT DEFAULT 'form_d',           -- 'form_d', 'adv', 'manual'
    confidence      NUMERIC(3,2) DEFAULT 1.0,        -- 0.0–1.0
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (ria_id, filing_id)
);

CREATE INDEX IF NOT EXISTS ria_alloc_ria_idx     ON ria_fund_allocations (ria_id);
CREATE INDEX IF NOT EXISTS ria_alloc_signal_idx  ON ria_fund_allocations (signal_date DESC);


-- -----------------------------------------------------------------------
-- territories
-- Wholesaler territory definitions. Each row = one territory config
-- for one firm. Phase 1: manually seeded. Phase 2: UI-configurable.
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS territories (
    id              BIGSERIAL PRIMARY KEY,
    firm_id         BIGINT,                         -- TODO: references firms table (Phase 2)
    wholesaler_name TEXT,
    states          TEXT[],                         -- e.g. ['AZ', 'NV', 'UT']
    created_at      TIMESTAMPTZ DEFAULT NOW()
);
