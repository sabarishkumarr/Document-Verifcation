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

  getDocumentFileUrl: (documentId) => `${API_BASE}/documents/${documentId}/file`,

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
