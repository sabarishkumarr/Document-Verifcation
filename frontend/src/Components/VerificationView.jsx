import React, { useState, useEffect } from 'react';
import { api } from '../api';
import VisualDocumentWorkspace from './VisualDocumentWorkspace';
import ComparisonMatrix from './ComparisonMatrix';

export default function VerificationView({
  initialApplicantId,
  initialDocId,
  officerName = 'Arjun Mehta',
}) {
  // Queue list state
  const [applicants, setApplicants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);
  const [statusFilter, setStatusFilter] = useState('all');
  const [datasetFilter, setDatasetFilter] = useState('live');
  const [searchTerm, setSearchTerm] = useState('');
  const [showConfidenceDetails, setShowConfidenceDetails] = useState(false);
  const [showMatrixExpanded, setShowMatrixExpanded] = useState(false);

  // Selected Applicant State
  const [selectedApplicantId, setSelectedApplicantId] = useState(null);
  const [applicantProfile, setApplicantProfile] = useState(null);
  const [profileLoading, setProfileLoading] = useState(false);

  // Profile Edit Modal State
  const [isEditingProfile, setIsEditingProfile] = useState(false);
  const [profileForm, setProfileForm] = useState({
    name: '',
    email: '',
    phone: '',
    risk_level: 'low',
    notes: '',
  });
  const [savingProfile, setSavingProfile] = useState(false);

  // Document Inspection Modal State
  const [inspectingDoc, setInspectingDoc] = useState(null);
  const openInspectModal = (doc) => setInspectingDoc(doc);

  // Field Correction Modal State
  const [correctingDoc, setCorrectingDoc] = useState(null);
  const [correctionForm, setCorrectionForm] = useState({
    name: '',
    dob: '',
    id_number: '',
    gender: '',
    father_name: '',
    address: '',
    expiry_date: '',
  });
  const [submittingCorrection, setSubmittingCorrection] = useState(false);

  // Decision Modal State
  const [decisionModal, setDecisionModal] = useState({
    isOpen: false,
    decision: null,
    title: '',
    description: '',
    notes: '',
    requiresNotes: false,
  });
  const [submittingDecision, setSubmittingDecision] = useState(false);

  useEffect(() => {
    loadApplicants();
  }, [datasetFilter, statusFilter]);

  const loadApplicants = async () => {
    setLoading(true);
    setError(null);
    try {
      const res = await api.getApplicants(datasetFilter, statusFilter);
      const list = res.data?.applicants || [];
      setApplicants(list);

      // Handle initial selection
      const targetId = initialApplicantId || initialDocId;
      if (targetId) {
        const found = list.find((a) => a.id === targetId);
        if (found) {
          selectApplicant(found.id);
        } else {
          // Check if targetId is document ID
          try {
            const docRes = await api.getDocument(targetId);
            const docAppId = docRes.data?.document?.applicant_id;
            if (docAppId && list.some((a) => a.id === docAppId)) {
              selectApplicant(docAppId);
            } else if (list.length > 0) {
              selectApplicant(list[0].id);
            }
          } catch (e) {
            if (list.length > 0) selectApplicant(list[0].id);
          }
        }
      } else if (selectedApplicantId) {
        const stillExists = list.find((a) => a.id === selectedApplicantId);
        if (stillExists) {
          selectApplicant(selectedApplicantId);
        } else if (list.length > 0) {
          selectApplicant(list[0].id);
        } else {
          setSelectedApplicantId(null);
          setApplicantProfile(null);
        }
      } else if (list.length > 0) {
        selectApplicant(list[0].id);
      } else {
        setSelectedApplicantId(null);
        setApplicantProfile(null);
      }
    } catch (err) {
      setError(err.message || 'Failed to load applicants.');
    } finally {
      setLoading(false);
    }
  };

  const selectApplicant = async (appId) => {
    setSelectedApplicantId(appId);
    setProfileLoading(true);
    setError(null);
    try {
      const res = await api.getApplicantProfile(appId);
      setApplicantProfile(res.data);
      const app = res.data?.applicant;
      if (app) {
        setProfileForm({
          name: app.name || '',
          email: app.email || '',
          phone: app.phone || '',
          risk_level: app.risk_level || 'low',
          notes: app.notes || '',
        });
      }
    } catch (err) {
      console.error('Failed to load profile:', err);
      setError(`Failed to load profile: ${err.message}`);
    } finally {
      setProfileLoading(false);
    }
  };

  const handleSaveProfile = async (e) => {
    e.preventDefault();
    if (!selectedApplicantId) return;
    setSavingProfile(true);
    setError(null);
    try {
      await api.updateApplicantProfile(selectedApplicantId, profileForm);
      setSuccessMsg('Applicant profile updated successfully.');
      setIsEditingProfile(false);
      await selectApplicant(selectedApplicantId);
      await loadApplicants();
    } catch (err) {
      setError(err.message || 'Failed to update profile.');
    } finally {
      setSavingProfile(false);
    }
  };

  const openCorrectionModal = (doc) => {
    setCorrectingDoc(doc);
    const f = doc.extracted_fields || {};
    setCorrectionForm({
      name: f.name || f.applicant_name || '',
      dob: f.dob || f.date_of_birth || '',
      id_number: f.masked_id || f.id_number || f.pan || f.aadhaar || f.passport_number || f.dl_number || f.voter_id || '',
      gender: f.gender || '',
      father_name: f.father_name || f.guardian_name || '',
      address: f.address || '',
      expiry_date: f.expiry_date || '',
    });
  };

  const handleSaveCorrections = async () => {
    if (!correctingDoc) return;
    setSubmittingCorrection(true);
    setError(null);
    try {
      await api.submitReview(correctingDoc.id, {
        decision: correctingDoc.review_status || 'manual_review',
        edited_fields: correctionForm,
        notes: `Field corrections verified by ${officerName}`,
        officer_name: officerName,
      });
      setSuccessMsg(`Corrections for ${correctingDoc.original_filename} saved.`);
      setCorrectingDoc(null);
      await selectApplicant(selectedApplicantId);
      await loadApplicants();
    } catch (err) {
      setError(err.message || 'Failed to save field corrections.');
    } finally {
      setSubmittingCorrection(false);
    }
  };

  const openDecisionModal = (decision) => {
    let title = '';
    let description = '';
    let requiresNotes = false;

    if (decision === 'verified') {
      title = 'Confirm Applicant KYC Verification';
      description = `Verify KYC for ${applicantProfile?.applicant?.name || selectedApplicantId}. Ensure all document checks agree and confidence meets the required threshold (> 75.0%).`;
    } else if (decision === 'resubmission_requested') {
      title = 'Request Document Resubmission';
      description = `Request applicant ${applicantProfile?.applicant?.name || selectedApplicantId} to resubmit clearer, updated, or missing documents.`;
      requiresNotes = true;
    } else if (decision === 'rejected') {
      title = 'Confirm Applicant KYC Rejection';
      description = `Reject applicant ${applicantProfile?.applicant?.name || selectedApplicantId}. A recorded justification is mandatory for compliance audit trails.`;
      requiresNotes = true;
    } else {
      title = 'Flag for Senior Compliance Review';
      description = `Escalate applicant ${applicantProfile?.applicant?.name || selectedApplicantId} for supervisory audit.`;
    }

    setDecisionModal({
      isOpen: true,
      decision,
      title,
      description,
      notes: '',
      requiresNotes,
    });
  };

  const executeDecision = async () => {
    if (!selectedApplicantId || !decisionModal.decision) return;
    if (decisionModal.requiresNotes && (!decisionModal.notes || !decisionModal.notes.trim())) {
      setError('A justification note is required to complete this decision.');
      return;
    }

    setSubmittingDecision(true);
    setError(null);
    try {
      await api.submitApplicantReview(selectedApplicantId, {
        decision: decisionModal.decision,
        notes: decisionModal.notes,
        officer_name: officerName,
      });

      setSuccessMsg(`Decision '${decisionModal.decision.toUpperCase().replace('_', ' ')}' applied successfully.`);
      setDecisionModal({ isOpen: false, decision: null, title: '', description: '', notes: '', requiresNotes: false });

      await selectApplicant(selectedApplicantId);
      await loadApplicants();
    } catch (err) {
      setError(err.message || 'Failed to apply verification decision.');
    } finally {
      setSubmittingDecision(false);
    }
  };

  // Extract confidence & identity validation data
  const crossComp = applicantProfile?.cross_comparison || {};
  const matrix = crossComp?.matrix || {};
  const confidence = crossComp?.confidence || matrix?.confidence || null;
  const overallConfidence = confidence?.overall_confidence !== undefined ? confidence.overall_confidence : null;
  const isSubmissible = confidence?.is_submissible !== false;
  const identityVal = confidence?.identity_validation || null;
  const hasIdentityMismatch = identityVal?.is_match === false;

  // Determine Verification Gate eligibility
  const getEligibility = () => {
    if (!applicantProfile) return { eligible: false, reason: 'Profile loading...' };
    const docs = applicantProfile.documents || [];
    if (docs.length === 0) return { eligible: false, reason: 'No documents submitted for this applicant.' };

    if (overallConfidence !== null && overallConfidence <= 75.0) {
      return {
        eligible: false,
        reason: `Overall verification confidence is ${overallConfidence}% (minimum > 75.0% required).`,
      };
    }

    if (hasIdentityMismatch) {
      return {
        eligible: false,
        reason: 'Blocking Identity Mismatch: Declared applicant name does not match extracted document identity.',
      };
    }

    if (matrix.rows) {
      const hasExpired = matrix.rows.some((r) => r.attribute_key === 'expiry_date' && r.result_status === 'EXPIRED');
      if (hasExpired) return { eligible: false, reason: 'Contains expired document(s). Expired documents block verification.' };

      const hasNameMismatch = matrix.rows.some((r) => r.attribute_key === 'name' && r.result_status === 'MISMATCH');
      if (hasNameMismatch) return { eligible: false, reason: 'Critical Customer Name mismatch detected across documents.' };

      const hasDobMismatch = matrix.rows.some((r) => r.attribute_key === 'dob' && r.result_status === 'MISMATCH');
      if (hasDobMismatch) return { eligible: false, reason: 'Critical Date of Birth mismatch detected across documents.' };
    }

    return { eligible: true, reason: null };
  };

  const eligibility = getEligibility();

  // Search & Filter
  const filteredApplicants = applicants.filter((app) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    const name = (app.name || '').toLowerCase();
    const id = (app.id || '').toLowerCase();
    const email = (app.email || '').toLowerCase();
    return name.includes(term) || id.includes(term) || email.includes(term);
  });

  const getStatusBadge = (status) => {
    const s = (status || '').toLowerCase().replace(/_/g, ' ');
    if (s === 'verified' || s === 'approved') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
          <span className="material-symbols-outlined text-[13px]">verified</span>
          Verified
        </span>
      );
    }
    if (s === 'requires attention' || s === 'manual review') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-amber-50 text-amber-800 border border-amber-300">
          <span className="material-symbols-outlined text-[13px]">warning</span>
          Requires Attention
        </span>
      );
    }
    if (s === 'resubmission requested') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-indigo-50 text-indigo-700 border border-indigo-200">
          <span className="material-symbols-outlined text-[13px]">replay</span>
          Resubmission
        </span>
      );
    }
    if (s === 'rejected') {
      return (
        <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-red-50 text-red-700 border border-red-200">
          <span className="material-symbols-outlined text-[13px]">cancel</span>
          Rejected
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-slate-100 text-slate-700 border border-slate-300">
        <span className="material-symbols-outlined text-[13px]">hourglass_empty</span>
        Pending
      </span>
    );
  };

  const getRiskBadge = (risk) => {
    const r = (risk || 'low').toLowerCase();
    if (r === 'high') {
      return <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-red-100 text-red-800 border border-red-200">High Risk</span>;
    }
    if (r === 'medium') {
      return <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-amber-100 text-amber-800 border border-amber-200">Med Risk</span>;
    }
    return <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-slate-100 text-slate-700 border border-slate-200">Low Risk</span>;
  };

  return (
    <div className="max-w-[1600px] mx-auto px-4 sm:px-6 lg:px-8 py-6 space-y-6">
      {/* Toast alerts */}
      {successMsg && (
        <div className="bg-emerald-50 border border-emerald-200 text-emerald-800 px-4 py-3 rounded-lg text-sm flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-emerald-600">check_circle</span>
            <span>{successMsg}</span>
          </div>
          <button onClick={() => setSuccessMsg(null)} className="text-emerald-600 hover:text-emerald-800 text-xs font-bold">DISMISS</button>
        </div>
      )}

      {error && (
        <div className="bg-red-50 border border-red-200 text-red-800 px-4 py-3 rounded-lg text-sm flex items-center justify-between">
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-red-600">error</span>
            <span>{error}</span>
          </div>
          <button onClick={() => setError(null)} className="text-red-600 hover:text-red-800 text-xs font-bold">DISMISS</button>
        </div>
      )}

      {/* Top Header Summary */}
      <div className="bg-white border border-[#E2E8F0] rounded-xl p-5 shadow-xs flex flex-col md:flex-row md:items-center justify-between gap-4">
        <div>
          <div className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[#2563EB] text-[22px]">verified_user</span>
            <h1 className="text-xl font-bold text-[#0F172A]">Verification & Compliance Workspace</h1>
            <span className="text-xs bg-blue-50 text-blue-700 border border-blue-200 px-2 py-0.5 rounded-full font-semibold">
              Officer: {officerName}
            </span>
          </div>
          <p className="text-xs text-[#64748B] mt-1">
            Deterministic KYC verification, applicant profile audit, confidence score gate (&gt;75%), and multi-document consistency.
          </p>
        </div>

        {/* Quick Filter Buttons */}
        <div className="flex items-center gap-1.5 flex-wrap">
          {['all', 'pending', 'requires_attention', 'verified', 'rejected'].map((st) => (
            <button
              key={st}
              onClick={() => setStatusFilter(st)}
              className={`px-3 py-1.5 rounded-lg text-xs font-semibold capitalize transition-colors ${
                statusFilter === st
                  ? 'bg-[#0F172A] text-white shadow-xs'
                  : 'bg-[#F8FAFC] text-[#64748B] hover:bg-[#F1F5F9] border border-[#E2E8F0]'
              }`}
            >
              {st.replace('_', ' ')}
            </button>
          ))}
        </div>
      </div>

      {/* Main Two-Pane Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-6 items-start">
        {/* Left Pane: Applicant Queue (4 cols) */}
        <div className="lg:col-span-4 bg-white border border-[#E2E8F0] rounded-xl shadow-xs overflow-hidden flex flex-col h-[820px]">
          {/* Dataset Filter Tabs */}
          <div className="flex items-center gap-1 p-2 bg-[#F1F5F9] border-b border-[#E2E8F0]">
            <button
              onClick={() => setDatasetFilter('live')}
              className={`flex-1 py-1.5 px-2 rounded-lg text-[11px] font-semibold transition-colors text-center ${
                datasetFilter === 'live'
                  ? 'bg-white text-[#0F172A] shadow-2xs font-bold border border-[#CBD5E1]'
                  : 'text-[#64748B] hover:text-[#0F172A]'
              }`}
            >
              Operational
            </button>
            <button
              onClick={() => setDatasetFilter('synthetic')}
              className={`flex-1 py-1.5 px-2 rounded-lg text-[11px] font-semibold transition-colors text-center ${
                datasetFilter === 'synthetic'
                  ? 'bg-white text-[#0F172A] shadow-2xs font-bold border border-[#CBD5E1]'
                  : 'text-[#64748B] hover:text-[#0F172A]'
              }`}
            >
              Synthetic Fixtures
            </button>
            <button
              onClick={() => setDatasetFilter('all')}
              className={`flex-1 py-1.5 px-2 rounded-lg text-[11px] font-semibold transition-colors text-center ${
                datasetFilter === 'all'
                  ? 'bg-white text-[#0F172A] shadow-2xs font-bold border border-[#CBD5E1]'
                  : 'text-[#64748B] hover:text-[#0F172A]'
              }`}
            >
              All
            </button>
          </div>

          {/* Search bar */}
          <div className="p-3 border-b border-[#E2E8F0] bg-[#F8FAFC]">
            <div className="relative">
              <span className="material-symbols-outlined absolute left-3 top-2.5 text-slate-400 text-[18px]">search</span>
              <input
                type="text"
                placeholder="Search by name, ID, or email..."
                value={searchTerm}
                onChange={(e) => setSearchTerm(e.target.value)}
                className="w-full bg-white border border-[#CBD5E1] rounded-lg pl-9 pr-3 py-2 text-xs text-[#0F172A] focus:outline-none focus:border-[#2563EB]"
              />
            </div>
            <div className="flex items-center justify-between text-[11px] text-[#64748B] mt-2 px-1">
              <span>{filteredApplicants.length} applicants listed</span>
              <button onClick={loadApplicants} className="text-[#2563EB] hover:underline flex items-center gap-0.5">
                <span className="material-symbols-outlined text-[13px]">refresh</span> Refresh
              </button>
            </div>
          </div>

          {/* Applicant list scrollable */}
          <div className="flex-1 overflow-y-auto divide-y divide-[#E2E8F0]">
            {loading ? (
              <div className="p-8 text-center text-xs text-[#64748B]">Loading queue...</div>
            ) : filteredApplicants.length === 0 ? (
              <div className="p-8 text-center text-xs text-[#64748B]">No applicants match criteria.</div>
            ) : (
              filteredApplicants.map((app) => {
                const isSelected = selectedApplicantId === app.id;
                const isProvisional = app.is_provisional || !app.name || !app.name.trim();
                const displayName = app.display_name || app.name || `Provisional Applicant (${app.id})`;
                return (
                  <div
                    key={app.id}
                    onClick={() => selectApplicant(app.id)}
                    className={`p-3.5 cursor-pointer transition-colors ${
                      isSelected
                        ? 'bg-blue-50/70 border-l-4 border-l-[#2563EB]'
                        : 'hover:bg-[#F8FAFC] border-l-4 border-l-transparent'
                    }`}
                  >
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-1.5 min-w-0">
                        <span className="font-bold text-xs text-[#0F172A] truncate" title={displayName}>
                          {displayName}
                        </span>
                        {isProvisional && (
                          <span className="px-1.5 py-0.2 rounded text-[9px] font-semibold bg-amber-50 text-amber-700 border border-amber-200 shrink-0">
                            Provisional
                          </span>
                        )}
                      </div>
                      {getStatusBadge(app.status)}
                    </div>
                    <div className="flex items-center justify-between gap-2 mt-1.5 text-[11px] text-[#64748B]">
                      <span className="font-mono text-[10px]">{app.id}</span>
                      <div className="flex items-center gap-1.5">
                        {getRiskBadge(app.risk_level)}
                        <span className="bg-slate-100 text-slate-700 px-1.5 py-0.5 rounded text-[10px] font-semibold">
                          {app.document_count || 0} doc{app.document_count !== 1 ? 's' : ''}
                        </span>
                      </div>
                    </div>
                    {app.latest_document_date && (
                      <div className="text-[10px] text-slate-400 mt-1 flex items-center gap-1">
                        <span className="material-symbols-outlined text-[12px]">schedule</span>
                        Updated {new Date(app.latest_document_date).toLocaleDateString()}
                      </div>
                    )}
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* Right Pane: Review & Verification Details (8 cols) */}
        <div className="lg:col-span-8 space-y-6">
          {profileLoading ? (
            <div className="bg-white border border-[#E2E8F0] rounded-xl p-12 text-center text-xs text-[#64748B]">
              Loading applicant profile & verification matrix...
            </div>
          ) : !applicantProfile ? (
            <div className="bg-white border border-[#E2E8F0] rounded-xl p-12 text-center text-xs text-[#64748B]">
              Select an applicant from the queue to inspect records and perform verification.
            </div>
          ) : (
            <>
              {/* Applicant Profile Card */}
              <div className="bg-white border border-[#E2E8F0] rounded-xl p-5 shadow-xs space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#E2E8F0] pb-4">
                  <div>
                    <div className="flex items-center gap-2">
                      <h2 className="text-lg font-bold text-[#0F172A]">
                        {applicantProfile.applicant?.name || selectedApplicantId}
                      </h2>
                      <span className="text-xs font-mono text-[#64748B] bg-slate-100 px-2 py-0.5 rounded">
                        {applicantProfile.applicant?.id}
                      </span>
                      {getStatusBadge(applicantProfile.applicant?.status)}
                    </div>
                    <p className="text-xs text-[#64748B] mt-0.5">
                      Created: {applicantProfile.applicant?.created_at ? new Date(applicantProfile.applicant.created_at).toLocaleString() : 'N/A'}
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <button
                      onClick={() => setIsEditingProfile(!isEditingProfile)}
                      className="px-3 py-1.5 bg-[#F8FAFC] hover:bg-[#F1F5F9] text-[#0F172A] border border-[#CBD5E1] rounded-lg text-xs font-semibold flex items-center gap-1.5 transition-colors"
                    >
                      <span className="material-symbols-outlined text-[15px]">edit</span>
                      {isEditingProfile ? 'Cancel Edit' : 'Edit Profile'}
                    </button>
                  </div>
                </div>

                {/* Profile Edit Form Drawer/Inline */}
                {isEditingProfile && (
                  <form onSubmit={handleSaveProfile} className="bg-[#F8FAFC] border border-[#CBD5E1] rounded-xl p-4 space-y-3">
                    <h4 className="text-xs font-bold text-[#0F172A] uppercase tracking-wider">Update Applicant Information</h4>
                    <div className="grid grid-cols-1 sm:grid-cols-2 gap-3">
                      <div>
                        <label className="block text-[11px] font-semibold text-[#64748B] mb-1">Full Name *</label>
                        <input
                          type="text"
                          required
                          value={profileForm.name}
                          onChange={(e) => setProfileForm({ ...profileForm, name: e.target.value })}
                          className="w-full bg-white border border-[#CBD5E1] rounded px-3 py-1.5 text-xs text-[#0F172A]"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-semibold text-[#64748B] mb-1">Email Address</label>
                        <input
                          type="email"
                          value={profileForm.email}
                          onChange={(e) => setProfileForm({ ...profileForm, email: e.target.value })}
                          className="w-full bg-white border border-[#CBD5E1] rounded px-3 py-1.5 text-xs text-[#0F172A]"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-semibold text-[#64748B] mb-1">Phone Number</label>
                        <input
                          type="text"
                          value={profileForm.phone}
                          onChange={(e) => setProfileForm({ ...profileForm, phone: e.target.value })}
                          className="w-full bg-white border border-[#CBD5E1] rounded px-3 py-1.5 text-xs text-[#0F172A]"
                        />
                      </div>
                      <div>
                        <label className="block text-[11px] font-semibold text-[#64748B] mb-1">Risk Profile</label>
                        <select
                          value={profileForm.risk_level}
                          onChange={(e) => setProfileForm({ ...profileForm, risk_level: e.target.value })}
                          className="w-full bg-white border border-[#CBD5E1] rounded px-3 py-1.5 text-xs text-[#0F172A]"
                        >
                          <option value="low">Low Risk</option>
                          <option value="medium">Medium Risk</option>
                          <option value="high">High Risk</option>
                        </select>
                      </div>
                    </div>
                    <div>
                      <label className="block text-[11px] font-semibold text-[#64748B] mb-1">Officer Notes</label>
                      <textarea
                        rows="2"
                        value={profileForm.notes}
                        onChange={(e) => setProfileForm({ ...profileForm, notes: e.target.value })}
                        className="w-full bg-white border border-[#CBD5E1] rounded px-3 py-1.5 text-xs text-[#0F172A]"
                        placeholder="Internal compliance notes..."
                      />
                    </div>
                    <div className="flex justify-end gap-2 pt-2">
                      <button
                        type="button"
                        onClick={() => setIsEditingProfile(false)}
                        className="px-3 py-1.5 bg-white border border-[#CBD5E1] rounded text-xs font-semibold text-[#64748B]"
                      >
                        Cancel
                      </button>
                      <button
                        type="submit"
                        disabled={savingProfile}
                        className="px-4 py-1.5 bg-[#2563EB] hover:bg-blue-700 text-white rounded text-xs font-semibold disabled:opacity-50"
                      >
                        {savingProfile ? 'Saving...' : 'Save Profile'}
                      </button>
                    </div>
                  </form>
                )}

                {/* Profile Readonly Meta Grid */}
                <div className="grid grid-cols-2 sm:grid-cols-4 gap-4 text-xs">
                  <div>
                    <span className="text-[#64748B] block text-[11px]">Email</span>
                    <span className="font-semibold text-[#0F172A]">{applicantProfile.applicant?.email || 'Not specified'}</span>
                  </div>
                  <div>
                    <span className="text-[#64748B] block text-[11px]">Phone</span>
                    <span className="font-semibold text-[#0F172A]">{applicantProfile.applicant?.phone || 'Not specified'}</span>
                  </div>
                  <div>
                    <span className="text-[#64748B] block text-[11px]">Risk Level</span>
                    <span className="font-semibold text-[#0F172A]">{getRiskBadge(applicantProfile.applicant?.risk_level)}</span>
                  </div>
                  <div>
                    <span className="text-[#64748B] block text-[11px]">Total Documents</span>
                    <span className="font-semibold text-[#0F172A]">{applicantProfile.documents?.length || 0} registered</span>
                  </div>
                </div>
              </div>

              {/* Confidence Score & Submission Gate Gauge */}
              <div className="bg-white border border-[#E2E8F0] rounded-xl p-5 shadow-xs space-y-4">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 border-b border-[#E2E8F0] pb-3">
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined text-[#2563EB]">analytics</span>
                    <h3 className="text-sm font-bold text-[#0F172A]">Verification Confidence & Submission Gate</h3>
                  </div>
                  <div className="flex items-center gap-2">
                    <span className="text-xs text-[#64748B]">Required Threshold:</span>
                    <span className="text-xs font-bold text-slate-800 bg-slate-100 border border-slate-200 px-2 py-0.5 rounded">
                      &gt; 75.0%
                    </span>
                  </div>
                </div>

                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-5 p-4 bg-[#F8FAFC] border border-[#E2E8F0] rounded-xl">
                  {/* Gauge score visualization */}
                  <div className="flex items-center gap-4">
                    <div
                      className={`w-20 h-20 rounded-full border-4 flex items-center justify-center transition-all shrink-0 ${
                        overallConfidence === null
                          ? 'border-slate-200 text-slate-400'
                          : overallConfidence > 75.0
                          ? 'border-emerald-500 text-emerald-700 bg-emerald-50/40'
                          : overallConfidence >= 50.0
                          ? 'border-amber-500 text-amber-700 bg-amber-50/40'
                          : 'border-red-500 text-red-700 bg-red-50/40'
                      }`}
                    >
                      <div className="text-center">
                        <span className="text-xl font-black block leading-none">
                          {overallConfidence !== null ? `${overallConfidence}%` : 'N/A'}
                        </span>
                      </div>
                    </div>

                    <div>
                      <div className="flex items-center gap-2">
                        <span className="text-sm font-bold text-[#0F172A]">Overall Confidence Score</span>
                        {overallConfidence !== null && overallConfidence > 75.0 ? (
                          <span className="inline-flex items-center gap-1 text-[11px] font-bold text-emerald-700 bg-emerald-100 px-2 py-0.5 rounded-full">
                            <span className="material-symbols-outlined text-[13px]">check_circle</span>
                            Verification Eligible
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-[11px] font-bold text-red-700 bg-red-100 px-2 py-0.5 rounded-full">
                            <span className="material-symbols-outlined text-[13px]">lock</span>
                            Submission Locked
                          </span>
                        )}
                      </div>
                      <p className="text-xs text-[#64748B] mt-1">
                        {overallConfidence !== null && overallConfidence > 75.0
                          ? 'Applicant satisfies confidence threshold (>75.0%). Ready for officer decision.'
                          : 'Confidence score is below the 75.0% threshold required for approval.'}
                      </p>
                    </div>
                  </div>

                  {/* Toggle verification details */}
                  <button
                    onClick={() => setShowConfidenceDetails(!showConfidenceDetails)}
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 rounded-lg border border-[#CBD5E1] bg-white hover:bg-slate-50 text-[12px] font-semibold text-[#0F172A] transition-colors shrink-0 shadow-2xs"
                  >
                    <span className="material-symbols-outlined text-[15px] text-[#2563EB]">
                      {showConfidenceDetails ? 'expand_less' : 'tune'}
                    </span>
                    {showConfidenceDetails ? 'Hide Verification Details' : 'View Verification Details'}
                  </button>
                </div>

                {/* Blocking Gate Warning Alert */}
                {!eligibility.eligible && (
                  <div className="p-3.5 bg-red-50 border border-red-200 rounded-lg flex items-start gap-3 text-xs text-red-800">
                    <span className="material-symbols-outlined text-red-600 text-lg flex-shrink-0 mt-0.5">gpp_bad</span>
                    <div className="space-y-1">
                      <span className="font-bold block">APPROVAL GATE ACTIVE — SUBMISSION LOCKED</span>
                      <p>{eligibility.reason}</p>
                      {confidence?.corrective_actions && confidence.corrective_actions.length > 0 && (
                        <div className="mt-1 pt-1 border-t border-red-200 text-[11px]">
                          <strong className="text-red-900">Recommended Corrective Actions: </strong>
                          {confidence.corrective_actions.join('; ')}
                        </div>
                      )}
                    </div>
                  </div>
                )}

                {/* Expandable Verification Components & Math Details */}
                {showConfidenceDetails && (
                  <div className="pt-3 border-t border-[#E2E8F0] space-y-3">
                    <h4 className="text-xs font-bold text-[#0F172A] uppercase tracking-wider">
                      Confidence Components &amp; Factor Breakdown
                    </h4>
                    <div className="grid grid-cols-1 sm:grid-cols-3 gap-3 text-center">
                      <div className="bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg p-3">
                        <span className="text-[10px] uppercase font-bold text-slate-500 block">Identity (C_id)</span>
                        <span className="text-base font-bold text-[#0F172A]">
                          {confidence?.identity_validation?.score !== undefined
                            ? `${confidence.identity_validation.score}%`
                            : confidence?.confidence_components?.identity !== undefined
                            ? `${confidence.confidence_components.identity}%`
                            : 'N/A'}
                        </span>
                        <span className="text-[10px] text-slate-400 block mt-0.5">Declared vs Document Name</span>
                      </div>
                      <div className="bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg p-3">
                        <span className="text-[10px] uppercase font-bold text-slate-500 block">Consistency (C_comp)</span>
                        <span className="text-base font-bold text-[#0F172A]">
                          {confidence?.attribute_comparison_confidence !== undefined
                            ? `${confidence.attribute_comparison_confidence}%`
                            : confidence?.confidence_components?.comparison !== undefined
                            ? `${confidence.confidence_components.comparison}%`
                            : 'N/A'}
                        </span>
                        <span className="text-[10px] text-slate-400 block mt-0.5">Cross-Document Concordance</span>
                      </div>
                      <div className="bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg p-3">
                        <span className="text-[10px] uppercase font-bold text-slate-500 block">Extraction (C_ext)</span>
                        <span className="text-base font-bold text-[#0F172A]">
                          {confidence?.document_extraction_confidence !== undefined
                            ? `${confidence.document_extraction_confidence}%`
                            : confidence?.confidence_components?.extraction !== undefined
                            ? `${confidence.confidence_components.extraction}%`
                            : 'N/A'}
                        </span>
                        <span className="text-[10px] text-slate-400 block mt-0.5">OCR Quality &amp; Completeness</span>
                      </div>
                    </div>

                    {/* Influencing factors summary */}
                    {confidence?.factors && confidence.factors.length > 0 && (
                      <div className="bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg p-3 text-xs space-y-1">
                        <span className="text-[11px] font-bold text-slate-700 block">Scoring Factors:</span>
                        <div className="max-h-28 overflow-y-auto space-y-1 pr-1">
                          {confidence.factors.map((fact, idx) => (
                            <div key={idx} className="flex items-start gap-1.5 text-[11px] text-slate-600">
                              <span className="text-blue-500 font-bold">•</span>
                              <span>{fact}</span>
                            </div>
                          ))}
                        </div>
                      </div>
                    )}
                  </div>
                )}
              </div>

              {/* Registered Documents List with Secure Inspect */}
              <div className="bg-white border border-[#E2E8F0] rounded-xl p-5 shadow-xs space-y-4">
                <div className="flex items-center justify-between border-b border-[#E2E8F0] pb-3">
                  <div className="flex items-center gap-2">
                    <span className="material-symbols-outlined text-[#2563EB]">folder_shared</span>
                    <h3 className="text-sm font-bold text-[#0F172A]">Submitted Documents for Verification</h3>
                  </div>
                  <span className="text-xs text-[#64748B]">
                    {applicantProfile.documents?.length || 0} document(s) uploaded
                  </span>
                </div>

                <div className="overflow-x-auto">
                  <table className="w-full text-left text-xs border-collapse">
                    <thead>
                      <tr className="border-b border-[#E2E8F0] bg-[#F8FAFC] text-[#64748B] uppercase tracking-wider text-[10px] font-bold">
                        <th className="py-2.5 px-3">Document</th>
                        <th className="py-2.5 px-3">Type</th>
                        <th className="py-2.5 px-3">Status</th>
                        <th className="py-2.5 px-3">Uploaded</th>
                        <th className="py-2.5 px-3 text-right">Actions</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#E2E8F0]">
                      {applicantProfile.documents?.map((doc) => (
                        <tr key={doc.id} className="hover:bg-[#F8FAFC] transition-colors">
                          <td className="py-3 px-3 font-semibold text-[#0F172A]">
                            <div className="flex items-center gap-2">
                              <span className="material-symbols-outlined text-slate-400 text-[18px]">description</span>
                              <span className="truncate max-w-[200px]" title={doc.original_filename}>{doc.original_filename}</span>
                            </div>
                          </td>
                          <td className="py-3 px-3">
                            <span className="bg-blue-50 text-blue-700 border border-blue-200 px-2 py-0.5 rounded text-[11px] font-bold">
                              {doc.document_type_name || doc.document_type}
                            </span>
                          </td>
                          <td className="py-3 px-3">
                            {getStatusBadge(doc.review_status || doc.processing_status)}
                          </td>
                          <td className="py-3 px-3 text-[#64748B] text-[11px]">
                            {doc.created_at ? new Date(doc.created_at).toLocaleDateString() : 'N/A'}
                          </td>
                          <td className="py-3 px-3 text-right space-x-1.5">
                            <button
                              onClick={() => openInspectModal(doc)}
                              title="Open secure protected document inspection viewer"
                              className="px-2.5 py-1 bg-[#0F172A] hover:bg-[#1E293B] text-white rounded text-[11px] font-semibold inline-flex items-center gap-1 transition-colors"
                            >
                              <span className="material-symbols-outlined text-[13px]">visibility</span>
                              Inspect
                            </button>
                            <button
                              onClick={() => openCorrectionModal(doc)}
                              title="Edit extracted fields"
                              className="px-2.5 py-1 bg-white hover:bg-slate-100 text-slate-700 border border-slate-300 rounded text-[11px] font-semibold inline-flex items-center gap-1 transition-colors"
                            >
                              <span className="material-symbols-outlined text-[13px]">tune</span>
                              Correct
                            </button>
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              {/* Cross-Document Comparison Matrix Accordion */}
              <div className="bg-white border border-[#E2E8F0] rounded-xl shadow-xs overflow-hidden">
                <div
                  className="p-4 bg-white flex flex-col sm:flex-row sm:items-center justify-between gap-3 cursor-pointer select-none hover:bg-[#F8FAFC] transition-colors"
                  onClick={() => setShowMatrixExpanded(!showMatrixExpanded)}
                >
                  <div className="flex items-center gap-2 flex-wrap">
                    <span className="material-symbols-outlined text-[#2563EB] text-[20px]">table_chart</span>
                    <h3 className="text-sm font-bold text-[#0F172A]">Cross-Document Comparison Matrix</h3>
                    <span className="text-xs text-[#64748B]">({matrix.rows?.length || 0} attributes evaluated)</span>
                    {matrix.overall_verdict && (
                      <span className={`px-2 py-0.5 rounded-full text-[10px] font-bold uppercase tracking-wider ${
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
                  <button
                    type="button"
                    className="inline-flex items-center gap-1.5 px-3 py-1.5 bg-[#F8FAFC] hover:bg-[#F1F5F9] text-[#0F172A] border border-[#CBD5E1] rounded-lg text-xs font-semibold self-start sm:self-auto transition-colors"
                  >
                    <span>{showMatrixExpanded ? 'Hide Matrix' : 'View Full Comparison Matrix'}</span>
                    <span className="material-symbols-outlined text-[15px]">
                      {showMatrixExpanded ? 'expand_less' : 'expand_more'}
                    </span>
                  </button>
                </div>

                {showMatrixExpanded && (
                  <div className="border-t border-[#E2E8F0]">
                    <ComparisonMatrix
                      matrix={matrix}
                      applicantId={selectedApplicantId}
                      applicantName={applicantProfile.applicant?.name}
                    />
                  </div>
                )}
              </div>

              {/* Officer Verification Decision Action Bar */}
              <div className="bg-white border border-[#E2E8F0] rounded-xl p-5 shadow-xs space-y-3">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <h3 className="text-sm font-bold text-[#0F172A]">Compliance Officer Final Verification</h3>
                    <p className="text-xs text-[#64748B]">
                      Deterministic submission decision recorded in PostgreSQL audit logs.
                    </p>
                  </div>

                  <div className="flex items-center gap-2 flex-wrap">
                    <button
                      onClick={() => openDecisionModal('verified')}
                      disabled={!eligibility.eligible}
                      title={!eligibility.eligible ? eligibility.reason : 'Approve applicant KYC'}
                      className="px-4 py-2 bg-emerald-600 hover:bg-emerald-700 text-white rounded-lg text-xs font-bold flex items-center gap-1.5 transition-colors disabled:opacity-40 disabled:cursor-not-allowed shadow-xs"
                    >
                      <span className="material-symbols-outlined text-[16px]">verified</span>
                      Approve & Verify KYC
                    </button>

                    <button
                      onClick={() => openDecisionModal('resubmission_requested')}
                      className="px-3.5 py-2 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-xs font-bold flex items-center gap-1.5 transition-colors shadow-xs"
                    >
                      <span className="material-symbols-outlined text-[16px]">replay</span>
                      Request Resubmission
                    </button>

                    <button
                      onClick={() => openDecisionModal('manual_review')}
                      className="px-3.5 py-2 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-xs font-bold flex items-center gap-1.5 transition-colors shadow-xs"
                    >
                      <span className="material-symbols-outlined text-[16px]">flag</span>
                      Flag for Review
                    </button>

                    <button
                      onClick={() => openDecisionModal('rejected')}
                      className="px-3.5 py-2 bg-red-600 hover:bg-red-700 text-white rounded-lg text-xs font-bold flex items-center gap-1.5 transition-colors shadow-xs"
                    >
                      <span className="material-symbols-outlined text-[16px]">cancel</span>
                      Reject KYC
                    </button>
                  </div>
                </div>

                {!eligibility.eligible && (
                  <div className="text-[11px] text-red-600 font-medium">
                    * Approval locked: {eligibility.reason}
                  </div>
                )}
              </div>
            </>
          )}
        </div>
      </div>

      {/* Decision Modal */}
      {decisionModal.isOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full p-6 space-y-4 border border-[#E2E8F0]">
            <div className="flex items-center justify-between border-b border-[#E2E8F0] pb-3">
              <h3 className="text-base font-bold text-[#0F172A]">{decisionModal.title}</h3>
              <button
                onClick={() => setDecisionModal({ ...decisionModal, isOpen: false })}
                className="text-slate-400 hover:text-slate-600"
              >
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>

            <p className="text-xs text-[#64748B]">{decisionModal.description}</p>

            <div>
              <label className="block text-xs font-semibold text-[#0F172A] mb-1">
                Audit Trail Justification Notes {decisionModal.requiresNotes && <span className="text-red-500">*</span>}
              </label>
              <textarea
                rows="3"
                value={decisionModal.notes}
                onChange={(e) => setDecisionModal({ ...decisionModal, notes: e.target.value })}
                placeholder="Enter justification or reason for this decision..."
                className="w-full bg-[#F8FAFC] border border-[#CBD5E1] rounded-lg p-2.5 text-xs text-[#0F172A] focus:outline-none focus:border-[#2563EB]"
              />
            </div>

            <div className="bg-slate-50 border border-slate-200 rounded p-2.5 text-[11px] text-slate-600">
              Recorded Compliance Officer: <strong>{officerName}</strong>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setDecisionModal({ ...decisionModal, isOpen: false })}
                className="px-4 py-2 bg-white border border-[#CBD5E1] rounded-lg text-xs font-semibold text-[#64748B] hover:bg-slate-50"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={submittingDecision}
                onClick={executeDecision}
                className="px-4 py-2 bg-[#2563EB] hover:bg-blue-700 text-white rounded-lg text-xs font-bold disabled:opacity-50"
              >
                {submittingDecision ? 'Submitting...' : 'Confirm Decision'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Field Correction Modal */}
      {correctingDoc && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-xl w-full p-6 space-y-4 border border-[#E2E8F0]">
            <div className="flex items-center justify-between border-b border-[#E2E8F0] pb-3">
              <h3 className="text-base font-bold text-[#0F172A]">Correct Extracted Document Fields</h3>
              <button onClick={() => setCorrectingDoc(null)} className="text-slate-400 hover:text-slate-600">
                <span className="material-symbols-outlined">close</span>
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-xs">
              <div>
                <label className="block text-[11px] font-semibold text-[#64748B] mb-1">Name</label>
                <input
                  type="text"
                  value={correctionForm.name}
                  onChange={(e) => setCorrectionForm({ ...correctionForm, name: e.target.value })}
                  className="w-full bg-[#F8FAFC] border border-[#CBD5E1] rounded px-3 py-1.5 text-xs text-[#0F172A]"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-[#64748B] mb-1">Date of Birth</label>
                <input
                  type="text"
                  value={correctionForm.dob}
                  onChange={(e) => setCorrectionForm({ ...correctionForm, dob: e.target.value })}
                  className="w-full bg-[#F8FAFC] border border-[#CBD5E1] rounded px-3 py-1.5 text-xs text-[#0F172A]"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-[#64748B] mb-1">ID Number</label>
                <input
                  type="text"
                  value={correctionForm.id_number}
                  onChange={(e) => setCorrectionForm({ ...correctionForm, id_number: e.target.value })}
                  className="w-full bg-[#F8FAFC] border border-[#CBD5E1] rounded px-3 py-1.5 text-xs text-[#0F172A]"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-[#64748B] mb-1">Gender</label>
                <input
                  type="text"
                  value={correctionForm.gender}
                  onChange={(e) => setCorrectionForm({ ...correctionForm, gender: e.target.value })}
                  className="w-full bg-[#F8FAFC] border border-[#CBD5E1] rounded px-3 py-1.5 text-xs text-[#0F172A]"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-[#64748B] mb-1">Father / Guardian Name</label>
                <input
                  type="text"
                  value={correctionForm.father_name}
                  onChange={(e) => setCorrectionForm({ ...correctionForm, father_name: e.target.value })}
                  className="w-full bg-[#F8FAFC] border border-[#CBD5E1] rounded px-3 py-1.5 text-xs text-[#0F172A]"
                />
              </div>
              <div>
                <label className="block text-[11px] font-semibold text-[#64748B] mb-1">Expiry Date</label>
                <input
                  type="text"
                  value={correctionForm.expiry_date}
                  onChange={(e) => setCorrectionForm({ ...correctionForm, expiry_date: e.target.value })}
                  className="w-full bg-[#F8FAFC] border border-[#CBD5E1] rounded px-3 py-1.5 text-xs text-[#0F172A]"
                />
              </div>
              <div className="sm:col-span-2">
                <label className="block text-[11px] font-semibold text-[#64748B] mb-1">Address</label>
                <textarea
                  rows="2"
                  value={correctionForm.address}
                  onChange={(e) => setCorrectionForm({ ...correctionForm, address: e.target.value })}
                  className="w-full bg-[#F8FAFC] border border-[#CBD5E1] rounded px-3 py-1.5 text-xs text-[#0F172A]"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                type="button"
                onClick={() => setCorrectingDoc(null)}
                className="px-4 py-2 bg-white border border-[#CBD5E1] rounded-lg text-xs font-semibold text-[#64748B]"
              >
                Cancel
              </button>
              <button
                type="button"
                disabled={submittingCorrection}
                onClick={handleSaveCorrections}
                className="px-4 py-2 bg-[#2563EB] hover:bg-blue-700 text-white rounded-lg text-xs font-bold disabled:opacity-50"
              >
                {submittingCorrection ? 'Saving...' : 'Save Field Corrections'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* Secure Protected Document Inspection Workspace Modal */}
      {inspectingDoc && (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-7xl w-full h-[90vh] overflow-hidden flex flex-col border border-[#CBD5E1]">
            <div className="p-3 bg-[#0F172A] text-white flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="material-symbols-outlined text-blue-400">policy</span>
                <span className="text-xs font-bold">Secure Inspection Workspace</span>
                <span className="text-slate-400 text-xs">|</span>
                <span className="text-xs text-slate-300 font-mono">{inspectingDoc.original_filename}</span>
              </div>
              <button
                onClick={() => setInspectingDoc(null)}
                className="text-slate-400 hover:text-white flex items-center gap-1 text-xs"
              >
                <span className="material-symbols-outlined text-[18px]">close</span>
                Close
              </button>
            </div>
            <div className="flex-1 overflow-hidden">
              <VisualDocumentWorkspace
                documentId={inspectingDoc.id}
                onClose={() => setInspectingDoc(null)}
              />
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
