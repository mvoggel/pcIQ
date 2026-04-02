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
    canonical_name  TEXT NOT NULL UNIQUE,
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
    private_fund_aum    NUMERIC,                    -- AUM allocated to private funds ($)
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

CREATE INDEX IF NOT EXISTS rias_firm_name_idx         ON rias (firm_name);
CREATE INDEX IF NOT EXISTS rias_state_idx             ON rias (state);
CREATE INDEX IF NOT EXISTS rias_aum_idx               ON rias (aum DESC);
CREATE INDEX IF NOT EXISTS rias_private_fund_aum_idx  ON rias (private_fund_aum DESC);

-- Migration: add private_fund_aum if upgrading from an earlier schema version
-- ALTER TABLE rias ADD COLUMN IF NOT EXISTS private_fund_aum NUMERIC;


-- -----------------------------------------------------------------------
-- fund_platforms
-- Links a Form D filing to the broker-dealers / platforms distributing it.
-- Sourced from Form D salesCompensationList — the direct distribution signal.
-- "Blue Owl Fund IV is being sold via iCapital in NY, CA, TX."
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS fund_platforms (
    id              BIGSERIAL PRIMARY KEY,
    filing_id       BIGINT NOT NULL REFERENCES form_d_filings(id) ON DELETE CASCADE,
    platform_name   TEXT NOT NULL,
    crd_number      TEXT,
    is_known_platform BOOLEAN DEFAULT FALSE,
    states          TEXT[],          -- 2-letter state codes where soliciting
    all_states      BOOLEAN DEFAULT FALSE,
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (filing_id, platform_name)
);

CREATE INDEX IF NOT EXISTS fund_platforms_filing_idx   ON fund_platforms (filing_id);
CREATE INDEX IF NOT EXISTS fund_platforms_name_idx     ON fund_platforms (platform_name);
CREATE INDEX IF NOT EXISTS fund_platforms_known_idx    ON fund_platforms (is_known_platform);


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
-- adv_enrichment
-- Cache of Form ADV data keyed by CRD number.
-- ADV PDFs take 4-8s to download + parse; this makes the fund modal instant.
-- TTL: 30 days (ADV data is filed annually, changes slowly).
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS adv_enrichment (
    crd                         TEXT PRIMARY KEY,
    firm_name                   TEXT,
    total_aum                   NUMERIC,
    discretionary_aum           NUMERIC,
    total_clients               INT,
    total_employees             INT,
    investment_advisory_employees INT,
    client_types                JSONB,   -- array of {label, clients, aum}
    fetched_at                  TIMESTAMPTZ DEFAULT NOW()
);


-- -----------------------------------------------------------------------
-- ria_platforms
-- Maps RIAs to the alternative investment platforms they are registered on.
-- Source: iCapital advisor directory, CAIS partner list, manual CSV import.
-- This is the "confirmed linkage" that makes allocator inference defensible:
--   Fund Y is on iCapital (fund_platforms)  +
--   RIA X is an iCapital partner (ria_platforms)  +
--   RIA X is in territory  →  high-confidence probable buyer
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ria_platforms (
    id              BIGSERIAL PRIMARY KEY,
    crd_number      TEXT NOT NULL,
    platform_name   TEXT NOT NULL,           -- 'iCapital', 'CAIS', 'Orion', etc.
    source          TEXT DEFAULT 'scrape',   -- 'scrape', 'csv', 'manual'
    created_at      TIMESTAMPTZ DEFAULT NOW(),
    UNIQUE (crd_number, platform_name)
);

CREATE INDEX IF NOT EXISTS ria_platforms_crd_idx      ON ria_platforms (crd_number);
CREATE INDEX IF NOT EXISTS ria_platforms_platform_idx ON ria_platforms (platform_name);


-- -----------------------------------------------------------------------
-- feeder_funds
-- Access vehicles / feeder funds that package underlying strategies.
-- Sourced from EDGAR Form D filings where the entity name contains a
-- known platform keyword (e.g., "iCapital Blue Owl Senior Loan Fund II").
-- Tells us which underlying strategies each platform is actively packaging,
-- how much has flowed, and which states they're targeting.
-- -----------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS feeder_funds (
    id              BIGSERIAL PRIMARY KEY,
    cik             TEXT NOT NULL,
    accession_no    TEXT NOT NULL UNIQUE,
    entity_name     TEXT NOT NULL,           -- raw EDGAR name, e.g. "iCapital Blue Owl SLF II"
    platform_name   TEXT NOT NULL,           -- 'iCapital', 'CAIS', etc.
    underlying_fund TEXT,                    -- stripped name, e.g. "Blue Owl SLF II"
    total_raised    NUMERIC,                 -- total_amount_sold from Form D ($)
    target_raise    NUMERIC,                 -- total_offering_amount ($)
    states          TEXT[],                  -- states listed in Form D
    filed_at        DATE,
    created_at      TIMESTAMPTZ DEFAULT NOW()
);

CREATE INDEX IF NOT EXISTS feeder_funds_platform_idx  ON feeder_funds (platform_name);
CREATE INDEX IF NOT EXISTS feeder_funds_filed_idx     ON feeder_funds (filed_at DESC);
CREATE INDEX IF NOT EXISTS feeder_funds_underlying_idx ON feeder_funds (underlying_fund);


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
