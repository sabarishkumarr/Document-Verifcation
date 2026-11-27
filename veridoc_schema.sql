-- ==============================================================================
-- VeriDoc AI — Production Database Initialization Schema
-- ==============================================================================
-- Target Engine: PostgreSQL 14+ (Compatible with PostgreSQL 14, 15, 16, 17, 18, 19)
-- Database Name: veridoc_db (or user-configured target database)
-- Encoding: UTF-8
--
-- Description:
-- Standalone database initialization DDL script generated directly from the
-- live VeriDoc AI PostgreSQL schema. This script sets up all required tables,
-- column definitions, primary keys, foreign-key relationships, default values,
-- constraints, sequences, and performance indexes.
--
-- Execution:
--   psql -U postgres -d veridoc_db -f veridoc_schema.sql
--   OR execute directly in pgAdmin 4 Query Tool against target database.
-- ==============================================================================

SET statement_timeout = 0;
SET lock_timeout = 0;
SET client_encoding = 'UTF8';
SET standard_conforming_strings = on;
SET check_function_bodies = false;
SET client_min_messages = warning;
SET row_security = off;

-- ==============================================================================
-- 1. Applicants Table
-- ==============================================================================
-- Purpose:
-- Central identity registry representing individual KYC applicants / customers.
-- Stores applicant contact information, cumulative identity consistency score,
-- overall compliance risk tier, and current verification status.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS applicants (
    id VARCHAR(255) PRIMARY KEY,
    name VARCHAR(255),
    status VARCHAR(50) DEFAULT 'pending',
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    email VARCHAR(255),
    phone VARCHAR(50),
    consistency_score REAL DEFAULT 0.0,
    risk_level VARCHAR(50) DEFAULT 'low',
    notes TEXT
);

COMMENT ON TABLE applicants IS 'Master registry of applicants undergoing KYC identity verification';
COMMENT ON COLUMN applicants.id IS 'Unique applicant identifier (e.g. APPL-2026-XXXX or custom external customer ID)';
COMMENT ON COLUMN applicants.name IS 'Primary legal full name detected across verified documents';
COMMENT ON COLUMN applicants.status IS 'Applicant compliance status: pending, verified, requires_attention, or rejected';
COMMENT ON COLUMN applicants.created_at IS 'Record creation timestamp with timezone';
COMMENT ON COLUMN applicants.email IS 'Optional applicant contact email address';
COMMENT ON COLUMN applicants.phone IS 'Optional applicant contact phone number';
COMMENT ON COLUMN applicants.consistency_score IS 'Cross-document field match score (0.0 to 100.0%)';
COMMENT ON COLUMN applicants.risk_level IS 'Calculated compliance risk classification: low, medium, or high';
COMMENT ON COLUMN applicants.notes IS 'Internal compliance notes or case summary';


-- ==============================================================================
-- 2. Documents Table
-- ==============================================================================
-- Purpose:
-- Stores metadata, ingestion state, classification results, extracted fields,
-- format validation outcomes, and human review decisions for each submitted
-- identity document (PAN, Aadhaar, Passport, Voter ID, Driving Licence).
-- ==============================================================================

CREATE TABLE IF NOT EXISTS documents (
    id VARCHAR(255) PRIMARY KEY,
    applicant_id VARCHAR(255) REFERENCES applicants(id) ON DELETE SET NULL,
    original_filename VARCHAR(255) NOT NULL,
    stored_filename VARCHAR(255) NOT NULL,
    document_type VARCHAR(100) DEFAULT 'unknown',
    file_size BIGINT,
    file_hash VARCHAR(128),
    mime_type VARCHAR(100),
    processing_status VARCHAR(50) DEFAULT 'pending',
    review_status VARCHAR(50) DEFAULT 'pending',
    upload_timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    extracted_text TEXT,
    extraction_metadata TEXT,
    classified_type VARCHAR(100) DEFAULT 'unknown',
    classification_confidence REAL DEFAULT 0.0,
    extracted_fields TEXT,
    validation_results TEXT,
    reviewed_by VARCHAR(255),
    reviewed_at TIMESTAMP WITH TIME ZONE,
    review_notes TEXT
);

