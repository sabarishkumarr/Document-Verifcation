/**
 * VeriDoc AI - Backend REST API Client
 */

const API_BASE = import.meta.env.VITE_API_URL || 'http://127.0.0.1:5000/api';

async function request(endpoint, options = {}) {
  const url = `${API_BASE}${endpoint}`;
  try {
    const res = await fetch(url, {
      ...options,
      headers: {
        ...(options.headers || {}),
      },
    });
    const data = await res.json();
    if (!res.ok) {
      throw new Error(data.message || data.error || `HTTP error ${res.status}`);
    }
    return data;
  } catch (err) {
    console.error(`API Error on ${endpoint}:`, err);
    throw err;
  }
}

export const api = {
  // Health & Diagnostics
  checkHealth: () => request('/health'),
  checkOcrStatus: () => request('/documents/ocr-status'),
  checkAiStatus: () => request('/documents/ai-status'),

  // Dashboard Statistics
  getDashboardStats: (dataset = 'all') => request(dataset && dataset !== 'all' ? `/dashboard/stats?dataset=${dataset}` : '/dashboard/stats'),
  getReportsSummary: (dataset = 'all') => request(dataset && dataset !== 'all' ? `/reports/summary?dataset=${dataset}` : '/reports/summary'),
  getAiUsage: () => request('/reports/ai-usage'),
  verifyAiModel: () => request('/reports/verify-model'),
  getReportDownloadUrl: (format = 'xlsx', dataset = 'all') => `${API_BASE}/reports/download?format=${format}&dataset=${dataset}`,

  // Document Upload & Processing
  getDocumentTypes: () => request('/documents/types'),
  discoverDocumentType: (formData) => {
    return fetch(`${API_BASE}/documents/discover-type`, {
      method: 'POST',
      body: formData,
    }).then(async (res) => {
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.message || 'Discovery failed');
      }
      return data;
    });
  },
  registerDocumentType: (typeData) =>
    request('/documents/register-type', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(typeData),
    }),

  uploadDocuments: (formData) => {
    return fetch(`${API_BASE}/documents/upload`, {
      method: 'POST',
      body: formData,
    }).then(async (res) => {
      const data = await res.json();
      if (!res.ok && res.status !== 201) {
        throw new Error(data.message || 'Upload failed');
      }
      return data;
    });
  },

  processDocument: (documentId) =>
    request(`/documents/${documentId}/process`, {
      method: 'POST',
    }),

  extractText: (documentId) =>
    request(`/documents/${documentId}/extract`, {
      method: 'POST',
    }),

  getDocumentText: (documentId) => request(`/documents/${documentId}/text`),

  getDocumentDetails: (documentId) => request(`/documents/${documentId}`),

  getDocumentFileUrl: (documentId, token = null) =>
    token ? `${API_BASE}/documents/${documentId}/file?token=${encodeURIComponent(token)}` : `${API_BASE}/documents/${documentId}/file`,

  // VeriDoc AI 2.0: Interactive Visual Workspace & Attributes
  generateDocumentPreviewToken: (documentId, officerName = 'Arjun Mehta') =>
    request(`/documents/${documentId}/preview-token`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ officer_name: officerName }),
    }),
  getDocumentPreviewUrl: (documentId, page = 1, token = null) =>
    token
      ? `${API_BASE}/documents/${documentId}/preview?page=${page}&token=${encodeURIComponent(token)}`
      : `${API_BASE}/documents/${documentId}/preview?page=${page}`,
  getDocumentPagesInfo: (documentId) => request(`/documents/${documentId}/pages/info`),
  getDocumentAttributes: (documentId) => request(`/documents/${documentId}/attributes`),
  addCustomAttribute: (documentId, attrData) =>
    request(`/documents/${documentId}/attributes`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(attrData),
    }),
  deleteCustomAttribute: (documentId, attributeId) =>
    request(`/documents/${documentId}/attributes/${attributeId}`, {
      method: 'DELETE',
    }),
  marqueeExtractText: (documentId, bbox, pageNumber = 1) =>
    request(`/documents/${documentId}/marquee-extract`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ bbox, page_number: pageNumber }),
    }),

  listDocuments: (params = {}) => {
    const cleanParams = new URLSearchParams();
    Object.entries(params).forEach(([k, v]) => {
      if (v !== undefined && v !== null && v !== '' && v !== 'all') {
        cleanParams.append(k, v);
      }
    });
    const query = cleanParams.toString();
    return request(query ? `/documents?${query}` : '/documents');
  },

  // Verification Queue
  getVerificationQueue: (status = 'pending') =>
    request(`/documents/queue?status=${status}`),

  getDocumentHistory: (documentId) => request(`/documents/${documentId}/history`),

  submitReview: (documentId, reviewData) =>
    request(`/documents/${documentId}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(reviewData),
    }),

  assignDocument: (documentId, applicantId) =>
    request(`/documents/${documentId}/assign`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ applicant_id: applicantId }),
    }),

  // Applicants
  getApplicants: (dataset = 'all', status = 'all') => {
    const params = new URLSearchParams();
    if (dataset && dataset !== 'all') params.append('dataset', dataset);
    if (status && status !== 'all') params.append('status', status);
    const qs = params.toString();
    return request(qs ? `/applicants?${qs}` : '/applicants');
  },

  getApplicantProfile: (applicantId) => request(`/applicants/${applicantId}`),

  submitApplicantReview: (applicantId, reviewData) =>
    request(`/applicants/${applicantId}/review`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(reviewData),
    }),

  getApplicantComparisonExportUrl: (applicantId, format = 'xlsx') =>
    `${API_BASE}/applicants/${applicantId}/comparison/export?format=${format}`,

  updateApplicantProfile: (applicantId, applicantData) =>
    request(`/applicants/${applicantId}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(applicantData),
    }),

  createApplicant: (applicantData) =>
    request('/applicants', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(applicantData),
    }),

  // Global Search
  search: (query) => request(`/search?q=${encodeURIComponent(query)}`),

  // Document Repository & Dynamic Schemas (Milestone 1)
  getRepositoryStats: () => request('/repository/stats'),
  getRepositoryTypes: (params = {}) => {
    const q = new URLSearchParams();
    if (params.category) q.append('category', params.category);
    if (params.source_origin) q.append('source_origin', params.source_origin);
    if (params.search) q.append('search', params.search);
    if (params.active_only) q.append('active_only', params.active_only);
    const qs = q.toString();
    return request(`/repository/types${qs ? `?${qs}` : ''}`);
  },
  createDocumentType: (typeData) =>
    request('/repository/types', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(typeData),
    }),
  getDocumentTypeDetails: (idOrKey) => request(`/repository/types/${encodeURIComponent(idOrKey)}`),
  getDocumentTypeSample: (idOrKey) => request(`/repository/types/${encodeURIComponent(idOrKey)}/sample`),
  uploadDocumentTypeSample: (idOrKey, file) => {
    const formData = new FormData();
    formData.append('file', file);
    return fetch(`${API_BASE}/repository/types/${encodeURIComponent(idOrKey)}/sample`, {
      method: 'POST',
      body: formData,
    }).then(async (res) => {
      const data = await res.json();
      if (!res.ok) {
        throw new Error(data.message || 'Sample upload failed');
      }
      return data;
    });
  },
  updateDocumentType: (idOrKey, updateData) =>
    request(`/repository/types/${encodeURIComponent(idOrKey)}`, {
      method: 'PUT',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(updateData),
    }),
  publishDocumentSchema: (idOrKey, schemaData) =>
    request(`/repository/types/${encodeURIComponent(idOrKey)}/schemas`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(schemaData),
    }),
  rollbackDocumentSchema: (idOrKey, targetVersion) =>
    request(`/repository/types/${encodeURIComponent(idOrKey)}/rollback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_version: targetVersion }),
    }),
  discoverRepositoryAttributes: (formData) =>
    fetch(`${API_BASE}/repository/discover-attributes`, {
      method: 'POST',
      body: formData,
    }).then(async (res) => {
      const data = await res.json();
      if (!res.ok) throw new Error(data.message || 'Discovery failed');
      return data;
    }),

  // Document Mapping & Triangulation (Milestone 3)
  getApplicantTriangulation: (applicantId) => request(`/applicants/${applicantId}/triangulation`),
  runApplicantTriangulation: (applicantId) =>
    request(`/applicants/${applicantId}/triangulation`, {
      method: 'POST',
    }),
  saveApplicantTriangulation: (applicantId, data) =>
    request(`/applicants/${applicantId}/triangulation/resolve`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(data),
    }),

  // Triangulation Comparison Rules (VeriDoc AI 2.0)
  getTriangulationCombinations: () => request('/triangulation/combinations'),
  getCombinationRules: (combinationKey) =>
    request(`/triangulation/combinations/${encodeURIComponent(combinationKey)}/rules`),
  discoverCombinationRules: (combinationKey, documentTypes = null) =>
    request(`/triangulation/combinations/${encodeURIComponent(combinationKey)}/discover`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ document_types: documentTypes }),
    }),
  saveCombinationRules: (combinationKey, payload) =>
    request(`/triangulation/combinations/${encodeURIComponent(combinationKey)}/rules`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(payload),
    }),
  getCombinationVersions: (combinationKey) =>
    request(`/triangulation/combinations/${encodeURIComponent(combinationKey)}/versions`),
  rollbackCombinationVersion: (combinationKey, targetVersion) =>
    request(`/triangulation/combinations/${encodeURIComponent(combinationKey)}/rollback`, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ target_version: targetVersion }),
    }),

  // Testing & Evaluation Module (Milestone 3)
  getBenchmarkRuns: () => request('/evaluation/runs'),
  runBenchmarkEvaluation: (params = {}) =>
    request('/evaluation/benchmark', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(params),
    }),

  // Demonstration Dataset
  seedDemo: (force = false) =>
    request(`/demo/seed?force=${force}`, {
      method: 'POST',
    }),

  resetDemo: () =>
    request('/demo/reset', {
      method: 'POST',
    }),
};
