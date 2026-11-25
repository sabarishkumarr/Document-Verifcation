import React from 'react';
import { api } from '../api';

export default function ComparisonMatrix({ matrix, applicantId, applicantName, onNavigateToQueue, onNavigateToApplicant }) {
  if (!matrix || !matrix.rows || matrix.rows.length === 0) {
    return (
      <div className="bg-white border border-[#E2E8F0] rounded-xl p-6 text-center text-[#64748B] text-[13px]">
        No comparison matrix available. Upload at least one document to generate the structured comparison.
      </div>
    );
  }

  const columns = matrix.columns || [];
  const rows = matrix.rows || [];
  const targetApplicantId = applicantId || matrix.applicant_id;

  const getStatusBadge = (status, label) => {
    const s = (status || '').toLowerCase().replace(/_/g, ' ');
    if (s === 'match' || s === 'valid') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
          <span className="material-symbols-outlined text-[13px]">check_circle</span>
          {label || 'MATCH'}
        </span>
      );
    }
    if (s === 'mismatch') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-red-50 text-red-700 border border-red-200">
          <span className="material-symbols-outlined text-[13px]">cancel</span>
          {label || 'MISMATCH'}
        </span>
      );
    }
    if (s === 'expired') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-rose-50 text-rose-800 border border-rose-300">
          <span className="material-symbols-outlined text-[13px]">event_busy</span>
          {label || 'EXPIRED'}
        </span>
      );
    }
    if (s === 'needs review' || s === 'warning' || s === 'variation') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-50 text-amber-800 border border-amber-300">
          <span className="material-symbols-outlined text-[13px]">warning</span>
          {label || 'NEEDS REVIEW'}
        </span>
      );
    }
    if (s === 'not detected' || s === 'unavailable' || s === 'missing') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-50 text-amber-800 border border-amber-300">
          <span className="material-symbols-outlined text-[13px]">help_outline</span>
          {label || 'NOT DETECTED'}
        </span>
      );
    }
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[11px] font-medium bg-slate-100 text-slate-600 border border-slate-200">
        {label || 'NOT APPLICABLE'}
      </span>
    );
  };

  const getRowBackground = (status) => {
    const s = (status || '').toLowerCase().replace(/_/g, ' ');
    if (s === 'mismatch' || s === 'expired') return 'bg-red-50/40 hover:bg-red-50/70';
    if (s === 'needs review' || s === 'warning') return 'bg-amber-50/30 hover:bg-amber-50/60';
    return 'hover:bg-[#F8FAFC]';
  };

  const handleExport = (format) => {
    if (!targetApplicantId) return;
    const url = api.getApplicantComparisonExportUrl(targetApplicantId, format);
    window.open(url, '_blank');
  };

  return (
    <div className="bg-white border border-[#E2E8F0] rounded-xl shadow-xs overflow-hidden">
      {/* Top action header */}
      <div className="p-5 border-b border-[#E2E8F0] bg-white flex flex-col sm:flex-row sm:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[#2563EB] text-[20px]">table_chart</span>
            <h3 className="text-[16px] font-bold text-[#0F172A]">Cross-Document Comparison Matrix</h3>
            {matrix.overall_verdict && (
              <span className={`ml-2 px-2.5 py-0.5 rounded-full text-[11px] font-bold uppercase tracking-wider ${
                matrix.overall_verdict === 'VERIFIED'
                  ? 'bg-emerald-100 text-emerald-800 border border-emerald-200'
                  : matrix.overall_verdict === 'MANUAL_REVIEW'
                  ? 'bg-amber-100 text-amber-800 border border-amber-200'
                  : 'bg-red-100 text-red-800 border border-red-200'
              }`}>
                {matrix.overall_verdict.replace('_', ' ')}
              </span>
            )}
          </div>
          <p className="text-[12px] text-[#64748B] mt-1">
            Deterministic attribute-by-document comparison for applicant{' '}
            <strong className="text-[#0F172A]">{applicantName || matrix.applicant_name || targetApplicantId}</strong> ({columns.length} document{columns.length !== 1 ? 's' : ''} compared)
          </p>
        </div>

        {/* Export and Action Buttons */}
        <div className="flex items-center gap-2 flex-wrap">
          <button
            onClick={() => handleExport('xlsx')}
            disabled={!targetApplicantId}
            title="Download comparison matrix in Excel spreadsheet format (.xlsx)"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#F8FAFC] hover:bg-[#F1F5F9] text-[#0F172A] border border-[#CBD5E1] rounded-lg text-[12px] font-semibold transition-colors disabled:opacity-50"
          >
            <span className="material-symbols-outlined text-[16px] text-emerald-600">download</span>
            Export XLSX
          </button>
          <button
            onClick={() => handleExport('csv')}
            disabled={!targetApplicantId}
            title="Download comparison matrix as Comma Separated Values (.csv)"
            className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#F8FAFC] hover:bg-[#F1F5F9] text-[#0F172A] border border-[#CBD5E1] rounded-lg text-[12px] font-semibold transition-colors disabled:opacity-50"
          >
            <span className="material-symbols-outlined text-[16px] text-[#2563EB]">file_present</span>
            Export CSV
          </button>

          {onNavigateToQueue && columns[0]?.id && (
            <button
              onClick={() => onNavigateToQueue(columns[0].id)}
              className="inline-flex items-center gap-1 px-3 py-1.5 bg-[#0F172A] hover:bg-[#1E293B] text-white rounded-lg text-[12px] font-semibold transition-colors shadow-xs"
            >
              <span className="material-symbols-outlined text-[15px]">fact_check</span>
              Review in Queue
            </button>
          )}

          {onNavigateToApplicant && targetApplicantId && (
            <button
              onClick={() => onNavigateToApplicant(targetApplicantId)}
              className="inline-flex items-center gap-1 px-3 py-1.5 bg-[#2563EB] hover:bg-blue-700 text-white rounded-lg text-[12px] font-semibold transition-colors shadow-xs"
            >
              <span className="material-symbols-outlined text-[15px]">account_box</span>
              View Profile
            </button>
          )}
        </div>
      </div>

      {/* Spreadsheet Table */}
      <div className="overflow-x-auto w-full">
        <table className="min-w-full text-left border-collapse text-[13px]">
          <thead>
            <tr className="bg-[#F8FAFC] border-b border-[#E2E8F0]">
              <th className="py-3 px-4 font-bold text-[#475569] uppercase tracking-wider text-[11px] w-[190px] min-w-[190px] max-w-[210px] break-words whitespace-normal sticky left-0 bg-[#F8FAFC] z-10 border-r border-[#E2E8F0]">
                Identity Attribute
              </th>
              {columns.map((col) => (
                <th key={col.id} className="py-3 px-4 font-semibold text-[#0F172A] w-[220px] min-w-[220px] max-w-[250px] border-r border-[#E2E8F0]">
                  <div className="flex items-center justify-between gap-1 mb-1">
                    <span className="text-[11px] font-mono text-[#64748B]">#{col.id.slice(0, 6)}</span>
                    <span className="px-1.5 py-0.5 rounded text-[10px] font-bold uppercase bg-blue-100 text-blue-800">
                      {col.type_label || col.document_type}
                    </span>
                  </div>
                  <div className="font-bold text-[12px] text-[#0F172A] break-all line-clamp-2 leading-tight" title={col.filename}>
                    {col.filename}
                  </div>
                </th>
              ))}
              <th className="py-3 px-4 font-bold text-[#475569] uppercase tracking-wider text-[11px] w-[140px] min-w-[140px] border-r border-[#E2E8F0]">
                Result
              </th>
              <th className="py-3 px-4 font-bold text-[#475569] uppercase tracking-wider text-[11px] min-w-[240px] max-w-[360px] break-words whitespace-normal">
                Verification Explanation
              </th>
            </tr>
          </thead>
          <tbody className="divide-y divide-[#E2E8F0]">
            {rows.map((row, idx) => (
              <tr key={idx} className={`transition-colors ${getRowBackground(row.result_status)}`}>
                <td className="py-3 px-4 font-bold text-[#0F172A] w-[190px] min-w-[190px] max-w-[210px] break-words whitespace-normal sticky left-0 bg-inherit z-10 border-r border-[#E2E8F0]">
                  {row.attribute_label}
                </td>
                {columns.map((col) => {
                  const val = row.values ? row.values[col.id] : null;
                  const isNotDetected = !val || val === 'Not detected' || val === 'Not Detected' || val === 'Not Available';
                  const isNotApplicable = val === 'Not applicable' || val === 'Not Applicable';
                  return (
                    <td key={col.id} className="py-3 px-4 border-r border-[#E2E8F0] font-mono text-[12px] w-[220px] min-w-[220px] max-w-[250px] break-words whitespace-normal">
                      {isNotApplicable ? (
                        <span className="text-slate-400 italic font-sans">Not applicable</span>
                      ) : isNotDetected ? (
                        <span className="text-amber-700 italic font-sans font-medium">Not detected</span>
                      ) : (
                        <span className="text-[#0F172A] font-medium break-words">{String(val)}</span>
                      )}
                    </td>
                  );
                })}
                <td className="py-3 px-4 border-r border-[#E2E8F0] w-[140px] min-w-[140px] align-middle">
                  {getStatusBadge(row.result_status, row.result_label)}
                </td>
                <td className="py-3 px-4 text-[12px] text-[#475569] leading-relaxed min-w-[240px] max-w-[360px] break-words whitespace-normal">
                  {row.explanation}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      {/* Footer isolation note */}
      <div className="p-3 bg-[#F8FAFC] border-t border-[#E2E8F0] flex items-center justify-between text-[11px] text-[#64748B]">
        <span>Strict applicant data isolation: Documents compared belong solely to applicant <strong>{targetApplicantId}</strong>.</span>
        <span>Deterministic Verification</span>
      </div>
    </div>
  );
}
