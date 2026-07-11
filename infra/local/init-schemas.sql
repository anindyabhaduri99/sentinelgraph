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

-- =====================================================================
-- observability schema + token_usage table
-- Added in Phase 3.6 to answer a real operational question: "how much
-- of our LLM budget have we spent, broken down by role and provider?"
-- The Model Gateway is the single chokepoint every LLM call passes
-- through, so it's the one place that can log real, provider-reported
-- token counts (not estimates) per invocation. This table is the
-- source of truth the gateway's /usage endpoint (built next) will
-- query and aggregate from.
--
-- Kept in its own schema (not ticketing/identity) because this is an
-- observability/cost-governance concern, not business or user data —
-- same "one schema per distinct concern" principle used for
-- ticketing/langgraph_checkpoints/identity in Phase 1.
-- =====================================================================
CREATE SCHEMA IF NOT EXISTS observability;

CREATE TABLE IF NOT EXISTS observability.token_usage (
    id              SERIAL PRIMARY KEY,        -- auto-incrementing row id
    role            VARCHAR(30) NOT NULL,      -- which agent role made this call, e.g. 'planner', 'analyst', 'evaluator'
    provider        VARCHAR(20) NOT NULL,      -- 'anthropic' or 'openai' — which vendor actually served this call
    model           VARCHAR(50) NOT NULL,      -- exact model name used, e.g. 'claude-sonnet-4-5' — lets us track cost changes if a model version changes later
    input_tokens    INTEGER NOT NULL,          -- tokens sent to the model (system prompt + user message), as reported by the provider
    output_tokens   INTEGER NOT NULL,          -- tokens the model generated in its response, as reported by the provider
    cost_usd        NUMERIC(10, 6) NOT NULL,   -- computed dollar cost for this single call, using our own price table (not provider-reported)
    created_at      TIMESTAMP NOT NULL DEFAULT now()  -- when this call happened, so /usage can filter by day/week/etc.
);

-- =====================================================================
-- identity.users
-- Real user accounts for SentinelGraph. Passwords are never stored in
-- plain text — only a bcrypt hash. The role column is what Phase 5's
-- entitlement tables will key off of to determine what each user can
-- access or do.
-- =====================================================================
CREATE TABLE IF NOT EXISTS identity.users (
    user_id         VARCHAR(50) PRIMARY KEY,      -- user-chosen unique login ID
    email           VARCHAR(255) NOT NULL UNIQUE,
    password_hash   VARCHAR(255) NOT NULL,         -- bcrypt hash, never plain text
    role            VARCHAR(30) NOT NULL CHECK (
                        role IN ('admin', 'portfolio_manager', 'ops', 'external_client', 'risk_analyst')
                    ),
    created_at      TIMESTAMP NOT NULL DEFAULT now(),
    updated_at      TIMESTAMP NOT NULL DEFAULT now()
);

-- =====================================================================
-- identity.entitlements
-- The permissions list. Each row answers one question: "can this role
-- do this action on this resource?" The DAL checks this table before
-- allowing any data access — the LLM never sees or decides this.
-- =====================================================================
CREATE TABLE IF NOT EXISTS identity.entitlements (
    id              SERIAL PRIMARY KEY,
    role            VARCHAR(30) NOT NULL,       -- e.g. 'portfolio_manager'
    resource        VARCHAR(50) NOT NULL,       -- e.g. 'ticket', 'portfolio'
    action          VARCHAR(20) NOT NULL,       -- e.g. 'read', 'write'
    UNIQUE (role, resource, action)              -- no duplicate rules
);

-- Seed data: a starting set of real permission rules.
INSERT INTO identity.entitlements (role, resource, action) VALUES
    ('admin', 'ticket', 'read'),
    ('admin', 'ticket', 'write'),
    ('admin', 'portfolio', 'read'),
    ('admin', 'portfolio', 'write'),
    ('portfolio_manager', 'ticket', 'read'),
    ('portfolio_manager', 'portfolio', 'read'),
    ('ops', 'ticket', 'read'),
    ('ops', 'ticket', 'write'),
    ('risk_analyst', 'ticket', 'read'),
    ('risk_analyst', 'portfolio', 'read'),
    ('external_client', 'ticket', 'read'),
    ('external_client', 'portfolio', 'read')
ON CONFLICT (role, resource, action) DO NOTHING;

-- =====================================================================
-- identity.tool_registry
-- Catalog of registered tools/agents. Pure metadata — this table does
-- NOT decide who can use a tool (that's identity.entitlements, checked
-- separately at runtime by Phase 6b's filtering node). This table only
-- answers "what tools exist and what do they do."
-- =====================================================================
CREATE TABLE IF NOT EXISTS identity.tool_registry (
    tool_name       VARCHAR(50) PRIMARY KEY,     -- unique identifier, e.g. 'get_ticket'
    description     TEXT NOT NULL,               -- human/LLM-readable: what this tool does
    input_schema    JSONB NOT NULL,              -- JSON schema describing expected parameters
    resource        VARCHAR(50) NOT NULL,        -- maps to identity.entitlements.resource (e.g. 'ticket')
    owning_domain   VARCHAR(50) NOT NULL,        -- which team/domain registered this, e.g. 'client_servicing'
    enabled         BOOLEAN NOT NULL DEFAULT TRUE, -- lets a tool be disabled without deleting its row
    created_at      TIMESTAMP NOT NULL DEFAULT now()
);

-- Seed data: register our two existing tools for real.
INSERT INTO identity.tool_registry (tool_name, description, input_schema, resource, owning_domain)
VALUES
    (
        'get_ticket',
        'Retrieves a client service ticket by its ticket ID, including subject, status, and SLA breach flag.',
        '{"type": "object", "properties": {"ticket_id": {"type": "string", "description": "The ticket identifier, e.g. TCK-1001"}}, "required": ["ticket_id"]}',
        'ticket',
        'client_servicing'
    ),
    (
        'get_portfolio',
        'Retrieves a client portfolio by client ID, including portfolio value, asset allocation percentages, and risk profile.',
        '{"type": "object", "properties": {"client_id": {"type": "string", "description": "The client identifier, e.g. CLIENT-88213"}}, "required": ["client_id"]}',
        'portfolio',
        'portfolio_management'
    )
ON CONFLICT (tool_name) DO NOTHING;

INSERT INTO identity.entitlements (role, resource, action) VALUES
    ('admin', 'tool_registry', 'write')
ON CONFLICT (role, resource, action) DO NOTHING;