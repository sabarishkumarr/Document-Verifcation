-- ==============================================================================
-- VeriDoc AI 2.0 — Migration 002: Universal Platform Schema Extension
-- ==============================================================================
-- Safe, non-destructive migration extending PostgreSQL database 'veridoc_db'
-- to support dynamic document classification, arbitrary attribute schemas,
-- normalized attribute storage with bounding boxes, asynchronous processing jobs,
-- and machine-to-machine API authentication.
--
-- Preserves all existing tables (applicants, documents, audit_reviews, ai_usage_logs)
-- and historical data with zero downtime.
-- ==============================================================================

SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;

-- 1. Document Type Definitions Catalog
CREATE TABLE IF NOT EXISTS document_type_definitions (
    id SERIAL PRIMARY KEY,
    type_key VARCHAR(100) UNIQUE NOT NULL,
    display_name VARCHAR(255) NOT NULL,
    category VARCHAR(100) DEFAULT 'general',
    description TEXT,
    is_system BOOLEAN DEFAULT FALSE,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_doc_type_key ON document_type_definitions(type_key);
CREATE INDEX IF NOT EXISTS idx_doc_type_category ON document_type_definitions(category);

-- Pre-seed System KYC Types + Common Business Document Types
INSERT INTO document_type_definitions (type_key, display_name, category, description, is_system, is_active)
VALUES
    ('pan', 'Permanent Account Number Card', 'identity', 'Income Tax Department PAN Identity Card', TRUE, TRUE),
    ('aadhaar', 'Aadhaar Card', 'identity', 'Unique Identification Authority of India (UIDAI)', TRUE, TRUE),
    ('passport', 'Indian Passport', 'identity', 'Republic of India Travel & Identity Passport', TRUE, TRUE),
    ('voter_id', 'Elector Photo Identity Card', 'identity', 'Election Commission of India Voter ID', TRUE, TRUE),
    ('driving_licence', 'Motor Driving Licence', 'identity', 'State Transport Department Driving Licence', TRUE, TRUE),
    ('salary_slip', 'Salary Certificate / Payslip', 'financial', 'Monthly corporate employee payslip and earnings statement', FALSE, TRUE),
    ('bank_statement', 'Bank Account Statement', 'financial', 'Official bank transaction ledger and account summary', FALSE, TRUE),
    ('commercial_invoice', 'Commercial / Tax Invoice', 'billing', 'Itemized billing invoice with GSTIN and payment breakdown', FALSE, TRUE),
    ('tax_form_16', 'Form 16 Tax Certificate', 'tax', 'Employer certificate of tax deducted at source (TDS)', FALSE, TRUE),
    ('utility_bill', 'Utility / Electricity / Water Bill', 'utility', 'Recurring utility billing receipt for address verification', FALSE, TRUE),
    ('unknown', 'Unclassified Document', 'general', 'Novel or unclassified document type requiring identification', TRUE, TRUE)
ON CONFLICT (type_key) DO UPDATE 
SET display_name = EXCLUDED.display_name,
    category = EXCLUDED.category,
    description = EXCLUDED.description;


-- 2. Document Extraction Schemas & Learned Templates
CREATE TABLE IF NOT EXISTS document_schemas (
    id SERIAL PRIMARY KEY,
    document_type_id INTEGER REFERENCES document_type_definitions(id) ON DELETE CASCADE,
    version INTEGER DEFAULT 1,
    schema_name VARCHAR(255) NOT NULL,
    attribute_definitions JSONB NOT NULL DEFAULT '[]'::jsonb,
    spatial_templates JSONB DEFAULT '{}'::jsonb,
    sample_count INTEGER DEFAULT 0,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_schema_type ON document_schemas(document_type_id);
CREATE INDEX IF NOT EXISTS idx_schema_active ON document_schemas(is_active);


-- 3. Normalized Dynamic Attributes with Spatial Bounding Boxes & Provenance
CREATE TABLE IF NOT EXISTS document_extracted_attributes (
    id SERIAL PRIMARY KEY,
    document_id VARCHAR(255) REFERENCES documents(id) ON DELETE CASCADE,
    attribute_key VARCHAR(100) NOT NULL,
    attribute_label VARCHAR(255),
    data_type VARCHAR(50) DEFAULT 'string',
    raw_value TEXT,
    normalized_value TEXT,
    confidence REAL DEFAULT 1.0,
    source_type VARCHAR(50) DEFAULT 'standard',
    extraction_method VARCHAR(50) DEFAULT 'ai_gemini',
    page_number INTEGER DEFAULT 1,
    bounding_box JSONB,
    is_verified BOOLEAN DEFAULT FALSE,
    is_deleted BOOLEAN DEFAULT FALSE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_attr_doc ON document_extracted_attributes(document_id);
CREATE INDEX IF NOT EXISTS idx_attr_key ON document_extracted_attributes(attribute_key);
CREATE INDEX IF NOT EXISTS idx_attr_verified ON document_extracted_attributes(is_verified);


-- 4. Asynchronous Processing Jobs Queue & State Machine
CREATE TABLE IF NOT EXISTS processing_jobs (
    id VARCHAR(255) PRIMARY KEY,
    document_id VARCHAR(255) REFERENCES documents(id) ON DELETE CASCADE,
    status VARCHAR(50) DEFAULT 'queued',
    progress INTEGER DEFAULT 0,
    stage VARCHAR(100) DEFAULT 'intake',
    attempt_count INTEGER DEFAULT 0,
    max_retries INTEGER DEFAULT 3,
    error_message TEXT,
    result_summary JSONB,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    started_at TIMESTAMP WITH TIME ZONE,
    completed_at TIMESTAMP WITH TIME ZONE
);

CREATE INDEX IF NOT EXISTS idx_jobs_status ON processing_jobs(status);
CREATE INDEX IF NOT EXISTS idx_jobs_doc ON processing_jobs(document_id);


-- 5. API Keys for External Machine-to-Machine Authentication
CREATE TABLE IF NOT EXISTS api_keys (
    id SERIAL PRIMARY KEY,
    key_hash VARCHAR(128) UNIQUE NOT NULL,
    key_prefix VARCHAR(20) NOT NULL,
    name VARCHAR(255) NOT NULL,
    permissions JSONB DEFAULT '["read", "write"]'::jsonb,
    rate_limit_rpm INTEGER DEFAULT 60,
    status VARCHAR(50) DEFAULT 'active',
    last_used_at TIMESTAMP WITH TIME ZONE,
    expires_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_api_keys_hash ON api_keys(key_hash);
CREATE INDEX IF NOT EXISTS idx_api_keys_status ON api_keys(status);


-- 6. Webhook Subscriptions for Event Dispatching
CREATE TABLE IF NOT EXISTS webhook_subscriptions (
    id SERIAL PRIMARY KEY,
    target_url VARCHAR(1024) NOT NULL,
    secret_token VARCHAR(255) NOT NULL,
    subscribed_events JSONB DEFAULT '["document.completed", "document.failed"]'::jsonb,
    is_active BOOLEAN DEFAULT TRUE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);
