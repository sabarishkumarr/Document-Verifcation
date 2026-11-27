import React, { useState, useEffect } from 'react';
import { api } from '../api';

export default function DashboardView({ onNavigateToUpload, onNavigateToQueue }) {
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [typeFilter, setTypeFilter] = useState('all');
  const [statusFilter, setStatusFilter] = useState('all');

  useEffect(() => {
    loadStats();
  }, []);

  const loadStats = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getDashboardStats('live');
      setStats(res.data);
    } catch (err) {
      setError(err.message || 'Failed to load dashboard statistics.');
    } finally {
      setLoading(false);
    }
  };

  const getDocTypeBadge = (type) => {
    const formatted = (type || 'unknown').toUpperCase();
    const colors = {
      PAN: 'bg-blue-50 text-blue-700 border-blue-200',
      AADHAAR: 'bg-emerald-50 text-emerald-700 border-emerald-200',
      PASSPORT: 'bg-purple-50 text-purple-700 border-purple-200',
      VOTER_ID: 'bg-amber-50 text-amber-700 border-amber-200',
      DRIVING_LICENCE: 'bg-indigo-50 text-indigo-700 border-indigo-200',
      UNKNOWN: 'bg-slate-100 text-slate-700 border-slate-200',
    };
    return (
      <span className={`inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold border ${colors[formatted] || colors.UNKNOWN}`}>
        {formatted.replace(/_/g, ' ')}
      </span>
    );
  };

  const getStatusBadge = (status) => {
    const s = (status || 'pending').toLowerCase();
    if (s === 'approved' || s === 'completed' || s === 'verified') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#EDF4EE] text-[#2E5A36] text-[12px] font-medium">
          <span className="w-1.5 h-1.5 rounded-full bg-[#2E5A36]"></span>
          Approved
        </span>
      );
    }
    if (s === 'rejected' || s === 'manual_review' || s === 'failed') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#F9EFEB] text-[#8C3B30] text-[12px] font-medium">
          <span className="w-1.5 h-1.5 rounded-full bg-[#8C3B30]"></span>
          Requires Attention
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#EDF3F8] text-[#3B6282] text-[12px] font-medium">
        <span className="w-1.5 h-1.5 rounded-full bg-[#3B6282]"></span>
        Pending Review
      </span>
    );
  };

  const getIssueSummary = (item) => {
    if (item.validation_results) {
      try {
        const parsed = typeof item.validation_results === 'string'
          ? JSON.parse(item.validation_results)
          : item.validation_results;
        
        if (parsed.flags && parsed.flags.length > 0) {
          return parsed.flags[0];
        }
        if (parsed.checks) {
          const failed = parsed.checks.find(c => c.status === 'fail' || c.status === 'warning');
          if (failed && failed.message) {
            return failed.message;
          }
        }
      } catch (e) {
        // ignore parse error
      }
    }
    if (item.review_status === 'manual_review') {
      return 'Discrepancy flagged / secondary review required';
    }
    if (item.review_status === 'rejected') {
      return 'Rejected by verification officer';
    }
    if (item.review_status === 'resubmission_requested') {
      return 'Resubmission requested due to quality/mismatch';
    }
    return 'Pending verification & identity cross-check';
  };

  const filteredRecent = (stats?.recent_documents || []).filter((doc) => {
    const docType = (doc.classified_type || doc.document_type || '').toLowerCase();
    const docStatus = (doc.review_status || doc.processing_status || '').toLowerCase();

    if (typeFilter !== 'all' && !docType.includes(typeFilter.toLowerCase())) {
      return false;
    }
    if (statusFilter !== 'all') {
      if (statusFilter === 'processed' && docStatus !== 'approved' && docStatus !== 'completed' && docStatus !== 'verified') return false;
      if (statusFilter === 'pending' && docStatus !== 'pending') return false;
      if (statusFilter === 'attention' && docStatus !== 'manual_review' && docStatus !== 'rejected') return false;
    }
    return true;
  });

  return (
    <div className="w-full max-w-7xl mx-auto px-6 lg:px-8 py-8 space-y-10">
      
      {/* 1. Dashboard Header */}
      <header className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-2 border-b border-[#E2E8F0]">
        <div>
          <h1 className="text-[20px] font-bold text-[#0F172A] tracking-tight">
            Overview
          </h1>
          <p className="text-[13px] text-[#64748B] mt-0.5">
            Operational processing summary, verification attention items, and recent documents.
          </p>
        </div>

        <div className="flex items-center gap-3 shrink-0">
          <button
            onClick={loadStats}
            className="inline-flex items-center gap-2 bg-white border border-[#CBD5E1] text-[#334155] px-3.5 py-2 rounded-lg text-[13px] font-semibold hover:bg-slate-50 transition-colors shadow-2xs"
            type="button"
          >
            <span className="material-symbols-outlined text-[17px] text-[#64748B]">refresh</span>
            Refresh
          </button>
          <button
            onClick={onNavigateToUpload}
            className="inline-flex items-center gap-2 bg-[#2563EB] hover:bg-[#1D4ED8] text-white px-4 py-2 rounded-lg text-[13px] font-semibold transition-colors shadow-2xs"
            type="button"
          >
            <span>+</span>
            Upload Documents
          </button>
        </div>
      </header>

      {/* Error state */}
      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-800 text-[13px] flex items-center justify-between">
          <span>{error}</span>
          <button onClick={loadStats} className="font-semibold underline ml-4">Retry</button>
        </div>
      )}

      {/* 2. Key Metrics Cards (4 Clean Cards) */}
      <section aria-label="System Metrics" className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-4">
        {/* Card 1: Total Documents */}
        <div className="bg-white border border-[#E2E8F0] p-5 rounded-lg flex flex-col justify-between h-36 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-[12px] font-bold uppercase tracking-wider text-[#64748B]">Total Documents</span>
            <span className="material-symbols-outlined text-[#64748B] text-[20px]">folder_open</span>
          </div>
          <div>
            <div className="text-[34px] font-bold text-[#0F172A] leading-none tracking-tight">
              {loading ? '...' : (stats?.total_documents ?? 0)}
            </div>
            <div className="text-[12px] text-[#64748B] mt-2">All uploaded identity files</div>
          </div>
        </div>

        {/* Card 2: Processed */}
        <div className="bg-white border border-[#E2E8F0] p-5 rounded-lg flex flex-col justify-between h-36 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-[12px] font-bold uppercase tracking-wider text-[#64748B]">Processed</span>
            <span className="material-symbols-outlined text-[#2E5A36] text-[20px]">check_circle</span>
          </div>
          <div>
            <div className="text-[34px] font-bold text-[#0F172A] leading-none tracking-tight">
              {loading ? '...' : (stats?.processed_count ?? 0)}
            </div>
            <div className="flex items-center gap-1.5 mt-2">
              <span className="w-1.5 h-1.5 rounded-full bg-[#2E5A36]"></span>
              <span className="text-[12px] text-[#64748B]">OCR & extraction completed</span>
            </div>
          </div>
        </div>

        {/* Card 3: Pending Review */}
        <div className="bg-white border border-[#E2E8F0] p-5 rounded-lg flex flex-col justify-between h-36 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-[12px] font-bold uppercase tracking-wider text-[#64748B]">Pending Review</span>
            <span className="material-symbols-outlined text-[#2563EB] text-[20px]">schedule</span>
          </div>
          <div>
            <div className="text-[34px] font-bold text-[#0F172A] leading-none tracking-tight">
              {loading ? '...' : (stats?.pending_review_count ?? 0)}
            </div>
            <div className="flex items-center gap-1.5 mt-2">
              <span className="w-1.5 h-1.5 rounded-full bg-[#2563EB]"></span>
              <span className="text-[12px] text-[#64748B]">Awaiting officer review</span>
            </div>
          </div>
        </div>

        {/* Card 4: Issues Found */}
        <div className="bg-white border border-[#E2E8F0] p-5 rounded-lg flex flex-col justify-between h-36 shadow-xs">
          <div className="flex items-center justify-between">
            <span className="text-[12px] font-bold uppercase tracking-wider text-[#64748B]">Issues Found</span>
            <span className="material-symbols-outlined text-[#8C3B30] text-[20px]">flag</span>
          </div>
          <div>
            <div className="text-[34px] font-bold text-[#8C3B30] leading-none tracking-tight">
              {loading ? '...' : (stats?.issues_count ?? 0)}
            </div>
            <div className="flex items-center gap-1.5 mt-2">
              <span className="w-1.5 h-1.5 rounded-full bg-[#8C3B30]"></span>
              <span className="text-[12px] text-[#64748B]">Format or mismatch flags</span>
            </div>
          </div>
        </div>
      </section>

      {/* 3. Requires Attention Section (One Row Per Applicant) */}
      <section aria-labelledby="attention-heading" className="space-y-4">
        <div className="flex items-center justify-between">
          <div className="flex items-center gap-3">
            <h2 id="attention-heading" className="text-[16px] font-bold text-[#0F172A]">
              Requires attention
            </h2>
            <span className="px-2.5 py-0.5 rounded text-[12px] font-semibold bg-[#F9EFEB] text-[#8C3B30]">
              {(stats?.attention_items || stats?.attention_queue || []).length} applicant{(stats?.attention_items || stats?.attention_queue || []).length !== 1 ? 's' : ''}
            </span>
          </div>
          <button
            onClick={() => onNavigateToQueue()}
            className="text-[13px] font-semibold text-[#2563EB] hover:underline"
          >
            Open Queue →
          </button>
        </div>

        <div className="bg-white border border-[#E2E8F0] rounded-lg overflow-hidden shadow-xs">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-[#F8FAFC] border-b border-[#E2E8F0] text-[#64748B] text-[11px] font-bold uppercase tracking-wider">
                  <th className="py-3 px-5">Applicant</th>
                  <th className="py-3 px-5">Affected Documents</th>
                  <th className="py-3 px-5">Primary Issue / Finding</th>
                  <th className="py-3 px-5">Status</th>
                  <th className="py-3 px-5 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E2E8F0] text-[13px]">
                {loading ? (
                  <tr>
                    <td colSpan="5" className="py-8 text-center text-[#64748B]">
                      Loading attention queue...
                    </td>
                  </tr>
                ) : (!stats?.attention_items && !stats?.attention_queue) || (stats?.attention_items || stats?.attention_queue || []).length === 0 ? (
                  <tr>
                    <td colSpan="5" className="py-8 text-center text-[#64748B]">
                      No applicant discrepancies flagged. All identity dossiers clear.
                    </td>
                  </tr>
                ) : (
                  (stats?.attention_items || stats?.attention_queue || []).slice(0, 8).map((item) => (
                    <tr key={item.id || item.applicant_id} className="hover:bg-[#F8FAFC] transition-colors">
                      <td className="py-3.5 px-5 font-medium text-[#0F172A]">
                        <div className="font-semibold text-[#0F172A]">
                          {item.applicant_name || item.name || <span className="text-amber-800 italic font-medium">Name not detected</span>}
                        </div>
                        {(item.applicant_id || item.id) && (
                          <div className="text-[11px] font-mono text-[#64748B]">#{item.applicant_id || item.id}</div>
                        )}
                      </td>
                      <td className="py-3.5 px-5">
                        <span className="inline-flex items-center px-2.5 py-0.5 rounded bg-slate-100 text-slate-800 text-[12px] font-medium">
                          {item.affected_doc_count || 1} affected document{item.affected_doc_count !== 1 ? 's' : ''}
                        </span>
                      </td>
                      <td className="py-3.5 px-5 max-w-md">
                        <span className={`inline-block px-2.5 py-0.5 rounded text-[11px] font-medium border ${
                          (item.applicant_status === 'rejected' || item.review_status === 'rejected')
                            ? 'bg-red-50 text-red-800 border-red-200'
                            : 'bg-amber-50 text-amber-800 border-amber-200'
                        }`}>
                          {item.main_issue || getIssueSummary(item)}
                        </span>
                      </td>
                      <td className="py-3.5 px-5">
                        {getStatusBadge(item.applicant_status || item.review_status)}
                      </td>
                      <td className="py-3.5 px-5 text-right">
                        <button
                          onClick={() => onNavigateToQueue(item.applicant_id || item.id)}
                          className="text-[#2563EB] hover:text-[#0F172A] font-semibold text-[13px] transition-colors"
                        >
                          Review →
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>

      {/* 4. Recent Documents Section */}
      <section aria-labelledby="recent-heading" className="space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-baseline justify-between gap-4">
          <h2 id="recent-heading" className="text-[16px] font-bold text-[#0F172A]">
            Recent documents
          </h2>

          {/* Filters */}
          <div className="flex flex-wrap items-center gap-2.5">
            <select
              value={typeFilter}
              onChange={(e) => setTypeFilter(e.target.value)}
              className="bg-white border border-[#E2E8F0] text-[13px] text-[#0F172A] px-3 py-1.5 rounded-lg focus:outline-none"
            >
              <option value="all">Document Type: All</option>
              <option value="pan">PAN Card</option>
              <option value="aadhaar">Aadhaar Card</option>
              <option value="passport">Passport</option>
              <option value="voter_id">Voter ID</option>
              <option value="driving_licence">Driving Licence</option>
            </select>

            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-white border border-[#E2E8F0] text-[13px] text-[#0F172A] px-3 py-1.5 rounded-lg focus:outline-none"
            >
              <option value="all">Status: All</option>
              <option value="processed">Processed</option>
              <option value="pending">Pending Review</option>
              <option value="attention">Requires Attention</option>
            </select>
          </div>
        </div>

        <div className="bg-white border border-[#E2E8F0] rounded-lg overflow-hidden shadow-xs">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-[#F8FAFC] border-b border-[#E2E8F0] text-[#64748B] text-[11px] font-bold uppercase tracking-wider">
                  <th className="py-3 px-5">Applicant</th>
                  <th className="py-3 px-5">Document</th>
                  <th className="py-3 px-5">Classified Type</th>
                  <th className="py-3 px-5">Uploaded At</th>
                  <th className="py-3 px-5">Review Status</th>
                  <th className="py-3 px-5 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E2E8F0] text-[13px]">
                {loading ? (
                  <tr>
                    <td colSpan="6" className="py-8 text-center text-[#64748B]">
                      Loading recent documents...
                    </td>
                  </tr>
                ) : filteredRecent.length === 0 ? (
                  <tr>
                    <td colSpan="6" className="py-8 text-center text-[#64748B]">
                      No recent documents found matching criteria.
                    </td>
                  </tr>
                ) : (
                  filteredRecent.map((doc) => (
                    <tr key={doc.id} className="hover:bg-[#F8FAFC] transition-colors">
                      <td className="py-3.5 px-5 font-medium text-[#0F172A]">
                        {doc.applicant_name || <span className="text-amber-800 italic font-medium">Name not detected</span>}
                      </td>
                      <td className="py-3.5 px-5 text-[#64748B] font-mono text-[12px]">
                        {doc.original_filename}
                      </td>
                      <td className="py-3.5 px-5">
                        {getDocTypeBadge(doc.classified_type || doc.document_type)}
                      </td>
                      <td className="py-3.5 px-5 text-[#64748B] text-[12px]">
                        {doc.upload_timestamp ? new Date(doc.upload_timestamp).toLocaleDateString() : 'Recent'}
                      </td>
                      <td className="py-3.5 px-5">
                        {getStatusBadge(doc.review_status)}
                      </td>
                      <td className="py-3.5 px-5 text-right">
                        <button
                          onClick={() => onNavigateToQueue(doc.applicant_id || doc.id)}
                          className="text-[#2563EB] hover:text-[#0F172A] font-semibold text-[13px] transition-colors"
                        >
                          Inspect →
                        </button>
                      </td>
                    </tr>
                  ))
                )}
              </tbody>
            </table>
          </div>
        </div>
      </section>

    </div>
  );
}
