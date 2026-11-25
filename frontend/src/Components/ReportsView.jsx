import React, { useState, useEffect } from 'react';
import { api } from '../api';
import ComparisonMatrix from './ComparisonMatrix';

export default function ReportsView() {
  const [reportSummary, setReportSummary] = useState(null);
  const [loading, setLoading] = useState(true);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');

  // Pagination State for Audit Ledger
  const [currentPage, setCurrentPage] = useState(1);
  const itemsPerPage = 10;

  // Applicant Matrix Details Modal
  const [activeApplicantId, setActiveApplicantId] = useState(null);
  const [applicantProfile, setApplicantProfile] = useState(null);
  const [loadingProfile, setLoadingProfile] = useState(false);

  // Expandable row details state
  const [expandedApplicantIds, setExpandedApplicantIds] = useState(new Set());
  const [showUsageLedger, setShowUsageLedger] = useState(false);

  const toggleExpand = (id) => {
    setExpandedApplicantIds((prev) => {
      const next = new Set(prev);
      if (next.has(id)) {
        next.delete(id);
      } else {
        next.add(id);
      }
      return next;
    });
  };

  useEffect(() => {
    loadReportsData();
    setCurrentPage(1);
  }, []);

  const loadReportsData = async () => {
    setLoading(true);
    try {
      const repRes = await api.getReportsSummary('all');
      setReportSummary(repRes.data);
    } catch (err) {
      console.warn('Reports load error:', err);
    } finally {
      setLoading(false);
    }
  };

  const handleDownload = (format = 'xlsx') => {
    const url = api.getReportDownloadUrl(format, 'all');
    const link = document.createElement('a');
    link.href = url;
    link.setAttribute('download', `veridoc_kyc_compliance_report.${format}`);
    document.body.appendChild(link);
    link.click();
    document.body.removeChild(link);
  };

  const handleViewApplicantDetails = async (applicantId) => {
    setActiveApplicantId(applicantId);
    setLoadingProfile(true);
    try {
      const res = await api.getApplicantProfile(applicantId);
      setApplicantProfile(res.data);
    } catch (err) {
      console.warn('Could not load applicant profile for report modal:', err);
      setApplicantProfile(null);
    } finally {
      setLoadingProfile(false);
    }
  };

  const closeApplicantModal = () => {
    setActiveApplicantId(null);
    setApplicantProfile(null);
  };

  const filteredApplicants = (reportSummary?.applicants || []).filter((app) => {
    const name = (app.name || '').toLowerCase();
    const id = (app.id || '').toLowerCase();
    const st = (app.status || '').toLowerCase();

    if (statusFilter !== 'all') {
      if (statusFilter === 'pending' && st !== 'pending' && st !== 'active') return false;
      if (statusFilter === 'requires_attention' && st !== 'requires_attention' && st !== 'manual_review') return false;
      if (statusFilter === 'verified' && st !== 'verified' && st !== 'approved') return false;
      if (statusFilter === 'rejected' && st !== 'rejected') return false;
    }

    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    return name.includes(term) || id.includes(term);
  });

  const totalPages = Math.max(1, Math.ceil(filteredApplicants.length / itemsPerPage));
  const paginatedApplicants = filteredApplicants.slice(
    (currentPage - 1) * itemsPerPage,
    currentPage * itemsPerPage
  );

  const getStatusBadge = (status) => {
    const st = (status || 'pending').toLowerCase();
    if (st === 'verified' || st === 'approved') {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-100 text-emerald-800">
          Verified
        </span>
      );
    }
    if (st === 'rejected') {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-red-100 text-red-800">
          Rejected
        </span>
      );
    }
    if (st === 'requires_attention' || st === 'manual_review') {
      return (
        <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-100 text-amber-800">
          Requires Attention
        </span>
      );
    }
    return (
      <span className="inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-700">
        Pending Review
      </span>
    );
  };

  return (
    <div className="w-full max-w-7xl mx-auto px-6 lg:px-8 py-8 space-y-8">
      {/* Header */}
      <header className="flex flex-col md:flex-row md:items-end justify-between gap-4 pb-2">
        <div className="space-y-1.5">
          <div className="flex items-center gap-2">
            <span className="text-[11px] font-bold tracking-widest uppercase text-[#64748B]">AUDIT & COMPLIANCE</span>
            <span className="text-[#CBD5E1] text-[11px]">/</span>
            <span className="text-[11px] font-bold tracking-widest uppercase text-[#2563EB]">KYC REPORTS</span>
          </div>
          <h1 className="font-serif text-[38px] font-bold text-[#0F172A] leading-tight">
            Compliance Verification Reports<span className="text-[#2563EB]">.</span>
          </h1>
          <p className="text-[15px] text-[#64748B]">
            Automated verification audits, compliance metrics, and applicant verification ledgers.
          </p>
        </div>

        {/* Export & Download Actions */}
        <div className="flex items-center gap-2.5 flex-wrap">
          <button
            onClick={() => handleDownload('xlsx')}
            className="inline-flex items-center gap-2 px-4 py-2.5 bg-[#0F172A] hover:bg-[#1E293B] text-white rounded-lg text-[13px] font-semibold transition-colors shadow-xs"
            title="Download multi-sheet compliance workbook (.xlsx)"
          >
            <span className="material-symbols-outlined text-[18px] text-emerald-400">table_view</span>
            Export XLSX
          </button>
          <button
            onClick={() => handleDownload('csv')}
            className="inline-flex items-center gap-2 px-3.5 py-2.5 bg-white border border-[#CBD5E1] hover:bg-[#F8FAFC] text-[#0F172A] rounded-lg text-[13px] font-semibold transition-colors shadow-xs"
            title="Download full compliance verification report as CSV"
          >
            <span className="material-symbols-outlined text-[18px] text-[#2563EB]">file_present</span>
            Export CSV
          </button>
          <button
            onClick={() => handleDownload('json')}
            className="inline-flex items-center gap-2 px-3 py-2.5 bg-white border border-[#CBD5E1] hover:bg-[#F8FAFC] text-[#0F172A] rounded-lg text-[13px] font-semibold transition-colors shadow-xs"
            title="Download audit payload as structured JSON"
          >
            <span className="material-symbols-outlined text-[18px] text-purple-600">data_object</span>
            JSON
          </button>
          <button
            onClick={loadReportsData}
            className="p-2.5 bg-white border border-[#CBD5E1] hover:bg-[#F8FAFC] text-[#64748B] rounded-lg transition-colors shadow-xs"
            title="Refresh Report Data"
          >
            <span className="material-symbols-outlined text-[18px]">refresh</span>
          </button>
        </div>
      </header>

      {/* Summary Metrics: 4 Clean Cards */}
      <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
        <div className="bg-white border border-[#E2E8F0] rounded-xl p-5 shadow-xs">
          <div className="text-[11px] font-bold uppercase tracking-wider text-[#64748B]">Total Applicants</div>
          <div className="text-[30px] font-bold text-[#0F172A] mt-1">{reportSummary?.total_applicants ?? '-'}</div>
          <div className="text-[11px] text-[#64748B] mt-0.5">Enrolled applicants</div>
        </div>
        <div className="bg-white border border-[#E2E8F0] rounded-xl p-5 shadow-xs">
          <div className="text-[11px] font-bold uppercase tracking-wider text-[#64748B]">Total Documents</div>
          <div className="text-[30px] font-bold text-[#2563EB] mt-1">{reportSummary?.total_documents ?? '-'}</div>
          <div className="text-[11px] text-[#64748B] mt-0.5">Processed & validated</div>
        </div>
        <div className="bg-white border border-[#E2E8F0] rounded-xl p-5 shadow-xs">
          <div className="text-[11px] font-bold uppercase tracking-wider text-[#64748B]">Verified Applicants</div>
          <div className="text-[30px] font-bold text-emerald-700 mt-1">{reportSummary?.verified_applicants ?? '-'}</div>
          <div className="text-[11px] text-emerald-700 mt-0.5">Identity checks cleared</div>
        </div>
        <div className="bg-white border border-[#E2E8F0] rounded-xl p-5 shadow-xs">
          <div className="text-[11px] font-bold uppercase tracking-wider text-[#64748B]">Requires Attention</div>
          <div className="text-[30px] font-bold text-amber-700 mt-1">{reportSummary?.attention_applicants ?? '-'}</div>
          <div className="text-[11px] text-amber-700 mt-0.5">Discrepancy / manual review</div>
        </div>
      </div>

      {/* AI Usage & Cost Economics (Google Gemini) - Requirement 8 */}
      <section className="bg-white border border-[#E2E8F0] rounded-xl p-5 shadow-xs space-y-4">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-2 pb-2 border-b border-[#E2E8F0]">
          <div className="flex items-center gap-2 flex-wrap">
            <span className="material-symbols-outlined text-[20px] text-[#2563EB]">smart_toy</span>
            <h3 className="text-[15px] font-bold text-[#0F172A]">AI Document Intelligence & Token Telemetry</h3>
            <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-semibold bg-blue-50 text-blue-700 border border-blue-200">
              Google Gemini
            </span>
            <span className="inline-flex items-center px-2 py-0.5 rounded text-[11px] font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
              Local OCR: $0.00 Cost
            </span>
          </div>
          <div className="flex items-center gap-2.5 text-[12px] text-[#64748B] flex-wrap">
            <div className="flex items-center gap-1.5">
              <span>Model:</span>
              <code className="px-2 py-0.5 bg-slate-100 rounded text-[11px] font-mono text-[#0F172A] font-semibold">
                {reportSummary?.ai_usage?.model || 'gemini-3.5-flash-lite'}
              </code>
            </div>
            <button
              onClick={() => setShowUsageLedger(!showUsageLedger)}
              className="inline-flex items-center gap-1.5 px-2.5 py-1 text-[11px] font-semibold rounded border border-[#CBD5E1] bg-[#F8FAFC] hover:bg-slate-100 text-[#0F172A] transition-colors shadow-2xs"
            >
              <span className="material-symbols-outlined text-[14px] text-[#2563EB]">
                {showUsageLedger ? 'expand_less' : 'receipt_long'}
              </span>
              {showUsageLedger ? 'Hide API Ledger' : `View API Ledger (${reportSummary?.ai_usage?.recent_logs?.length ?? 0})`}
            </button>
          </div>
        </div>

        {/* 11 Requirement Metrics Grid */}
        <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-6 gap-3">
          {/* Metric 1 & 2 & 3: Total Docs, Gemini Docs, Locally Processed Docs */}
          <div className="bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg p-3">
            <div className="text-[10px] font-bold uppercase tracking-wider text-[#64748B]">Total Docs Processed</div>
            <div className="text-[20px] font-bold text-[#0F172A] mt-0.5">
              {reportSummary?.ai_usage?.metrics?.total_documents_processed ?? reportSummary?.total_documents ?? 0}
            </div>
            <div className="text-[10px] text-[#64748B] mt-0.5">
              <span className="text-blue-700 font-semibold">{reportSummary?.ai_usage?.metrics?.gemini_documents_count ?? 0}</span> Gemini • <span className="text-slate-700 font-semibold">{reportSummary?.ai_usage?.metrics?.locally_processed_documents ?? 0}</span> local OCR
            </div>
          </div>

          {/* Metric 4 & 5 & 6: Total Calls, Successful Calls, Failed Calls */}
          <div className="bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg p-3">
            <div className="text-[10px] font-bold uppercase tracking-wider text-[#64748B]">Gemini API Calls</div>
            <div className="text-[20px] font-bold text-[#2563EB] mt-0.5">
              {reportSummary?.ai_usage?.metrics?.total_api_calls ?? 0}
            </div>
            <div className="text-[10px] text-[#64748B] mt-0.5">
              <span className="text-emerald-700 font-semibold">{reportSummary?.ai_usage?.metrics?.successful_calls ?? 0}</span> ok • <span className="text-rose-600 font-semibold">{reportSummary?.ai_usage?.metrics?.failed_calls ?? 0}</span> err
            </div>
          </div>

          {/* Metric 7: Total Prompt / Input Tokens */}
          <div className="bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg p-3">
            <div className="text-[10px] font-bold uppercase tracking-wider text-[#64748B]">Prompt Tokens</div>
            <div className="text-[20px] font-bold text-[#0F172A] mt-0.5">
              {reportSummary?.ai_usage?.metrics?.total_prompt_tokens
                ? reportSummary.ai_usage.metrics.total_prompt_tokens.toLocaleString()
                : '0'}
            </div>
            <div className="text-[10px] text-[#64748B] mt-0.5">Input payload tokens</div>
          </div>

          {/* Metric 8: Total Candidate / Output Tokens */}
          <div className="bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg p-3">
            <div className="text-[10px] font-bold uppercase tracking-wider text-[#64748B]">Candidate Tokens</div>
            <div className="text-[20px] font-bold text-[#0F172A] mt-0.5">
              {reportSummary?.ai_usage?.metrics?.total_candidate_tokens
                ? reportSummary.ai_usage.metrics.total_candidate_tokens.toLocaleString()
                : '0'}
            </div>
            <div className="text-[10px] text-[#64748B] mt-0.5">JSON extraction output</div>
          </div>

          {/* Metric 9: Total Tokens Consumed */}
          <div className="bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg p-3">
            <div className="text-[10px] font-bold uppercase tracking-wider text-[#64748B]">Total Tokens</div>
            <div className="text-[20px] font-bold text-[#0F172A] mt-0.5">
              {reportSummary?.ai_usage?.metrics?.total_tokens
                ? reportSummary.ai_usage.metrics.total_tokens.toLocaleString()
                : '0'}
            </div>
            <div className="text-[10px] text-[#64748B] mt-0.5">Billed token volume</div>
          </div>

          {/* Metric 10 & 11: Estimated Cumulative Cost & Average Latency */}
          <div className="bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg p-3">
            <div className="text-[10px] font-bold uppercase tracking-wider text-[#64748B]">Estimated Cost</div>
            <div className="text-[20px] font-bold text-emerald-700 mt-0.5">
              {reportSummary?.ai_usage?.metrics?.cost_available && reportSummary?.ai_usage?.metrics?.estimated_total_cost !== null
                ? `$${reportSummary.ai_usage.metrics.estimated_total_cost.toFixed(4)}`
                : 'Unavailable*'}
            </div>
            <div className="text-[10px] text-[#64748B] mt-0.5">
              Avg latency: <span className="font-semibold text-slate-700">{reportSummary?.ai_usage?.metrics?.avg_latency_ms ? `${reportSummary.ai_usage.metrics.avg_latency_ms} ms` : '—'}</span>
            </div>
          </div>
        </div>

        {/* Informative Guidance & Cost Transparency */}
        <div className="flex flex-col sm:flex-row sm:items-center justify-between text-[11px] text-[#64748B] pt-1 border-t border-[#F1F5F9] gap-1">
          <div>
            * Pricing tier: <span className="font-semibold text-slate-700">${reportSummary?.ai_usage?.pricing?.input_per_m ?? 0.075}</span> / 1M input, <span className="font-semibold text-slate-700">${reportSummary?.ai_usage?.pricing?.output_per_m ?? 0.3}</span> / 1M output (Flash tier).
            {(!reportSummary?.ai_usage?.metrics?.cost_available) && (
              <span className="ml-1 text-slate-500">(Historical documents without token telemetry are marked cost unavailable).</span>
            )}
          </div>
          <div className="text-emerald-700 font-medium">
            Local OCR fallback documents incur $0.00 API cost.
          </div>
        </div>

        {/* API Transaction Telemetry Ledger */}
        {showUsageLedger && (
          <div className="mt-3 pt-3 border-t border-[#E2E8F0] space-y-2">
            <div className="flex items-center justify-between">
              <h4 className="text-[13px] font-bold text-[#0F172A] flex items-center gap-1.5">
                <span className="material-symbols-outlined text-[16px] text-[#2563EB]">list_alt</span>
                Recent Gemini API Transaction Ledger
              </h4>
              <span className="text-[11px] text-[#64748B]">Showing recent {reportSummary?.ai_usage?.recent_logs?.length ?? 0} request records</span>
            </div>

            {(!reportSummary?.ai_usage?.recent_logs || reportSummary.ai_usage.recent_logs.length === 0) ? (
              <div className="text-center py-6 text-[12px] text-[#64748B] bg-[#F8FAFC] rounded-lg border border-[#E2E8F0]">
                No Gemini API calls recorded yet. Documents processed via local OCR incur no API telemetry.
              </div>
            ) : (
              <div className="overflow-x-auto border border-[#E2E8F0] rounded-lg">
                <table className="w-full text-left text-[12px] border-collapse bg-white">
                  <thead>
                    <tr className="bg-[#F8FAFC] border-b border-[#E2E8F0] text-[10px] font-bold uppercase tracking-wider text-[#64748B]">
                      <th className="py-2.5 px-3">Time</th>
                      <th className="py-2.5 px-3">Document / Applicant</th>
                      <th className="py-2.5 px-3">Channel / Type</th>
                      <th className="py-2.5 px-3">Status</th>
                      <th className="py-2.5 px-3">Tokens (In / Out / Tot)</th>
                      <th className="py-2.5 px-3">Latency</th>
                      <th className="py-2.5 px-3">Estimated Cost</th>
                      <th className="py-2.5 px-3">Notes</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-[#E2E8F0]">
                    {reportSummary.ai_usage.recent_logs.map((log) => (
                      <tr key={log.id} className="hover:bg-slate-50 transition-colors">
                        <td className="py-2 px-3 text-[#64748B] font-mono text-[11px] whitespace-nowrap">
                          {log.created_at ? log.created_at.replace('T', ' ').slice(0, 19) : '—'}
                        </td>
                        <td className="py-2 px-3">
                          <div className="font-semibold text-[#0F172A]">{log.document_id || 'System Probe'}</div>
                          {log.applicant_id && (
                            <div className="text-[10px] text-[#64748B] font-mono">{log.applicant_id}</div>
                          )}
                          {log.original_filename && (
                            <div className="text-[10px] text-slate-500 truncate max-w-[140px]">{log.original_filename}</div>
                          )}
                        </td>
                        <td className="py-2 px-3">
                          <span className="inline-flex items-center px-1.5 py-0.5 rounded text-[10px] font-mono bg-slate-100 text-slate-700">
                            {log.channel || 'SDK'}
                          </span>
                          {log.request_type && log.request_type !== 'multimodal_extraction' && (
                            <div className="text-[10px] text-slate-400">{log.request_type}</div>
                          )}
                        </td>
                        <td className="py-2 px-3">
                          {log.status === 'success' ? (
                            <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                              SUCCESS
                            </span>
                          ) : (
                            <span className="inline-flex items-center px-2 py-0.5 rounded text-[10px] font-semibold bg-rose-50 text-rose-700 border border-rose-200" title={log.error_message || 'Error'}>
                              ERROR
                            </span>
                          )}
                        </td>
                        <td className="py-2 px-3 font-mono text-[11px]">
                          {log.total_tokens !== null && log.total_tokens !== undefined ? (
                            <span>
                              <span className="text-[#64748B]">{log.prompt_tokens ?? 0}</span> / <span className="text-slate-700">{log.candidate_tokens ?? 0}</span> (<span className="font-bold text-[#0F172A]">{log.total_tokens}</span>)
                            </span>
                          ) : (
                            <span className="text-slate-400">—</span>
                          )}
                        </td>
                        <td className="py-2 px-3 text-[#64748B] font-mono text-[11px]">
                          {log.latency_ms !== null && log.latency_ms !== undefined ? `${log.latency_ms} ms` : '—'}
                        </td>
                        <td className="py-2 px-3 font-semibold text-emerald-700 font-mono text-[11px]">
                          {log.estimated_cost !== null && log.estimated_cost !== undefined ? `$${log.estimated_cost.toFixed(6)}` : '—'}
                        </td>
                        <td className="py-2 px-3 text-[11px] text-[#64748B] max-w-[200px] truncate" title={log.error_message || ''}>
                          {log.error_message ? <span className="text-rose-600">{log.error_message}</span> : <span className="text-slate-400">{log.model}</span>}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        )}
      </section>

      {/* Applicant Verification Audit Ledger */}
      <section className="bg-white border border-[#E2E8F0] rounded-xl shadow-xs overflow-hidden space-y-4 p-6">
        <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2 border-b border-[#E2E8F0]">
          <div>
            <h3 className="text-[18px] font-bold text-[#0F172A]">Applicant Verification Audit Ledger</h3>
            <p className="text-[12px] text-[#64748B]">Comprehensive applicant compliance records and specific verification findings.</p>
          </div>

          <div className="flex flex-wrap items-center gap-2.5">
            <input
              type="text"
              placeholder="Search applicant name or ID..."
              value={searchTerm}
              onChange={(e) => setSearchTerm(e.target.value)}
              className="bg-[#F8FAFC] border border-[#CBD5E1] rounded-lg px-3 py-1.5 text-[12px] text-[#0F172A] focus:outline-none focus:border-[#2563EB] min-w-[200px]"
            />
            <select
              value={statusFilter}
              onChange={(e) => setStatusFilter(e.target.value)}
              className="bg-[#F8FAFC] border border-[#CBD5E1] rounded-lg px-3 py-1.5 text-[12px] text-[#0F172A] focus:outline-none focus:border-[#2563EB]"
            >
              <option value="all">All Statuses</option>
              <option value="pending">Pending Review</option>
              <option value="requires_attention">Requires Attention</option>
              <option value="verified">Verified</option>
              <option value="rejected">Rejected</option>
            </select>
          </div>
        </div>

        <div className="overflow-x-auto">
          <table className="w-full text-left text-[13px] border-collapse">
            <thead>
              <tr className="bg-[#F8FAFC] border-b border-[#E2E8F0] text-[#64748B] text-[11px] uppercase tracking-wider">
                <th className="py-3 px-4 font-semibold">Applicant</th>
                <th className="py-3 px-4 font-semibold">Documents</th>
                <th className="py-3 px-4 font-semibold">Verification Status</th>
                <th className="py-3 px-4 font-semibold">Issues Found</th>
                <th className="py-3 px-4 font-semibold text-right">Actions</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E2E8F0]">
              {loading ? (
                <tr>
                  <td colSpan="5" className="py-8 text-center text-[#64748B]">
                    Loading audit ledger...
                  </td>
                </tr>
              ) : paginatedApplicants.length === 0 ? (
                <tr>
                  <td colSpan="5" className="py-8 text-center text-[#64748B]">
                    No applicant records match the selected criteria.
                  </td>
                </tr>
              ) : (
                paginatedApplicants.map((app) => {
                  const hasDiscrepancies = app.discrepancies && app.discrepancies.length > 0;
                  return (
                    <tr key={app.id} className="hover:bg-[#F8FAFC] transition-colors">
                      <td className="py-3.5 px-4">
                        <div className="font-semibold text-[#0F172A]">
                          {app.name || <span className="text-amber-800 italic font-medium">Name not detected</span>}
                        </div>
                        <div className="text-[11px] font-mono text-[#64748B]">#{app.id}</div>
                      </td>
                      <td className="py-3.5 px-4">
                        <div className="font-semibold text-[#0F172A]">{app.doc_count} document(s)</div>
                        <div className="text-[11px] text-[#64748B] capitalize">{(app.doc_types || []).join(', ')}</div>
                      </td>
                      <td className="py-3.5 px-4">
                        {getStatusBadge(app.status)}
                      </td>
                      <td className="py-3.5 px-4 max-w-lg">
                        {app.status === 'verified' || (!app.primary_issue && (!app.discrepancies || app.discrepancies.length === 0)) ? (
                          <span className="text-emerald-700 font-medium text-[12px] flex items-center gap-1">
                            <span className="material-symbols-outlined text-[15px]">check_circle</span>
                            No discrepancies found
                          </span>
                        ) : (
                          <div className="space-y-1.5">
                            {/* ONE Primary Concise Rejection / Issue Reason */}
                            <div className="flex items-center gap-2 flex-wrap">
                              <span className={`inline-block px-2.5 py-0.5 rounded text-[11px] font-semibold border ${
                                app.status === 'rejected'
                                  ? 'bg-red-50 text-red-800 border-red-200'
                                  : 'bg-amber-50 text-amber-800 border-amber-200'
                              }`}>
                                {app.primary_issue || (app.discrepancies && app.discrepancies[0]) || 'Requires attention'}
                              </span>

                              {/* Expandable toggle if there are detailed findings or officer remarks */}
                              {(app.validation_issues?.length > 0 || app.officer_remarks || (app.discrepancies && app.discrepancies.length > 1) || app.affected_docs?.length > 0) && (
                                <button
                                  type="button"
                                  onClick={() => toggleExpand(app.id)}
                                  className="text-[11px] text-[#2563EB] hover:text-[#1D4ED8] hover:underline font-semibold inline-flex items-center gap-0.5 transition-colors"
                                >
                                  <span>{expandedApplicantIds.has(app.id) ? 'Hide details' : 'View details'}</span>
                                  <span className="material-symbols-outlined text-[14px]">
                                    {expandedApplicantIds.has(app.id) ? 'expand_less' : 'expand_more'}
                                  </span>
                                </button>
                              )}
                            </div>

                            {/* Expandable Detailed Findings & Officer Remarks */}
                            {expandedApplicantIds.has(app.id) && (
                              <div className="p-3 bg-slate-50 border border-slate-200 rounded-lg text-[12px] space-y-2 mt-1.5 animate-in fade-in">
                                {app.officer_remarks && (
                                  <div>
                                    <div className="font-bold text-[#0F172A] text-[11px] uppercase tracking-wider">Officer Remarks / Decision:</div>
                                    <div className="text-slate-700 text-[12px]">{app.officer_remarks}</div>
                                  </div>
                                )}

                                {((app.validation_issues && app.validation_issues.length > 0) || (app.discrepancies && app.discrepancies.length > 0)) && (
                                  <div>
                                    <div className="font-bold text-[#0F172A] text-[11px] uppercase tracking-wider">Validation Findings:</div>
                                    <ul className="list-disc list-inside text-slate-700 text-[11px] space-y-0.5">
                                      {(app.validation_issues || app.discrepancies).map((issue, idx) => (
                                        <li key={idx}>{issue}</li>
                                      ))}
                                    </ul>
                                  </div>
                                )}

                                {app.affected_docs && app.affected_docs.length > 0 && (
                                  <div>
                                    <div className="font-bold text-[#0F172A] text-[11px] uppercase tracking-wider">Affected Documents ({app.affected_docs.length}):</div>
                                    <div className="space-y-0.5 text-[11px] text-slate-600 font-mono">
                                      {app.affected_docs.map((doc, idx) => (
                                        <div key={idx}>
                                          • {doc.type}: {doc.filename} {doc.flags?.length ? `— ${doc.flags.join('; ')}` : ''}
                                        </div>
                                      ))}
                                    </div>
                                  </div>
                                )}
                              </div>
                            )}
                          </div>
                        )}
                      </td>
                      <td className="py-3.5 px-4 text-right">
                        <button
                          onClick={() => handleViewApplicantDetails(app.id)}
                          className="px-2.5 py-1 text-[11px] font-bold text-[#2563EB] bg-blue-50 hover:bg-blue-100 rounded border border-blue-200 transition-colors"
                        >
                          View Details
                        </button>
                      </td>
                    </tr>
                  );
                })
              )}
            </tbody>
          </table>
        </div>

        {/* Pagination Controls */}
        {totalPages > 1 && (
          <div className="flex items-center justify-between pt-3 border-t border-[#E2E8F0] text-[12px] text-[#64748B]">
            <div>
              Showing {((currentPage - 1) * itemsPerPage) + 1} to {Math.min(currentPage * itemsPerPage, filteredApplicants.length)} of {filteredApplicants.length} applicants
            </div>
            <div className="flex items-center gap-1">
              <button
                disabled={currentPage === 1}
                onClick={() => setCurrentPage(p => Math.max(1, p - 1))}
                className="px-2.5 py-1 rounded border border-[#CBD5E1] bg-white text-[#0F172A] disabled:opacity-50"
              >
                Previous
              </button>
              <span className="px-2 font-medium">Page {currentPage} of {totalPages}</span>
              <button
                disabled={currentPage === totalPages}
                onClick={() => setCurrentPage(p => Math.min(totalPages, p + 1))}
                className="px-2.5 py-1 rounded border border-[#CBD5E1] bg-white text-[#0F172A] disabled:opacity-50"
              >
                Next
              </button>
            </div>
          </div>
        )}
      </section>

      {/* Applicant Comparison Matrix Modal */}
      {activeApplicantId && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-5xl w-full max-h-[90vh] overflow-y-auto p-6 space-y-4 border border-[#CBD5E1]">
            <div className="flex items-center justify-between pb-3 border-b border-[#E2E8F0]">
              <div>
                <h3 className="text-[18px] font-bold text-[#0F172A]">
                  Applicant Identity Verification Dossier
                </h3>
                <p className="text-[12px] text-[#64748B]">Applicant ID: #{activeApplicantId}</p>
              </div>
              <button
                onClick={closeApplicantModal}
                className="p-1 rounded-lg text-slate-400 hover:text-slate-700 hover:bg-slate-100"
              >
                <span className="material-symbols-outlined text-[20px]">close</span>
              </button>
            </div>

            {/* Rejection notice banner if applicant was rejected */}
            {applicantProfile?.applicant?.status === 'rejected' && (
              <div className="p-3.5 bg-red-50 border border-red-200 rounded-xl space-y-1">
                <div className="flex items-center gap-2 text-red-800 font-bold text-[13px]">
                  <span className="material-symbols-outlined text-[17px]">cancel</span>
                  <span>Applicant KYC Rejected</span>
                </div>
                {applicantProfile?.applicant?.notes && (
                  <p className="text-[12px] text-red-700">
                    <strong>Recorded Reason / Officer Remarks:</strong> {applicantProfile.applicant.notes}
                  </p>
                )}
              </div>
            )}

            {loadingProfile ? (
              <div className="p-12 text-center text-[#64748B]">Loading applicant comparison matrix...</div>
            ) : applicantProfile?.cross_comparison?.matrix ? (
              <ComparisonMatrix
                matrix={applicantProfile.cross_comparison.matrix}
                applicantId={activeApplicantId}
                applicantName={applicantProfile.applicant?.name}
              />
            ) : (
              <div className="p-8 text-center text-[#64748B] text-[13px]">
                No structured comparison matrix available for this applicant.
              </div>
            )}

            <div className="flex justify-end pt-2">
              <button
                onClick={closeApplicantModal}
                className="px-4 py-2 bg-[#0F172A] text-white rounded-lg text-[13px] font-semibold"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