COMMENT ON TABLE documents IS 'Uploaded identity documents, extraction payloads, validation results, and review statuses';
COMMENT ON COLUMN documents.id IS 'Unique document identifier (UUID)';
COMMENT ON COLUMN documents.applicant_id IS 'Foreign key referencing applicants(id); nullable for initial unassigned intake';
COMMENT ON COLUMN documents.original_filename IS 'Original upload filename as submitted by user/client';
COMMENT ON COLUMN documents.stored_filename IS 'Sanitized on-disk filename stored under storage/uploads/';
COMMENT ON COLUMN documents.document_type IS 'Document type category: pan, aadhaar, passport, voter_id, driving_licence, or unknown';
COMMENT ON COLUMN documents.file_size IS 'File size in bytes';
COMMENT ON COLUMN documents.file_hash IS 'SHA-256 content checksum for deduplication and integrity';
COMMENT ON COLUMN documents.mime_type IS 'Detected MIME type (application/pdf, image/jpeg, image/png)';
COMMENT ON COLUMN documents.processing_status IS 'Extraction pipeline status: pending, processing, completed, or failed';
COMMENT ON COLUMN documents.review_status IS 'Human officer review status: pending, approved, rejected, or resubmission_requested';
COMMENT ON COLUMN documents.upload_timestamp IS 'Intake timestamp with timezone';
COMMENT ON COLUMN documents.extracted_text IS 'Raw text extracted via PyMuPDF or Tesseract OCR';
COMMENT ON COLUMN documents.extraction_metadata IS 'JSON metadata of extraction execution (engine, DPI, pages, latency)';
COMMENT ON COLUMN documents.classified_type IS 'Model/Rule determined classification category';
COMMENT ON COLUMN documents.classification_confidence IS 'Classification confidence score between 0.0 and 1.0';
COMMENT ON COLUMN documents.extracted_fields IS 'Structured JSON payload of extracted identity fields (name, DOB, ID number, etc.)';
COMMENT ON COLUMN documents.validation_results IS 'Structured JSON payload of deterministic regex, checksum, and expiry checks';
COMMENT ON COLUMN documents.reviewed_by IS 'Name or identifier of the compliance officer who conducted manual review';
COMMENT ON COLUMN documents.reviewed_at IS 'Timestamp of compliance review decision';
COMMENT ON COLUMN documents.review_notes IS 'Officer comments explaining approval, rejection, or resubmission request';

-- Performance Indexes for Documents Table
CREATE INDEX IF NOT EXISTS idx_documents_applicant ON documents(applicant_id);
CREATE INDEX IF NOT EXISTS idx_documents_status ON documents(processing_status);
CREATE INDEX IF NOT EXISTS idx_documents_review ON documents(review_status);
CREATE INDEX IF NOT EXISTS idx_documents_hash ON documents(file_hash);


-- ==============================================================================
-- 3. Audit Review Ledger Table
-- ==============================================================================
-- Purpose:
-- Immutable audit log recording every human officer verification decision,
-- field correction/override, status transition, and timestamped review notes.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS audit_reviews (
    id SERIAL PRIMARY KEY,
    document_id VARCHAR(255) REFERENCES documents(id) ON DELETE CASCADE,
    applicant_id VARCHAR(255),
    officer_name VARCHAR(255) DEFAULT 'Review Officer',
    decision VARCHAR(50) NOT NULL,
    edited_fields TEXT,
    notes TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP
);

COMMENT ON TABLE audit_reviews IS 'Immutable audit ledger of compliance review decisions and manual field corrections';
COMMENT ON COLUMN audit_reviews.id IS 'Auto-incrementing serial audit log entry ID';
COMMENT ON COLUMN audit_reviews.document_id IS 'Foreign key referencing documents(id)';
COMMENT ON COLUMN audit_reviews.applicant_id IS 'Associated applicant identifier';
COMMENT ON COLUMN audit_reviews.officer_name IS 'Name of the compliance officer submitting the action';
COMMENT ON COLUMN audit_reviews.decision IS 'Decision code: approved, rejected, manual_review, or resubmission_requested';
COMMENT ON COLUMN audit_reviews.edited_fields IS 'JSON dictionary of field corrections made during review';
COMMENT ON COLUMN audit_reviews.notes IS 'Compliance commentary justifying the verification action';
COMMENT ON COLUMN audit_reviews.created_at IS 'Audit timestamp with timezone';

