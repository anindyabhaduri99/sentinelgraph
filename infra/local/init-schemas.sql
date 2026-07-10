-- =====================================================================
-- init-schemas.sql
-- Runs automatically the first time the Postgres Docker volume is
-- created (mounted to /docker-entrypoint-initdb.d/ in docker-compose.yml).
-- Establishes the three logically-separated schemas this project uses,
-- plus the real tables and seed data for the "ticketing" schema.
-- =====================================================================

-- ticketing: business data — service tickets and client portfolio records.
-- Owned/queried by the orchestrator service.
CREATE SCHEMA IF NOT EXISTS ticketing;

-- langgraph_checkpoints: reserved for LangGraph's own internal checkpoint
-- tables (agent execution state, used for resume/replay/audit). LangGraph
-- manages the tables inside this schema itself once we wire up a
-- Postgres-backed checkpointer in a later phase — kept isolated from
-- ticketing so a regulatory audit of routing decisions never has to
-- touch unrelated business data.
CREATE SCHEMA IF NOT EXISTS langgraph_checkpoints;

-- identity: user accounts, JWT/session metadata, and entitlement tables.
-- Owned by the governance service (built in a later phase).
CREATE SCHEMA IF NOT EXISTS identity;


-- =====================================================================
-- ticketing.tickets
-- One row per client service ticket — the core object the ISP-style
-- chatbot answers questions about (mirrors a ServiceNow-style ticket).
-- =====================================================================
CREATE TABLE IF NOT EXISTS ticketing.tickets (
    ticket_id       VARCHAR(20) PRIMARY KEY,          -- unique ticket identifier, e.g. "TCK-1001"
    client_id       VARCHAR(20) NOT NULL,              -- which client this ticket belongs to (FK-like link to portfolios.client_id, not enforced yet)
    subject         TEXT NOT NULL,                     -- free-text description of what the client asked/reported
    status          VARCHAR(20) NOT NULL DEFAULT 'open', -- e.g. 'open', 'closed' — current ticket state
    sla_breach      BOOLEAN NOT NULL DEFAULT FALSE,    -- whether this ticket has breached its service-level agreement
    created_at      TIMESTAMP NOT NULL DEFAULT now(),  -- when the ticket was created
    updated_at      TIMESTAMP NOT NULL DEFAULT now()   -- when the ticket was last modified
);

-- =====================================================================
-- ticketing.portfolios
-- One row per client's portfolio snapshot — simulates the kind of data
-- a real "Portfolio API" would return, used by the retriever node to
-- ground responses about a client's holdings and risk profile.
-- =====================================================================
CREATE TABLE IF NOT EXISTS ticketing.portfolios (
    client_id           VARCHAR(20) PRIMARY KEY,        -- unique client identifier, e.g. "CLIENT-88213"
    portfolio_value      NUMERIC(15, 2) NOT NULL,        -- total portfolio value in dollars
    equities_pct         NUMERIC(4, 3) NOT NULL,         -- fraction of portfolio in equities, e.g. 0.620 = 62%
    bonds_pct             NUMERIC(4, 3) NOT NULL,         -- fraction of portfolio in bonds
    cash_pct              NUMERIC(4, 3) NOT NULL,         -- fraction of portfolio held as cash
    risk_profile          VARCHAR(20) NOT NULL            -- client's stated risk tolerance, e.g. 'moderate', 'conservative'
);


-- =====================================================================
-- Seed data — real rows inserted once, at container init time, so the
-- orchestrator has actual data to query from the very first run.
-- ON CONFLICT DO NOTHING makes this safe to re-run without erroring if
-- the rows already exist.
-- =====================================================================
INSERT INTO ticketing.tickets (ticket_id, client_id, subject, status, sla_breach)
VALUES
    ('TCK-1001', 'CLIENT-88213', 'Question about Q3 fund rebalancing', 'open', FALSE),
    ('TCK-1002', 'CLIENT-77410', 'Dispute on trade execution price', 'open', TRUE),
    ('TCK-1003', 'CLIENT-88213', 'Request to increase bond allocation', 'closed', FALSE)
ON CONFLICT (ticket_id) DO NOTHING;

INSERT INTO ticketing.portfolios (client_id, portfolio_value, equities_pct, bonds_pct, cash_pct, risk_profile)
VALUES
    ('CLIENT-88213', 4250000.00, 0.620, 0.300, 0.080, 'moderate'),
    ('CLIENT-77410', 1800000.00, 0.450, 0.450, 0.100, 'conservative')
ON CONFLICT (client_id) DO NOTHING;