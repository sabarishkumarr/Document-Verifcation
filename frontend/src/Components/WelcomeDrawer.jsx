import React, { useState } from 'react';
import { api } from '../api';

export default function WelcomeDrawer({
  isOpen,
  onClose,
  officerName,
  onUpdateOfficerName,
  onNavigateTab,
}) {
  const [isEditingName, setIsEditingName] = useState(false);
  const [editedName, setEditedName] = useState(officerName || 'Arjun Mehta');
  const [isResetting, setIsResetting] = useState(false);
  const [notice, setNotice] = useState(null);

  if (!isOpen) return null;

  const handleSaveName = (e) => {
    e.preventDefault();
    if (editedName.trim()) {
      onUpdateOfficerName(editedName.trim());
      setIsEditingName(false);
    }
  };

  const handleResetDemo = async () => {
    if (!window.confirm('Reset synthetic demo dataset to initial baseline state?')) return;
    setIsResetting(true);
    setNotice(null);
    try {
      const res = await api.resetDemo();
      setNotice({ type: 'success', text: res.message || 'Synthetic demo dataset reset successfully.' });
      setTimeout(() => {
        window.location.reload();
      }, 1000);
    } catch (err) {
      setNotice({ type: 'error', text: err.message || 'Failed to reset demonstration dataset.' });
    } finally {
      setIsResetting(false);
    }
  };

  const shortcuts = [
    { id: 'overview', label: 'Operational Overview', desc: 'Pending reviews, queue metrics and daily status' },
    { id: 'repository', label: 'Document Repository', desc: 'Catalog of document types and interactive attribute mapping' },
    { id: 'upload', label: 'Upload Documents', desc: 'Direct applicant document ingestion and AI classification' },
    { id: 'verification', label: 'Verification Workspace', desc: 'Unified applicant directory, confidence score gate (>75%) & review' },
    { id: 'triangulation', label: 'Cross-Document Triangulation', desc: 'Consensus matrix across applicant identity documents' },
    { id: 'reports', label: 'Reports & Cost Ledger', desc: 'Compliance exports and per-page AI usage tracking' },
  ];

  return (
    <div className="fixed inset-0 z-50 flex justify-end">
      {/* Backdrop */}
      <div
        className="fixed inset-0 bg-slate-900/30 backdrop-blur-xs transition-opacity"
        onClick={onClose}
      />

      {/* Slide-over Drawer */}
      <div className="relative w-full max-w-md bg-white h-full shadow-2xl border-l border-[#E2E8F0] flex flex-col z-10 animate-in slide-in-from-right duration-200">
        
        {/* Drawer Header */}
        <div className="p-5 border-b border-[#E2E8F0] flex items-center justify-between bg-[#F8FAFC]">
          <div className="flex items-center gap-2.5">
            <span className="w-2.5 h-2.5 rounded-full bg-[#2563EB]" />
            <h2 className="text-[15px] font-bold text-[#0F172A] tracking-tight">
              Welcome Desk & System Guide
            </h2>
          </div>
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-lg flex items-center justify-center text-[#64748B] hover:text-[#0F172A] hover:bg-slate-200/60 transition-colors"
            title="Close Welcome Desk"
          >
            <span className="text-[18px] leading-none">✕</span>
          </button>
        </div>

        {/* Drawer Body */}
        <div className="p-5 overflow-y-auto flex-grow space-y-6 text-[13px]">
          
          {/* Active Review Officer Card */}
          <div className="bg-[#F8FAFC] border border-[#E2E8F0] rounded-xl p-4">
            <div className="flex items-center justify-between mb-2">
              <span className="text-[11px] font-bold uppercase tracking-wider text-[#64748B]">
                Active Review Officer
              </span>
              {!isEditingName && (
                <button
                  onClick={() => {
                    setEditedName(officerName);
                    setIsEditingName(true);
                  }}
                  className="text-[11px] font-semibold text-[#2563EB] hover:underline"
                >
                  Edit Name
                </button>
              )}
            </div>

            {isEditingName ? (
              <form onSubmit={handleSaveName} className="space-y-2 mt-2">
                <input
                  type="text"
                  value={editedName}
                  onChange={(e) => setEditedName(e.target.value)}
                  className="w-full px-3 py-1.5 border border-[#CBD5E1] rounded-lg text-[13px] font-medium text-[#0F172A] focus:outline-none focus:ring-2 focus:ring-[#2563EB]"
                  placeholder="Officer Name"
                  autoFocus
                />
                <div className="flex gap-2 justify-end">
                  <button
                    type="button"
                    onClick={() => setIsEditingName(false)}
                    className="px-2.5 py-1 text-[11px] font-semibold text-[#64748B] hover:bg-slate-200 rounded"
                  >
                    Cancel
                  </button>
                  <button
                    type="submit"
                    className="px-3 py-1 text-[11px] font-semibold bg-[#2563EB] text-white rounded hover:bg-[#1D4ED8]"
                  >
                    Save
                  </button>
                </div>
              </form>
            ) : (
              <div className="flex items-center gap-3">
                <div className="w-9 h-9 rounded-full bg-[#0F172A] text-white flex items-center justify-center text-[13px] font-bold">
                  {(officerName || 'RO')
                    .split(' ')
                    .map((n) => n[0])
                    .join('')
                    .substring(0, 2)
                    .toUpperCase()}
                </div>
                <div>
                  <div className="font-bold text-[#0F172A] text-[14px]">{officerName}</div>
                  <div className="text-[12px] text-[#64748B]">Compliance & Verification Specialist</div>
                </div>
              </div>
            )}
          </div>

          {/* Core System Standards */}
          <div className="space-y-2.5">
            <span className="text-[11px] font-bold uppercase tracking-wider text-[#64748B]">
              Operational Guidelines
            </span>
            <div className="space-y-2">
              <div className="p-3 bg-white border border-[#E2E8F0] rounded-lg flex items-start gap-2.5">
                <span className="w-1.5 h-1.5 rounded-full bg-[#2563EB] mt-1.5 shrink-0" />
                <div className="text-[12px] text-[#334155]">
                  <strong className="text-[#0F172A]">Strict Applicant Isolation:</strong> Documents from different applicants are never compared or intermingled.
                </div>
              </div>
              <div className="p-3 bg-white border border-[#E2E8F0] rounded-lg flex items-start gap-2.5">
                <span className="w-1.5 h-1.5 rounded-full bg-emerald-500 mt-1.5 shrink-0" />
                <div className="text-[12px] text-[#334155]">
                  <strong className="text-[#0F172A]">Masked PII Standards:</strong> Aadhaar numbers are masked to trailing 4 digits (<code className="font-mono text-[11px]">XXXX-XXXX-1234</code>) in all views and reports.
                </div>
              </div>
              <div className="p-3 bg-white border border-[#E2E8F0] rounded-lg flex items-start gap-2.5">
                <span className="w-1.5 h-1.5 rounded-full bg-amber-500 mt-1.5 shrink-0" />
                <div className="text-[12px] text-[#334155]">
                  <strong className="text-[#0F172A]">In-Context Schema Learning:</strong> Adding custom attributes synthesizes extraction rules and few-shot exemplars without neural model weight modifications.
                </div>
              </div>
            </div>
          </div>

          {/* Quick Navigation Directory */}
          <div className="space-y-2">
            <span className="text-[11px] font-bold uppercase tracking-wider text-[#64748B]">
              Workspace Modules
            </span>
            <div className="grid grid-cols-1 gap-1.5">
              {shortcuts.map((s) => (
                <button
                  key={s.id}
                  onClick={() => {
                    onNavigateTab(s.id);
                    onClose();
                  }}
                  className="w-full text-left p-2.5 rounded-lg border border-transparent hover:border-[#E2E8F0] hover:bg-[#F8FAFC] transition-all group"
                >
                  <div className="font-semibold text-[#0F172A] text-[13px] group-hover:text-[#2563EB] flex items-center justify-between">
                    <span>{s.label}</span>
                    <span className="text-[12px] text-[#94A3B8] group-hover:translate-x-0.5 transition-transform">→</span>
                  </div>
                  <div className="text-[11px] text-[#64748B] mt-0.5 line-clamp-1">{s.desc}</div>
                </button>
              ))}
            </div>
          </div>

          {/* Demo Dataset Management */}
          <div className="pt-4 border-t border-[#E2E8F0] space-y-3">
            <span className="text-[11px] font-bold uppercase tracking-wider text-[#64748B]">
              Demonstration Environment
            </span>
            <div className="p-3 bg-slate-50 border border-[#E2E8F0] rounded-lg text-[12px] text-[#64748B] flex flex-col gap-2.5">
              <span>
                Reset synthetic fixture documents, test applicant records, and benchmark state.
              </span>
              <button
                type="button"
                onClick={handleResetDemo}
                disabled={isResetting}
                className="self-start px-3 py-1.5 bg-white border border-[#CBD5E1] hover:bg-slate-100 text-[#0F172A] rounded-lg text-[11px] font-semibold transition-colors disabled:opacity-50"
              >
                {isResetting ? 'Resetting dataset...' : 'Reset Demonstration Dataset'}
              </button>
            </div>
            {notice && (
              <div className={`p-2.5 rounded-lg text-[12px] ${
                notice.type === 'success' ? 'bg-emerald-50 text-emerald-700 border border-emerald-200' : 'bg-red-50 text-red-700 border border-red-200'
              }`}>
                {notice.text}
              </div>
            )}
          </div>

        </div>

        {/* Drawer Footer */}
        <div className="p-4 border-t border-[#E2E8F0] bg-[#F8FAFC] flex items-center justify-between text-[11px] text-[#64748B]">
          <span>VeriDoc AI 2.0 · Universal Platform</span>
          <span>Click blue dot anytime to reopen</span>
        </div>

      </div>
    </div>
  );
}