-- Performance Index for Audit Reviews Table
CREATE INDEX IF NOT EXISTS idx_audit_doc ON audit_reviews(document_id);


-- ==============================================================================
-- 4. AI API Usage & Cost Tracking Table
-- ==============================================================================
-- Purpose:
-- Detailed financial and operational tracking of every external AI API call
-- (Google Gemini multimodal extraction or fallback REST calls). Records input/output
-- token counts, latency, billing estimates, model ID, and request status.
-- ==============================================================================

CREATE TABLE IF NOT EXISTS ai_usage_logs (
    id SERIAL PRIMARY KEY,
    document_id VARCHAR(255) REFERENCES documents(id) ON DELETE CASCADE,
    applicant_id VARCHAR(255) REFERENCES applicants(id) ON DELETE SET NULL,
    provider VARCHAR(50) NOT NULL,
    model VARCHAR(100) NOT NULL,
    prompt_tokens INTEGER,
    candidate_tokens INTEGER,
    total_tokens INTEGER,
    latency_ms INTEGER,
    status VARCHAR(50) NOT NULL,
    estimated_cost REAL,
    error_message TEXT,
    created_at TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    request_type VARCHAR(100) DEFAULT 'multimodal_extraction',
    channel VARCHAR(50) DEFAULT 'sdk'
);

COMMENT ON TABLE ai_usage_logs IS 'Operational log of AI API calls, token counts, latency, and estimated economics';
COMMENT ON COLUMN ai_usage_logs.id IS 'Auto-incrementing serial log record ID';
COMMENT ON COLUMN ai_usage_logs.document_id IS 'Foreign key referencing documents(id) processed by AI';
COMMENT ON COLUMN ai_usage_logs.applicant_id IS 'Foreign key referencing applicants(id)';
COMMENT ON COLUMN ai_usage_logs.provider IS 'AI provider: gemini, openai, or mock';
COMMENT ON COLUMN ai_usage_logs.model IS 'Model ID invoked (e.g. gemini-3.5-flash-lite, gemini-2.5-flash)';
COMMENT ON COLUMN ai_usage_logs.prompt_tokens IS 'Number of input/prompt tokens billed';
COMMENT ON COLUMN ai_usage_logs.candidate_tokens IS 'Number of output/candidate tokens billed';
COMMENT ON COLUMN ai_usage_logs.total_tokens IS 'Total tokens consumed (prompt + candidate)';
COMMENT ON COLUMN ai_usage_logs.latency_ms IS 'Round-trip API request latency in milliseconds';
COMMENT ON COLUMN ai_usage_logs.status IS 'Call status: success or error';
COMMENT ON COLUMN ai_usage_logs.estimated_cost IS 'Calculated estimated cost in USD based on configured billing tier pricing';
COMMENT ON COLUMN ai_usage_logs.error_message IS 'Sanitized error message if the API call failed';
COMMENT ON COLUMN ai_usage_logs.created_at IS 'Call timestamp with timezone';
COMMENT ON COLUMN ai_usage_logs.request_type IS 'Category of request: multimodal_extraction, model_verification, or fallback';
COMMENT ON COLUMN ai_usage_logs.channel IS 'Client communication protocol: sdk or rest';

-- Performance Indexes for AI Usage Table
CREATE INDEX IF NOT EXISTS idx_ai_usage_doc ON ai_usage_logs(document_id);
CREATE INDEX IF NOT EXISTS idx_ai_usage_applicant ON ai_usage_logs(applicant_id);
CREATE INDEX IF NOT EXISTS idx_ai_usage_provider ON ai_usage_logs(provider);
CREATE INDEX IF NOT EXISTS idx_ai_usage_status ON ai_usage_logs(status);

-- ==============================================================================
-- Schema Initialization Complete
-- ==============================================================================
