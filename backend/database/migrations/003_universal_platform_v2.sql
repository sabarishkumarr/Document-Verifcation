-- ==============================================================================
-- VeriDoc AI 2.0 — Migration 003: Document Repository, Triangulation & Benchmarking
-- ==============================================================================
-- Safe, non-destructive migration extending PostgreSQL database 'veridoc_db'
-- to support:
-- 1. Document Repository origin tags & metadata in document_type_definitions
-- 2. Applicant Document Triangulation / Cross-Document Mapping
-- 3. Synthetic & Benchmark Test Run Tracking
-- 4. Per-page AI usage & cost tracking fields in ai_usage_logs
--
-- Preserves all existing tables and historical data with zero downtime.
-- ==============================================================================

SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;

-- 1. Extend document_type_definitions
ALTER TABLE document_type_definitions 
ADD COLUMN IF NOT EXISTS source_origin VARCHAR(50) DEFAULT 'system',
ADD COLUMN IF NOT EXISTS icon VARCHAR(50) DEFAULT 'file',
ADD COLUMN IF NOT EXISTS tags JSONB DEFAULT '[]'::jsonb,
ADD COLUMN IF NOT EXISTS updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP;

-- Update existing system KYC types
UPDATE document_type_definitions 
SET source_origin = 'system', icon = 'id-card', tags = '["identity", "kyc", "government"]'::jsonb
WHERE type_key IN ('pan', 'aadhaar', 'passport', 'voter_id', 'driving_licence');

UPDATE document_type_definitions 
SET source_origin = 'system', icon = 'file-text', tags = '["financial", "commercial", "tax"]'::jsonb
WHERE type_key IN ('salary_slip', 'bank_statement', 'commercial_invoice', 'tax_form_16', 'utility_bill');

UPDATE document_type_definitions 
SET source_origin = 'ai_discovered'
WHERE type_key NOT IN ('pan', 'aadhaar', 'passport', 'voter_id', 'driving_licence', 'salary_slip', 'bank_statement', 'commercial_invoice', 'tax_form_16', 'utility_bill', 'unknown');


-- 2. Applicant Document Triangulation / Cross-Document Mapping Table
CREATE TABLE IF NOT EXISTS applicant_triangulations (
    id SERIAL PRIMARY KEY,
    applicant_id VARCHAR(255) REFERENCES applicants(id) ON DELETE CASCADE,
    triangulation_status VARCHAR(50) DEFAULT 'pending',
    consistency_score REAL DEFAULT 0.0,
    mapped_attributes JSONB DEFAULT '[]'::jsonb,
    conflicts_detected JSONB DEFAULT '[]'::jsonb,
    evidence_summary JSONB DEFAULT '{}'::jsonb,
    reviewed_by VARCHAR(255),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    updated_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    CONSTRAINT uq_applicant_triangulation UNIQUE (applicant_id)
);

CREATE INDEX IF NOT EXISTS idx_triang_applicant ON applicant_triangulations(applicant_id);
CREATE INDEX IF NOT EXISTS idx_triang_status ON applicant_triangulations(triangulation_status);


-- 3. Testing Benchmark Runs Table
CREATE TABLE IF NOT EXISTS benchmark_runs (
    id SERIAL PRIMARY KEY,
    test_run_name VARCHAR(255) NOT NULL,
    dataset_name VARCHAR(255) NOT NULL,
    pipeline_mode VARCHAR(50) DEFAULT 'hybrid',
    model_name VARCHAR(100),
    document_count INTEGER DEFAULT 0,
    classification_accuracy REAL,
    precision_score REAL,
    recall_score REAL,
    f1_score REAL,
    mean_cer REAL,
    false_acceptance_rate REAL,
    false_rejection_rate REAL,
    avg_latency_ms INTEGER,
    total_tokens INTEGER,
    total_cost REAL,
    per_page_cost REAL,
    results_summary JSONB DEFAULT '{}'::jsonb,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_benchmark_dataset ON benchmark_runs(dataset_name);
CREATE INDEX IF NOT EXISTS idx_benchmark_mode ON benchmark_runs(pipeline_mode);


-- 4. Extend ai_usage_logs for Per-Page & Modality Transparency
ALTER TABLE ai_usage_logs
ADD COLUMN IF NOT EXISTS page_number INTEGER DEFAULT 1,
ADD COLUMN IF NOT EXISTS input_modality VARCHAR(50) DEFAULT 'multimodal',
ADD COLUMN IF NOT EXISTS transmitted_image_bytes BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS transmitted_text BOOLEAN DEFAULT FALSE,
ADD COLUMN IF NOT EXISTS per_page_estimated_cost REAL,
ADD COLUMN IF NOT EXISTS pricing_version VARCHAR(50) DEFAULT 'gemini-3.5-flash-lite-2026-v1';
