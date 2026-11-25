import React, { useState, useEffect } from 'react';
import { api } from '../api';
import ComparisonMatrix from './ComparisonMatrix';

export default function ApplicantsView({ onNavigateToQueue, initialApplicantId }) {
  const [applicants, setApplicants] = useState([]);
  const [searchTerm, setSearchTerm] = useState('');
  const [statusFilter, setStatusFilter] = useState('all');
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [selectedApplicant, setSelectedApplicant] = useState(null);
  const [applicantProfile, setApplicantProfile] = useState(null);
  const [loadingProfile, setLoadingProfile] = useState(false);
  const [editing, setEditing] = useState(false);
  const [editForm, setEditForm] = useState({ name: '', email: '', phone: '', risk_level: 'low', notes: '' });
  const [savingProfile, setSavingProfile] = useState(false);

  useEffect(() => {
    loadApplicants();
  }, []);

  const loadApplicants = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getApplicants();
      const list = res.data.applicants || [];
      setApplicants(list);
      if (initialApplicantId && list.length > 0) {
        const found = list.find((a) => a.id === initialApplicantId);
        if (found) {
          openProfile(found);
        }
      }
    } catch (err) {
      setError(err.message || 'Failed to load applicants.');
    } finally {
      setLoading(false);
    }
  };

  const filteredApplicants = applicants.filter((a) => {
    if (statusFilter !== 'all') {
      const st = (a.status || 'pending').toLowerCase();
      if (statusFilter === 'pending' && st !== 'pending' && st !== 'active') return false;
      if (statusFilter === 'requires_attention' && st !== 'requires_attention' && st !== 'manual_review') return false;
      if (statusFilter === 'verified' && st !== 'verified' && st !== 'approved') return false;
      if (statusFilter === 'rejected' && st !== 'rejected') return false;
    }

    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    const name = (a.name || '').toLowerCase();
    const id = (a.id || '').toLowerCase();
    const email = (a.email || '').toLowerCase();
    return name.includes(term) || id.includes(term) || email.includes(term);
  });

  const openProfile = async (applicant) => {
    setSelectedApplicant(applicant);
    setEditing(false);
    setEditForm({
      name: applicant.name || '',
      email: applicant.email || '',
      phone: applicant.phone || '',
      risk_level: applicant.risk_level || 'low',
      notes: applicant.notes || '',
    });
    setLoadingProfile(true);
    try {
      const res = await api.getApplicantProfile(applicant.id);
      setApplicantProfile(res.data);
      if (res.data?.applicant) {
        const a = res.data.applicant;
        setEditForm({
          name: a.name || '',
          email: a.email || '',
          phone: a.phone || '',
          risk_level: a.risk_level || 'low',
          notes: a.notes || '',
        });
      }
    } catch (err) {
      console.warn('Error loading profile:', err);
    } finally {
      setLoadingProfile(false);
    }
  };

  const handleSaveProfile = async () => {
    if (!selectedApplicant) return;
    setSavingProfile(true);
    try {
      const res = await api.updateApplicantProfile(selectedApplicant.id, editForm);
      const updated = res.data.applicant;
      setSelectedApplicant(updated);
      setEditing(false);
      await loadApplicants();
    } catch (err) {
      console.error('Save profile error:', err);
      alert('Failed to update applicant profile: ' + (err.message || 'Server error'));
    } finally {
      setSavingProfile(false);
    }
  };

  const getStatusBadge = (status) => {
    const s = (status || 'pending').toLowerCase();
    if (s === 'verified' || s === 'approved') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-[#EDF4EE] text-[#2E5A36] text-[12px] font-medium">
          <span className="w-1.5 h-1.5 rounded-full bg-[#2E5A36]"></span>
          Verified
        </span>
      );
    }
    if (s === 'rejected') {
      return (
        <span className="inline-flex items-center gap-1.5 px-2.5 py-1 rounded bg-red-50 text-red-700 text-[12px] font-medium border border-red-200">
          <span className="w-1.5 h-1.5 rounded-full bg-red-600"></span>
          Rejected
        </span>
      );
    }
    if (s === 'requires_attention' || s === 'manual_review') {
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

  return (
    <div className="w-full max-w-7xl mx-auto px-6 lg:px-8 py-8 space-y-8">
      
      {/* Header */}
      <header className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-2">
        <div>
          <div className="flex items-center gap-2 mb-1.5 text-[12px] font-semibold tracking-wide">
            <span className="text-[#64748B] uppercase tracking-wider">Directory</span>
            <span className="text-[#CBD5E1]">/</span>
            <span className="text-[#2563EB]">Loan Applicants</span>
          </div>
          <h1 className="font-serif text-[38px] font-bold text-[#0F172A] leading-tight">
            Applicant Profiles<span className="text-[#2563EB]">.</span>
          </h1>
          <p className="text-[15px] text-[#64748B]">
            All registered housing finance loan applicants and their cross-document identity verification records.
          </p>
        </div>

        <button
          onClick={loadApplicants}
          className="inline-flex items-center gap-1.5 px-3.5 py-2 text-[13px] font-medium text-[#0F172A] bg-white border border-[#E2E8F0] rounded-lg hover:bg-[#F8FAFC] transition-colors shadow-xs"
        >
          <span className="material-symbols-outlined text-[17px] text-[#64748B]">refresh</span>
          Refresh List
        </button>
      </header>

      {/* Error state */}
      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-800 text-[13px]">
          {error}
        </div>
      )}

      {/* Filter and Status Bar */}
      <div className="bg-white border border-[#E2E8F0] rounded-xl px-4 py-3 flex flex-wrap items-center justify-between gap-3 shadow-xs">
        <div className="relative flex-1 min-w-[240px] max-w-md">
          <span className="material-symbols-outlined absolute left-2.5 top-1/2 -translate-y-1/2 text-[16px] text-[#94A3B8]">search</span>
          <input
            type="text"
            placeholder="Search by name, reference ID, or email..."
            value={searchTerm}
            onChange={(e) => setSearchTerm(e.target.value)}
            className="w-full bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg pl-8 pr-3 py-1.5 text-[13px] text-[#0F172A] focus:outline-none focus:border-[#2563EB]"
          />
        </div>

        <div className="flex items-center gap-2 flex-wrap">
          {[
            { id: 'all', label: 'All Applicants' },
            { id: 'pending', label: 'Pending Review' },
            { id: 'requires_attention', label: 'Requires Attention' },
            { id: 'verified', label: 'Verified' },
            { id: 'rejected', label: 'Rejected' },
          ].map((tab) => (
            <button
              key={tab.id}
              type="button"
              onClick={() => setStatusFilter(tab.id)}
              className={`px-3 py-1 rounded-lg text-[12px] font-medium transition-colors ${
                statusFilter === tab.id
                  ? 'bg-[#0F172A] text-white'
                  : 'bg-[#F8FAFC] text-[#64748B] hover:text-[#0F172A] border border-[#E2E8F0]'
              }`}
            >
              {tab.label}
            </button>
          ))}
        </div>
      </div>

      {/* Applicants Table */}
      <div className="bg-white border border-[#E2E8F0] rounded-xl overflow-hidden shadow-xs">
        <div className="overflow-x-auto">
          <table className="w-full text-left border-collapse">
            <thead>
              <tr className="bg-[#F8FAFC] border-b border-[#E2E8F0] text-[#64748B] text-[11px] font-bold uppercase tracking-wider">
                <th className="py-3.5 px-5">Applicant Reference</th>
                <th className="py-3.5 px-5">Name</th>
                <th className="py-3.5 px-5">Total Documents</th>
                <th className="py-3.5 px-5">Verification Status</th>
                <th className="py-3.5 px-5">Latest Activity</th>
                <th className="py-3.5 px-5 text-right">Action</th>
              </tr>
            </thead>
            <tbody className="divide-y divide-[#E2E8F0] text-[13px]">
              {loading ? (
                <tr>
                  <td colSpan="6" className="py-8 text-center text-[#64748B]">
                    Loading applicants...
                  </td>
                </tr>
              ) : filteredApplicants.length === 0 ? (
                <tr>
                  <td colSpan="6" className="py-8 text-center text-[#64748B]">
                    No applicants match the selected search or status criteria.
                  </td>
                </tr>
              ) : (
                filteredApplicants.map((a) => (
                  <tr key={a.id} className="hover:bg-[#F8FAFC] transition-colors">
                    <td className="py-3.5 px-5 font-mono text-[12px] text-[#0F172A] font-semibold">
                      #{a.id}
                    </td>
                    <td className="py-3.5 px-5 font-bold text-[#0F172A]">
                      {a.name || <span className="text-amber-800 italic font-medium">Name not detected</span>}
                    </td>
                    <td className="py-3.5 px-5">
                      <span className="inline-flex items-center px-2 py-0.5 rounded bg-slate-100 text-slate-800 font-medium text-[12px]">
                        {a.document_count || 0} document(s)
                      </span>
                    </td>
                    <td className="py-3.5 px-5">
                      {getStatusBadge(a.status)}
                    </td>
                    <td className="py-3.5 px-5 text-[#64748B] text-[12px]">
                      {a.latest_document_date ? new Date(a.latest_document_date).toLocaleDateString() : 'N/A'}
                    </td>
                    <td className="py-3.5 px-5 text-right">
                      <button
                        onClick={() => openProfile(a)}
                        className="text-[#2563EB] hover:text-[#0F172A] font-semibold text-[13px] transition-colors"
                      >
                        Inspect Profile →
                      </button>
                    </td>
                  </tr>
                ))
              )}
            </tbody>
          </table>
        </div>
      </div>

      {/* Applicant Profile Modal / Drawer */}
      {selectedApplicant && (
        <div className="fixed inset-0 z-50 bg-black/40 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl max-w-5xl w-full max-h-[90vh] overflow-y-auto shadow-2xl p-6 space-y-6">
            <div className="flex items-center justify-between pb-3 border-b border-[#E2E8F0]">
              <div>
                <span className="text-[11px] font-mono font-bold text-[#2563EB]">APPLICANT: #{selectedApplicant.id}</span>
                <h3 className="text-[20px] font-bold text-[#0F172A]">{selectedApplicant.name || <span className="text-amber-800 italic font-medium">Name not detected</span>}</h3>
              </div>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setEditing(!editing)}
                  className="inline-flex items-center gap-1 px-3 py-1.5 text-[12px] font-medium text-[#0F172A] bg-[#F8FAFC] hover:bg-[#E2E8F0] border border-[#CBD5E1] rounded-lg transition-colors"
                >
                  <span className="material-symbols-outlined text-[15px]">{editing ? 'close' : 'edit'}</span>
                  {editing ? 'Cancel' : 'Edit Profile'}
                </button>
                <button
                  onClick={() => setSelectedApplicant(null)}
                  className="w-8 h-8 rounded-full bg-[#F8FAFC] hover:bg-[#E2E8F0] flex items-center justify-center text-[#64748B]"
                >
                  <span className="material-symbols-outlined text-[18px]">close</span>
                </button>
              </div>
            </div>

            {/* Rejection Justification Notice */}
            {(selectedApplicant.status === 'rejected' || applicantProfile?.applicant?.status === 'rejected') && (
              <div className="p-4 bg-red-50 border border-red-200 rounded-xl space-y-1">
                <div className="flex items-center gap-2 text-red-800 font-bold text-[13px]">
                  <span className="material-symbols-outlined text-[18px]">cancel</span>
                  <span>Applicant KYC Rejected</span>
                </div>
                <p className="text-[12px] text-red-700">
                  {applicantProfile?.applicant?.notes || selectedApplicant.notes || 'This applicant was rejected by verification officer. Resubmission or escalated review required.'}
                </p>
              </div>
            )}

            {/* Profile Editing Form */}
            {editing && (
              <div className="p-4 bg-blue-50/60 border border-blue-200 rounded-xl space-y-3">
                <h4 className="text-[12px] font-bold text-blue-900 uppercase tracking-wider">Edit Applicant Details</h4>
                <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[13px]">
                  <div>
                    <label className="block text-[11px] font-bold text-slate-700 mb-1">Full Legal Name</label>
                    <input
                      type="text"
                      value={editForm.name}
                      onChange={(e) => setEditForm({ ...editForm, name: e.target.value })}
                      className="w-full px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-slate-900"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-bold text-slate-700 mb-1">Email Address</label>
                    <input
                      type="email"
                      value={editForm.email}
                      onChange={(e) => setEditForm({ ...editForm, email: e.target.value })}
                      className="w-full px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-slate-900"
                      placeholder="applicant@example.com"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-bold text-slate-700 mb-1">Phone Number</label>
                    <input
                      type="text"
                      value={editForm.phone}
                      onChange={(e) => setEditForm({ ...editForm, phone: e.target.value })}
                      className="w-full px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-slate-900"
                      placeholder="+91 98765 43210"
                    />
                  </div>
                  <div>
                    <label className="block text-[11px] font-bold text-slate-700 mb-1">Risk Level</label>
                    <select
                      value={editForm.risk_level}
                      onChange={(e) => setEditForm({ ...editForm, risk_level: e.target.value })}
                      className="w-full px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-slate-900"
                    >
                      <option value="low">Low Risk</option>
                      <option value="medium">Medium Risk</option>
                      <option value="high">High Risk</option>
                    </select>
                  </div>
                </div>
                <div>
                  <label className="block text-[11px] font-bold text-slate-700 mb-1">Verification Officer Notes</label>
                  <textarea
                    rows={2}
                    value={editForm.notes}
                    onChange={(e) => setEditForm({ ...editForm, notes: e.target.value })}
                    className="w-full px-3 py-1.5 bg-white border border-slate-300 rounded-lg text-slate-900"
                    placeholder="Enter compliance or background check notes..."
                  />
                </div>
                <div className="flex justify-end gap-2 pt-1">
                  <button
                    onClick={() => setEditing(false)}
                    className="px-3 py-1.5 text-[12px] font-medium text-slate-700 bg-white border border-slate-300 rounded-lg"
                  >
                    Cancel
                  </button>
                  <button
                    disabled={savingProfile}
                    onClick={handleSaveProfile}
                    className="px-4 py-1.5 text-[12px] font-bold text-white bg-[#2563EB] hover:bg-blue-700 rounded-lg"
                  >
                    {savingProfile ? 'Saving...' : 'Save Profile Changes'}
                  </button>
                </div>
              </div>
            )}

            {loadingProfile ? (
              <div className="p-8 text-center text-[#64748B]">Loading applicant documents and cross-check records...</div>
            ) : !applicantProfile ? (
              <div className="p-8 text-center text-red-600">Could not retrieve profile.</div>
            ) : (
              <div className="space-y-6">
                {/* Structured Comparison Matrix */}
                {applicantProfile.cross_comparison?.matrix ? (
                  <ComparisonMatrix
                    matrix={applicantProfile.cross_comparison.matrix}
                    applicantId={selectedApplicant.id}
                    applicantName={selectedApplicant.name}
                    onNavigateToQueue={(docId) => {
                      setSelectedApplicant(null);
                      onNavigateToQueue(docId);
                    }}
                  />
                ) : applicantProfile.cross_comparison ? (
                  <div className="p-4 bg-[#F8FAFC] border border-[#E2E8F0] rounded-xl space-y-3">
                    <div className="flex items-center justify-between">
                      <h4 className="text-[13px] font-bold uppercase tracking-wider text-[#64748B]">
                        Cross-Document Verification Verdict
                      </h4>
                      <span className={`px-2.5 py-0.5 rounded-full text-[11px] font-bold uppercase ${
                        applicantProfile.cross_comparison.overall_verdict === 'VERIFIED'
                          ? 'bg-emerald-100 text-emerald-800'
                          : 'bg-amber-100 text-amber-800'
                      }`}>
                        {applicantProfile.cross_comparison.overall_verdict}
                      </span>
                    </div>
                    <div className="text-[13px] text-[#0F172A]">
                      {applicantProfile.cross_comparison.summary}
                    </div>
                  </div>
                ) : null}

                {/* Submitted Documents List */}
                <div className="space-y-3">
                  <h4 className="text-[13px] font-bold uppercase tracking-wider text-[#64748B]">
                    Submitted Identity Documents ({applicantProfile.documents?.length || 0})
                  </h4>

                  <div className="space-y-2.5">
                    {(applicantProfile.documents || []).map((doc) => (
                      <div key={doc.id} className="p-3.5 bg-white border border-[#E2E8F0] rounded-xl flex items-center justify-between shadow-xs">
                        <div>
                          <div className="text-[13px] font-bold text-[#0F172A]">{doc.original_filename}</div>
                          <div className="text-[11px] text-[#64748B] font-mono">
                            Type: {(doc.classified_type || doc.document_type || 'unknown').toUpperCase()} | ID: #{doc.id.slice(0, 8)}
                          </div>
                        </div>
                        <button
                          onClick={() => {
                            setSelectedApplicant(null);
                            onNavigateToQueue(doc.id);
                          }}
                          className="px-3 py-1.5 bg-[#0F172A] hover:bg-[#1E293B] text-white rounded-lg text-[12px] font-medium"
                        >
                          Review Document →
                        </button>
                      </div>
                    ))}
                  </div>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

    </div>
  );
}
