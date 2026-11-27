import React, { useState, useEffect } from 'react';
import { api } from '../api';
import VisualDocumentWorkspace from './VisualDocumentWorkspace';

export default function VerificationQueueView({ initialApplicantId, initialDocId, officerName = 'Arjun Mehta' }) {
  // Queue list state (Applicants)
  const [applicants, setApplicants] = useState([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [successMsg, setSuccessMsg] = useState(null);
  const [statusFilter, setStatusFilter] = useState('all');
  const [searchTerm, setSearchTerm] = useState('');

  // Selected Applicant State
  const [selectedApplicantId, setSelectedApplicantId] = useState(null);
  const [applicantProfile, setApplicantProfile] = useState(null);
  const [profileLoading, setProfileLoading] = useState(false);

  // Document Inspection Modal State
  const [inspectingDoc, setInspectingDoc] = useState(null);

  // Field Correction Modal State (Optional editing)
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

  // Applicant Decision Dialog State
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
    loadQueue();
  }, [statusFilter]);

  const loadQueue = async () => {
    setLoading(true);
    setError(null);
    try {
      const appRes = await api.getApplicants('all', statusFilter);
      const appList = appRes.data?.applicants || [];
      setApplicants(appList);

      // Auto-select initial or first applicant
      const targetId = initialApplicantId || initialDocId;
      if (targetId) {
        const found = appList.find((a) => a.id === targetId);
        if (found) {
          selectApplicant(found.id);
        } else {
          // If targetId is a document ID, attempt to lookup document's applicant
          try {
            const docRes = await api.getDocument(targetId);
            const docAppId = docRes.data?.document?.applicant_id;
            if (docAppId && appList.find((a) => a.id === docAppId)) {
              selectApplicant(docAppId);
            } else if (appList.length > 0) {
              selectApplicant(appList[0].id);
            }
          } catch (e) {
            if (appList.length > 0) {
              selectApplicant(appList[0].id);
            }
          }
        }
      } else if (selectedApplicantId) {
        const stillExists = appList.find((a) => a.id === selectedApplicantId);
        if (stillExists) {
          selectApplicant(selectedApplicantId);
        } else if (appList.length > 0) {
          selectApplicant(appList[0].id);
        } else {
          setSelectedApplicantId(null);
          setApplicantProfile(null);
        }
      } else if (appList.length > 0) {
        selectApplicant(appList[0].id);
      } else {
        setSelectedApplicantId(null);
        setApplicantProfile(null);
      }
    } catch (err) {
      setError(err.message || 'Failed to load applicant verification queue.');
    } finally {
      setLoading(false);
    }
  };

  const selectApplicant = async (appId) => {
    setSelectedApplicantId(appId);
    setProfileLoading(true);
    setError(null);
    try {
      const profRes = await api.getApplicantProfile(appId);
      setApplicantProfile(profRes.data);
    } catch (err) {
      console.error('Failed to load applicant profile:', err);
      setError(`Failed to load profile for applicant ${appId}: ${err.message}`);
    } finally {
      setProfileLoading(false);
    }
  };

  const selectUnassignedView = () => {
    setIsViewingUnassigned(true);
    setSelectedApplicantId(null);
    setApplicantProfile(null);
  };

  // Open Document Inspection Modal
  const openInspectModal = (doc) => {
    setInspectingDoc(doc);
  };

  // Open Field Correction Modal
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

  // Save Field Corrections for a Document
  const handleSaveCorrections = async () => {
    if (!correctingDoc) return;
    setSubmittingCorrection(true);
    setError(null);
    try {
      await api.submitReview(correctingDoc.id, {
        decision: correctingDoc.review_status || 'manual_review',
        edited_fields: correctionForm,
        notes: `Field corrections by ${officerName}`,
        officer_name: officerName,
      });

      setSuccessMsg(`Field corrections for ${correctingDoc.original_filename} saved successfully.`);
      setCorrectingDoc(null);

      // Refresh applicant profile and queue
      if (selectedApplicantId) {
        await selectApplicant(selectedApplicantId);
      }
      await loadQueue();
    } catch (err) {
      setError(err.message || 'Failed to save corrections.');
    } finally {
      setSubmittingCorrection(false);
    }
  };

  // Assign Unassigned Document
  const handleAssignDocument = async (docId) => {
    const targetApplId = selectedAssignApplicant[docId];
    if (!targetApplId) return;
    setAssigningDocId(docId);
    setError(null);
    try {
      await api.assignDocument(docId, targetApplId);
      setSuccessMsg(`Document assigned to applicant '${targetApplId}'.`);
      await loadQueue();
    } catch (err) {
      setError(err.message || 'Failed to assign document.');
    } finally {
      setAssigningDocId(null);
    }
  };

  // Applicant Decision Modal Handler
  const openDecisionModal = (decision) => {
    let title = '';
    let description = '';
    let requiresNotes = false;

    if (decision === 'verified') {
      title = 'Confirm Applicant Verification';
      description = `Verify KYC for applicant ${applicantProfile?.applicant?.name || selectedApplicantId}. Confirm that all documents agree and no blocking discrepancies remain.`;
    } else if (decision === 'resubmission_requested') {
      title = 'Request Document Resubmission';
      description = `Request applicant ${applicantProfile?.applicant?.name || selectedApplicantId} to resubmit clearer or updated documents.`;
    } else if (decision === 'rejected') {
      title = 'Confirm Applicant KYC Rejection';
      description = `Reject applicant ${applicantProfile?.applicant?.name || selectedApplicantId}. A recorded justification is mandatory.`;
      requiresNotes = true;
    } else {
      title = 'Flag Applicant for Manual Review';
      description = `Flag applicant ${applicantProfile?.applicant?.name || selectedApplicantId} for senior compliance officer review.`;
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

  const executeApplicantDecision = async () => {
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

      setSuccessMsg(`Applicant '${applicantProfile?.applicant?.name || selectedApplicantId}' marked as ${decisionModal.decision.toUpperCase().replace('_', ' ')}.`);
      setDecisionModal({ isOpen: false, decision: null, title: '', description: '', notes: '', requiresNotes: false });

      // Refresh applicant profile and queue
      await selectApplicant(selectedApplicantId);
      await loadQueue();
    } catch (err) {
      setError(err.message || 'Failed to apply applicant decision.');
    } finally {
      setSubmittingDecision(false);
    }
  };

  // Check if applicant is eligible for "Mark Verified"
  const getVerificationEligibility = () => {
    if (!applicantProfile) return { eligible: false, reason: 'Profile loading...' };
    const matrix = applicantProfile.cross_comparison?.matrix;
    if (!matrix || !matrix.rows) return { eligible: false, reason: 'No comparison matrix available.' };

    const docs = applicantProfile.documents || [];
    if (docs.length === 0) return { eligible: false, reason: 'No documents uploaded.' };

    // Check expired documents
    const hasExpired = matrix.rows.some((r) => r.attribute_key === 'expiry_date' && r.result_status === 'EXPIRED');
    if (hasExpired) return { eligible: false, reason: 'Contains expired document(s). Expired documents prevent approval.' };

    // Check critical mismatches
    const hasNameMismatch = matrix.rows.some((r) => r.attribute_key === 'name' && r.result_status === 'MISMATCH');
    if (hasNameMismatch) return { eligible: false, reason: 'Critical Customer Name mismatch detected across documents.' };

    const hasDobMismatch = matrix.rows.some((r) => r.attribute_key === 'dob' && r.result_status === 'MISMATCH');
    if (hasDobMismatch) return { eligible: false, reason: 'Critical Date of Birth mismatch detected across documents.' };

    // Check missing mandatory fields
    const hasMissingName = matrix.rows.some((r) => r.attribute_key === 'name' && (r.result_status === 'UNAVAILABLE' || r.result_status === 'NOT DETECTED'));
    if (hasMissingName) return { eligible: false, reason: 'Mandatory field Customer Name is not detected.' };

    const hasMissingDob = matrix.rows.some((r) => r.attribute_key === 'dob' && (r.result_status === 'UNAVAILABLE' || r.result_status === 'NOT DETECTED'));
    if (hasMissingDob) return { eligible: false, reason: 'Mandatory field Date of Birth is not detected.' };

    return { eligible: true, reason: null };
  };

  const verificationEligibility = getVerificationEligibility();

  // Filter applicants by search
  const filteredApplicants = applicants.filter((app) => {
    if (!searchTerm) return true;
    const term = searchTerm.toLowerCase();
    const name = (app.name || '').toLowerCase();
    const id = (app.id || '').toLowerCase();
    return name.includes(term) || id.includes(term);
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
      <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-[11px] font-bold bg-blue-50 text-blue-700 border border-blue-200">
        <span className="material-symbols-outlined text-[13px]">schedule</span>
        Pending Review
      </span>
    );
  };

  const getCellStatusBadge = (status, label) => {
    const s = (status || '').toLowerCase().replace(/_/g, ' ');
    if (s === 'match' || s === 'valid') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-emerald-50 text-emerald-700 border border-emerald-200">
          <span className="material-symbols-outlined text-[12px]">check_circle</span>
          {label || 'MATCH'}
        </span>
      );
    }
    if (s === 'mismatch') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-red-50 text-red-700 border border-red-200">
          <span className="material-symbols-outlined text-[12px]">cancel</span>
          {label || 'MISMATCH'}
        </span>
      );
    }
    if (s === 'expired') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-rose-50 text-rose-800 border border-rose-300">
          <span className="material-symbols-outlined text-[12px]">event_busy</span>
          {label || 'EXPIRED'}
        </span>
      );
    }
    if (s === 'needs review' || s === 'warning' || s === 'variation') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-amber-50 text-amber-800 border border-amber-300">
          <span className="material-symbols-outlined text-[12px]">warning</span>
          {label || 'NEEDS REVIEW'}
        </span>
      );
    }
    if (s === 'not detected' || s === 'unavailable' || s === 'missing') {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[10px] font-bold bg-purple-50 text-purple-700 border border-purple-200">
          <span className="material-symbols-outlined text-[12px]">help_outline</span>
          {label || 'NOT DETECTED'}
        </span>
      );
    }
    return (
      <span className="inline-flex items-center px-2 py-0.5 rounded-full text-[10px] font-medium bg-slate-100 text-slate-600 border border-slate-200">
        {label || 'NOT APPLICABLE'}
      </span>
    );
  };

  const getExtractionMethodBadge = (doc) => {
    const f = doc?.extracted_fields || {};
    const method = (f.extraction_method || doc?.extraction_metadata?.extraction_method || '').toLowerCase();
    if (method.includes('gemini') || method.includes('ai')) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-purple-50 text-purple-700 border border-purple-200 text-[10px] font-bold">
          <span className="material-symbols-outlined text-[12px]">auto_awesome</span>
          AI Extraction
        </span>
      );
    }
    if (method.includes('tesseract') || method.includes('ocr')) {
      return (
        <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-amber-50 text-amber-700 border border-amber-200 text-[10px] font-bold">
          <span className="material-symbols-outlined text-[12px]">document_scanner</span>
          Optical OCR
        </span>
      );
    }
    return (
      <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full bg-blue-50 text-blue-700 border border-blue-200 text-[10px] font-bold">
        <span className="material-symbols-outlined text-[12px]">description</span>
        Digital Text
      </span>
    );
  };

  return (
    <div className="w-full max-w-[1620px] mx-auto px-6 py-6 space-y-5">
      {/* Page Title */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-1">
        <div>
          <h1 className="text-[20px] font-bold text-[#0F172A] tracking-tight leading-tight">
            Verification Queue
          </h1>
          <p className="text-[13px] text-[#64748B] mt-0.5">
            Review applicant documents, inspect multi-document extraction, and make compliance decisions.
          </p>
        </div>

        <div className="flex items-center gap-3">
          <button
            onClick={loadQueue}
            className="inline-flex items-center gap-1.5 px-3.5 py-2 text-[13px] font-medium text-[#0F172A] bg-white border border-[#E2E8F0] rounded-lg hover:bg-[#F8FAFC] transition-colors shadow-xs"
          >
            <span className="material-symbols-outlined text-[17px] text-[#64748B]">refresh</span>
            Refresh Queue
          </button>
        </div>
      </div>

      {/* Filter & Search Bar */}
      <div className="bg-white border border-[#E2E8F0] rounded-xl px-4 py-2.5 flex flex-wrap items-center justify-between gap-3 shadow-xs">
        <div className="relative flex-1 min-w-[240px] max-w-md">
          <span className="material-symbols-outlined absolute left-2.5 top-1/2 -translate-y-1/2 text-[16px] text-[#94A3B8]">search</span>
          <input
            type="text"
            placeholder="Search applicant name or ID..."
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
          ].map((f) => (
            <button
              key={f.id}
              onClick={() => setStatusFilter(f.id)}
              className={`px-3 py-1 rounded-lg text-[12px] font-medium transition-colors ${
                statusFilter === f.id
                  ? 'bg-[#0F172A] text-white'
                  : 'bg-[#F8FAFC] text-[#64748B] hover:text-[#0F172A] border border-[#E2E8F0]'
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      {/* Success / Error Notification */}
      {successMsg && (
        <div className="p-3 bg-emerald-50 border border-emerald-200 text-emerald-800 rounded-lg text-[13px] flex items-center justify-between">
          <span className="flex items-center gap-2 font-medium">
            <span className="material-symbols-outlined text-[18px]">check_circle</span>
            {successMsg}
          </span>
          <button onClick={() => setSuccessMsg(null)} className="font-semibold underline ml-2">Dismiss</button>
        </div>
      )}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 text-red-800 rounded-lg text-[13px] flex items-center justify-between">
          <span className="flex items-center gap-2">
            <span className="material-symbols-outlined text-[18px]">error</span>
            <span>{error}</span>
          </span>
          <button onClick={() => setError(null)} className="font-semibold underline ml-2">Dismiss</button>
        </div>
      )}

      {/* 2-Column Balanced Applicant Workspace */}
      <div className="grid grid-cols-1 lg:grid-cols-12 gap-5 items-start">
        {/* ======================================================== */}
        {/* Column 1: Applicant Queue Ledger (3 Cols) */}
        {/* ======================================================== */}
        <div className="lg:col-span-3 min-w-0 bg-white border border-[#E2E8F0] rounded-xl shadow-xs overflow-hidden flex flex-col h-[780px]">
          <div className="px-4 py-3 border-b border-[#E2E8F0] bg-[#FAFAFA] flex items-center justify-between">
            <span className="font-bold text-[14px] text-[#0F172A]">Applicant Ledger</span>
            <span className="text-[11px] px-2 py-0.5 bg-white border border-[#E2E8F0] rounded-full text-[#64748B] font-mono font-medium">
              {filteredApplicants.length} applicants
            </span>
          </div>

          <div className="divide-y divide-[#E2E8F0] overflow-y-auto flex-1">
            {loading ? (
              <div className="p-8 text-center text-[#64748B] text-[13px]">Loading applicant queue...</div>
            ) : filteredApplicants.length === 0 ? (
              <div className="p-8 text-center text-[#64748B] text-[13px]">No applicants found for selected filter.</div>
            ) : (
              filteredApplicants.map((app) => {
                const isSelected = selectedApplicantId === app.id;
                return (
                  <div
                    key={app.id}
                    onClick={() => selectApplicant(app.id)}
                    className={`p-3.5 cursor-pointer transition-colors border-l-4 ${
                      isSelected
                        ? 'bg-[#F0F5FA] border-l-[#2563EB]'
                        : 'hover:bg-[#F8FAFC] border-l-transparent'
                    }`}
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div className="min-w-0 flex-1">
                        <div className="text-[14px] font-bold text-[#0F172A] truncate">
                          {app.name || <span className="text-amber-800 italic font-medium">Name not detected</span>}
                        </div>
                        <div className="text-[11px] text-[#64748B] font-mono mt-0.5">
                          ID: {app.id}
                        </div>
                      </div>
                      <div className="flex-shrink-0">
                        {getStatusBadge(app.status)}
                      </div>
                    </div>

                    <div className="flex items-center justify-between mt-2.5 text-[11px]">
                      <span className="text-[#64748B] font-medium flex items-center gap-1">
                        <span className="material-symbols-outlined text-[14px]">description</span>
                        {app.document_count || 0} document{app.document_count !== 1 ? 's' : ''}
                      </span>
                      <span className="text-[#64748B]">
                        {app.latest_document_date ? new Date(app.latest_document_date).toLocaleDateString() : 'Active'}
                      </span>
                    </div>
                  </div>
                );
              })
            )}
          </div>
        </div>

        {/* ======================================================== */}
        {/* Column 2: Selected Applicant KYC Workspace (9 Cols) */}
        {/* ======================================================== */}
        <div className="lg:col-span-9 min-w-0 space-y-5">
          {profileLoading ? (
            <div className="bg-white border border-[#E2E8F0] rounded-xl shadow-xs p-12 text-center text-[#64748B]">
              Loading applicant KYC dossier...
            </div>
          ) : !applicantProfile ? (
            <div className="bg-white border border-[#E2E8F0] rounded-xl shadow-xs p-12 text-center text-[#64748B]">
              Select an applicant from the Ledger on the left to inspect and verify.
            </div>
          ) : (
            <>
              {/* Applicant Header & Overview */}
              <div className="bg-white border border-[#E2E8F0] rounded-xl shadow-xs p-5">
                <div className="flex flex-col md:flex-row md:items-center justify-between gap-4 pb-4 border-b border-[#E2E8F0]">
                  <div>
                    <div className="flex items-center gap-2 mb-1">
                      <span className="font-mono text-[11px] text-[#64748B] font-semibold">APPLICANT ID: {applicantProfile.applicant?.id}</span>
                      {getStatusBadge(applicantProfile.applicant?.status)}
                      <span className="px-2 py-0.5 rounded text-[11px] font-bold uppercase bg-slate-100 text-slate-700 font-mono">
                        Risk: {applicantProfile.applicant?.risk_level || 'low'}
                      </span>
                    </div>
                    <h2 className="text-[24px] font-bold text-[#0F172A]">
                      {applicantProfile.applicant?.name || (
                        <span className="text-amber-800 italic">Name not detected</span>
                      )}
                    </h2>
                    <div className="text-[12px] text-[#64748B] flex items-center gap-3 mt-1">
                      {applicantProfile.applicant?.email && (
                        <span>Email: <strong className="text-[#0F172A]">{applicantProfile.applicant.email}</strong></span>
                      )}
                      {applicantProfile.applicant?.phone && (
                        <span>Phone: <strong className="text-[#0F172A]">{applicantProfile.applicant.phone}</strong></span>
                      )}
                      <span>Dossier: <strong className="text-[#0F172A]">{applicantProfile.documents?.length || 0} document(s)</strong></span>
                    </div>
                  </div>
                </div>

                {/* Rejection Justification Notice */}
                {applicantProfile.applicant?.status === 'rejected' && (
                  <div className="mt-4 p-4 bg-red-50 border border-red-200 rounded-xl space-y-1.5">
                    <div className="flex items-center gap-2 text-red-950 font-bold text-[13px]">
                      <span className="material-symbols-outlined text-[17px] text-red-700">cancel</span>
                      Applicant KYC Application Rejected
                    </div>
                    {applicantProfile.applicant?.notes && (
                      <div className="text-[12px] text-red-900 leading-relaxed">
                        <strong className="text-red-950">Recorded Reason / Officer Remarks:</strong> {applicantProfile.applicant.notes}
                      </div>
                    )}
                  </div>
                )}

                {/* Blocking Issues or Expiry Alert if any */}
                {applicantProfile.applicant?.status !== 'rejected' && (!verificationEligibility.eligible || (applicantProfile.cross_comparison?.discrepancies || []).length > 0) && (
                  <div className="mt-4 p-3.5 bg-amber-50 border border-amber-200 rounded-xl space-y-1.5">
                    <div className="flex items-center gap-2 text-amber-950 font-bold text-[12px]">
                      <span className="material-symbols-outlined text-[16px] text-amber-700">warning</span>
                      Compliance Review Alerts
                    </div>
                    <ul className="list-disc list-inside text-[12px] text-amber-900 space-y-0.5">
                      {!verificationEligibility.eligible && (
                        <li className="font-semibold">{verificationEligibility.reason}</li>
                      )}
                      {(applicantProfile.cross_comparison?.discrepancies || []).map((d, i) => (
                        <li key={i}>{d}</li>
                      ))}
                    </ul>
                  </div>
                )}
              </div>

              {/* Consolidated Extraction and Comparison Table */}
              <div className="bg-white border border-[#E2E8F0] rounded-xl shadow-xs overflow-hidden">
                <div className="p-4 border-b border-[#E2E8F0] bg-white flex flex-col sm:flex-row sm:items-center justify-between gap-3">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="material-symbols-outlined text-[#2563EB] text-[19px]">table_chart</span>
                      <h3 className="text-[15px] font-bold text-[#0F172A]">Consolidated Extraction & Comparison Table</h3>
                      <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-blue-100 text-blue-800">
                        {applicantProfile.cross_comparison?.matrix?.columns?.length || 0} Documents Uploaded
                      </span>
                    </div>
                    <p className="text-[11px] text-[#64748B] mt-0.5">
                      Deterministic attribute comparison across all KYC documents uploaded by this applicant. Issue dates are excluded.
                    </p>
                  </div>

                  <div className="flex items-center gap-2">
                    <a
                      href={api.getApplicantComparisonExportUrl(selectedApplicantId, 'xlsx')}
                      target="_blank"
                      rel="noopener noreferrer"
                      className="inline-flex items-center gap-1 px-3 py-1.5 bg-[#F8FAFC] hover:bg-[#F1F5F9] text-[#0F172A] border border-[#CBD5E1] rounded-lg text-[11px] font-semibold transition-colors"
                    >
                      <span className="material-symbols-outlined text-[14px] text-emerald-600">download</span>
                      Export Excel
                    </a>
                  </div>
                </div>

                <div className="overflow-x-auto w-full">
                  <table className="min-w-full text-left border-collapse text-[13px]">
                    <thead>
                      <tr className="bg-[#F8FAFC] border-b border-[#E2E8F0]">
                        <th className="py-3 px-4 font-bold text-[#475569] uppercase tracking-wider text-[11px] w-[190px] min-w-[190px] max-w-[210px] break-words whitespace-normal border-r border-[#E2E8F0] sticky left-0 bg-[#F8FAFC] z-10">
                          Attribute
                        </th>
                        {(applicantProfile.cross_comparison?.matrix?.columns || []).map((col) => (
                          <th key={col.id} className="py-3 px-4 font-semibold text-[#0F172A] w-[220px] min-w-[220px] max-w-[250px] border-r border-[#E2E8F0]">
                            <div className="flex items-center justify-between gap-1 mb-0.5">
                              <span className="px-1.5 py-0.2 rounded text-[10px] font-bold uppercase bg-blue-100 text-blue-800">
                                {col.type_label || col.document_type}
                              </span>
                              <span className="text-[10px] font-mono text-[#64748B]">#{col.id.slice(0, 6)}</span>
                            </div>
                            <div className="font-bold text-[12px] text-[#0F172A] break-all line-clamp-2 leading-tight" title={col.filename}>
                              {col.filename}
                            </div>
                          </th>
                        ))}
                        <th className="py-3 px-4 font-bold text-[#475569] uppercase tracking-wider text-[11px] w-[140px] min-w-[140px] border-r border-[#E2E8F0]">
                          Comparison Result
                        </th>
                        <th className="py-3 px-4 font-bold text-[#475569] uppercase tracking-wider text-[11px] min-w-[240px] max-w-[360px] break-words whitespace-normal">
                          Explanation
                        </th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-[#E2E8F0]">
                      {(applicantProfile.cross_comparison?.matrix?.rows || []).map((row, idx) => {
                        const isMismatch = row.result_status === 'MISMATCH' || row.result_status === 'EXPIRED';
                        const isNeedsReview = row.result_status === 'NEEDS REVIEW' || row.result_status === 'UNAVAILABLE';
                        return (
                          <tr
                            key={idx}
                            className={`transition-colors ${
                              isMismatch
                                ? 'bg-red-50/40 hover:bg-red-50/70'
                                : isNeedsReview
                                ? 'bg-amber-50/30 hover:bg-amber-50/60'
                                : 'hover:bg-[#F8FAFC]'
                            }`}
                          >
                            <td className="py-3 px-4 font-bold text-[#0F172A] w-[190px] min-w-[190px] max-w-[210px] break-words whitespace-normal border-r border-[#E2E8F0] sticky left-0 bg-white z-10">
                              {row.attribute_label}
                            </td>
                            {(applicantProfile.cross_comparison?.matrix?.columns || []).map((col) => {
                              const val = row.values ? row.values[col.id] : null;
                              const isNotDetected = !val || val === 'Not detected' || val === 'Not Detected';
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
                              {getCellStatusBadge(row.result_status, row.result_label)}
                            </td>
                            <td className="py-3 px-4 text-[12px] text-[#475569] leading-relaxed min-w-[240px] max-w-[360px] break-words whitespace-normal">
                              {row.explanation}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>

                <div className="p-3 bg-[#F8FAFC] border-t border-[#E2E8F0] flex items-center justify-between text-[11px] text-[#64748B]">
                  <span>Showing attribute comparison for applicant <strong>{applicantProfile.applicant?.name || selectedApplicantId}</strong></span>
                  <span>Missing fields do not trigger false mismatches</span>
                </div>
              </div>

              {/* Uploaded Documents Shelf & Inspector */}
              <div className="bg-white border border-[#E2E8F0] rounded-xl shadow-xs p-5 space-y-4">
                <div className="flex items-center justify-between pb-2 border-b border-[#E2E8F0]">
                  <div>
                    <h3 className="text-[15px] font-bold text-[#0F172A]">Uploaded Applicant Documents</h3>
                    <p className="text-[11px] text-[#64748B]">Inspect original files or correct extracted field values if OCR errors occurred</p>
                  </div>
                  <span className="text-[11px] font-mono text-[#64748B]">
                    {applicantProfile.documents?.length || 0} file(s)
                  </span>
                </div>

                <div className="grid grid-cols-1 md:grid-cols-2 lg:grid-cols-3 gap-3">
                  {(applicantProfile.documents || []).map((doc) => (
                    <div
                      key={doc.id}
                      className="p-3.5 bg-[#F8FAFC] border border-[#E2E8F0] rounded-xl flex flex-col justify-between space-y-3"
                    >
                      <div>
                        <div className="flex items-center justify-between gap-1 mb-1.5">
                          <span className="px-2 py-0.5 rounded text-[10px] font-bold uppercase bg-blue-100 text-blue-800 font-mono">
                            {doc.classified_type || doc.document_type}
                          </span>
                          {getExtractionMethodBadge(doc)}
                        </div>
                        <h4 className="font-bold text-[13px] text-[#0F172A] truncate" title={doc.original_filename}>
                          {doc.original_filename}
                        </h4>
                        <div className="text-[11px] text-[#64748B] mt-0.5">
                          Size: {(doc.file_size / 1024).toFixed(1)} KB | Status: <strong className="text-[#0F172A]">{doc.review_status?.replace(/_/g, ' ')}</strong>
                        </div>
                      </div>

                      <div className="flex items-center gap-2 pt-2 border-t border-[#E2E8F0]">
                        <button
                          onClick={() => openInspectModal(doc)}
                          className="flex-1 py-1.5 px-2 bg-white hover:bg-slate-50 border border-[#CBD5E1] rounded-lg text-[11px] font-semibold text-[#0F172A] flex items-center justify-center gap-1 shadow-xs transition-colors"
                        >
                          <span className="material-symbols-outlined text-[14px] text-[#2563EB]">visibility</span>
                          Inspect
                        </button>
                        <button
                          onClick={() => openCorrectionModal(doc)}
                          className="py-1.5 px-2.5 bg-white hover:bg-slate-50 border border-[#CBD5E1] rounded-lg text-[11px] font-semibold text-[#64748B] hover:text-[#0F172A] flex items-center gap-1 shadow-xs transition-colors"
                          title="Correct extracted field value if needed"
                        >
                          <span className="material-symbols-outlined text-[14px]">edit</span>
                          Edit
                        </button>
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              {/* Applicant Compliance Actions Bar */}
              <div className="bg-white border border-[#E2E8F0] rounded-xl shadow-xs p-5">
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4">
                  <div>
                    <h3 className="text-[15px] font-bold text-[#0F172A]">Applicant KYC Compliance Actions</h3>
                    <p className="text-[12px] text-[#64748B]">
                      Submit official verification decision for applicant <strong>{applicantProfile.applicant?.name}</strong>
                    </p>
                  </div>

                  <div className="flex items-center gap-2.5 flex-wrap">
                    {/* Mark Verified Button */}
                    <button
                      disabled={!verificationEligibility.eligible || submittingDecision}
                      onClick={() => openDecisionModal('verified')}
                      title={verificationEligibility.eligible ? 'Approve applicant KYC' : verificationEligibility.reason}
                      className={`px-4 py-2.5 rounded-lg text-[13px] font-semibold transition-colors flex items-center gap-1.5 shadow-xs ${
                        verificationEligibility.eligible
                          ? 'bg-emerald-700 hover:bg-emerald-800 text-white cursor-pointer'
                          : 'bg-emerald-100 text-emerald-400 cursor-not-allowed border border-emerald-200'
                      }`}
                    >
                      <span className="material-symbols-outlined text-[18px]">verified</span>
                      Mark Verified
                    </button>

                    {/* Request Resubmission Button */}
                    <button
                      disabled={submittingDecision}
                      onClick={() => openDecisionModal('resubmission_requested')}
                      className="px-4 py-2.5 bg-indigo-600 hover:bg-indigo-700 text-white rounded-lg text-[13px] font-semibold transition-colors flex items-center gap-1.5 shadow-xs"
                    >
                      <span className="material-symbols-outlined text-[18px]">replay</span>
                      Request Resubmission
                    </button>

                    {/* Flag for Manual Review Button */}
                    <button
                      disabled={submittingDecision}
                      onClick={() => openDecisionModal('manual_review')}
                      className="px-4 py-2.5 bg-amber-600 hover:bg-amber-700 text-white rounded-lg text-[13px] font-semibold transition-colors flex items-center gap-1.5 shadow-xs"
                    >
                      <span className="material-symbols-outlined text-[18px]">flag</span>
                      Flag for Review
                    </button>

                    {/* Reject Button */}
                    <button
                      disabled={submittingDecision}
                      onClick={() => openDecisionModal('rejected')}
                      className="px-4 py-2.5 bg-red-700 hover:bg-red-800 text-white rounded-lg text-[13px] font-semibold transition-colors flex items-center gap-1.5 shadow-xs"
                    >
                      <span className="material-symbols-outlined text-[18px]">cancel</span>
                      Reject
                    </button>
                  </div>
                </div>
              </div>
            </>
          )}
        </div>
      </div>

      {/* ======================================================== */}
      {/* VeriDoc AI 2.0 Visual Document Workspace */}
      {/* ======================================================== */}
      {inspectingDoc && (
        <VisualDocumentWorkspace
          documentId={inspectingDoc.id}
          onClose={() => setInspectingDoc(null)}
          onAttributeUpdated={() => {
            if (selectedApplicantId) {
              selectApplicant(selectedApplicantId);
            }
          }}
        />
      )}

      {/* ======================================================== */}
      {/* Field Correction Modal (Optional OCR Corrections) */}
      {/* ======================================================== */}
      {correctingDoc && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-xl w-full p-6 space-y-4 border border-[#CBD5E1]">
            <div className="flex items-center justify-between pb-2 border-b border-[#E2E8F0]">
              <div>
                <h3 className="text-[16px] font-bold text-[#0F172A]">Correct Document Extracted Fields</h3>
                <p className="text-[11px] text-[#64748B]">Document: {correctingDoc.original_filename}</p>
              </div>
              <button onClick={() => setCorrectingDoc(null)} className="p-1 rounded hover:bg-slate-100">
                <span className="material-symbols-outlined text-[20px] text-[#64748B]">close</span>
              </button>
            </div>

            <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 text-[12px]">
              <div>
                <label className="block text-[11px] font-bold text-[#64748B] mb-0.5">Customer Name</label>
                <input
                  type="text"
                  value={correctionForm.name}
                  onChange={(e) => setCorrectionForm(prev => ({ ...prev, name: e.target.value }))}
                  className="w-full bg-[#F8FAFC] border border-[#CBD5E1] rounded-lg p-2 text-[#0F172A] focus:outline-none focus:border-[#2563EB]"
                />
              </div>

              <div>
                <label className="block text-[11px] font-bold text-[#64748B] mb-0.5">Date of Birth (YYYY-MM-DD)</label>
                <input
                  type="text"
                  value={correctionForm.dob}
                  onChange={(e) => setCorrectionForm(prev => ({ ...prev, dob: e.target.value }))}
                  className="w-full bg-[#F8FAFC] border border-[#CBD5E1] rounded-lg p-2 text-[#0F172A] font-mono focus:outline-none focus:border-[#2563EB]"
                />
              </div>

              <div>
                <label className="block text-[11px] font-bold text-[#64748B] mb-0.5">ID Number</label>
                <input
                  type="text"
                  value={correctionForm.id_number}
                  onChange={(e) => setCorrectionForm(prev => ({ ...prev, id_number: e.target.value }))}
                  className="w-full bg-[#F8FAFC] border border-[#CBD5E1] rounded-lg p-2 text-[#0F172A] font-mono focus:outline-none focus:border-[#2563EB]"
                />
              </div>

              <div>
                <label className="block text-[11px] font-bold text-[#64748B] mb-0.5">Gender</label>
                <select
                  value={correctionForm.gender}
                  onChange={(e) => setCorrectionForm(prev => ({ ...prev, gender: e.target.value }))}
                  className="w-full bg-[#F8FAFC] border border-[#CBD5E1] rounded-lg p-2 text-[#0F172A] focus:outline-none focus:border-[#2563EB]"
                >
                  <option value="">Select Gender</option>
                  <option value="MALE">MALE</option>
                  <option value="FEMALE">FEMALE</option>
                  <option value="TRANSGENDER">TRANSGENDER</option>
                </select>
              </div>

              <div>
                <label className="block text-[11px] font-bold text-[#64748B] mb-0.5">Father / Guardian Name</label>
                <input
                  type="text"
                  value={correctionForm.father_name}
                  onChange={(e) => setCorrectionForm(prev => ({ ...prev, father_name: e.target.value }))}
                  className="w-full bg-[#F8FAFC] border border-[#CBD5E1] rounded-lg p-2 text-[#0F172A] focus:outline-none focus:border-[#2563EB]"
                />
              </div>

              <div>
                <label className="block text-[11px] font-bold text-[#64748B] mb-0.5">Expiry Date (YYYY-MM-DD)</label>
                <input
                  type="text"
                  value={correctionForm.expiry_date}
                  onChange={(e) => setCorrectionForm(prev => ({ ...prev, expiry_date: e.target.value }))}
                  className="w-full bg-[#F8FAFC] border border-[#CBD5E1] rounded-lg p-2 text-[#0F172A] font-mono focus:outline-none focus:border-[#2563EB]"
                />
              </div>

              <div className="sm:col-span-2">
                <label className="block text-[11px] font-bold text-[#64748B] mb-0.5">Residential Address</label>
                <input
                  type="text"
                  value={correctionForm.address}
                  onChange={(e) => setCorrectionForm(prev => ({ ...prev, address: e.target.value }))}
                  className="w-full bg-[#F8FAFC] border border-[#CBD5E1] rounded-lg p-2 text-[#0F172A] focus:outline-none focus:border-[#2563EB]"
                />
              </div>
            </div>

            <div className="flex justify-end gap-2 pt-2 border-t border-[#E2E8F0]">
              <button
                onClick={() => setCorrectingDoc(null)}
                className="px-4 py-2 text-[12px] font-semibold text-[#64748B] hover:text-[#0F172A] bg-slate-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                disabled={submittingCorrection}
                onClick={handleSaveCorrections}
                className="px-4 py-2 bg-[#0F172A] hover:bg-[#1E293B] text-white rounded-lg text-[12px] font-semibold shadow-xs flex items-center gap-1.5"
              >
                {submittingCorrection ? 'Saving...' : 'Save Field Corrections'}
              </button>
            </div>
          </div>
        </div>
      )}

      {/* ======================================================== */}
      {/* Applicant Decision Confirmation Modal */}
      {/* ======================================================== */}
      {decisionModal.isOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-2xl max-w-md w-full p-6 space-y-4 border border-[#CBD5E1]">
            <div className="flex items-center gap-3">
              <span className={`p-2.5 rounded-full ${
                decisionModal.decision === 'verified'
                  ? 'bg-emerald-100 text-emerald-700'
                  : decisionModal.decision === 'rejected'
                  ? 'bg-red-100 text-red-700'
                  : 'bg-amber-100 text-amber-700'
              }`}>
                <span className="material-symbols-outlined text-[24px]">
                  {decisionModal.decision === 'verified' ? 'verified' : decisionModal.decision === 'rejected' ? 'cancel' : 'warning'}
                </span>
              </span>
              <div>
                <h3 className="text-[16px] font-bold text-[#0F172A]">{decisionModal.title}</h3>
                <p className="text-[12px] text-[#64748B]">Applicant: {applicantProfile?.applicant?.name || selectedApplicantId}</p>
              </div>
            </div>

            <p className="text-[13px] text-[#475569] leading-relaxed">
              {decisionModal.description}
            </p>

            <div>
              <label className="block text-[11px] font-bold text-[#64748B] mb-1">
                Audit Justification / Compliance Remarks {decisionModal.requiresNotes && <span className="text-red-600">*</span>}
              </label>
              <textarea
                rows="3"
                value={decisionModal.notes}
                onChange={(e) => setDecisionModal(prev => ({ ...prev, notes: e.target.value }))}
                placeholder={decisionModal.requiresNotes ? 'Enter required rejection reason...' : 'Optional compliance remarks...'}
                className="w-full bg-[#F8FAFC] border border-[#CBD5E1] rounded-lg p-2.5 text-[12px] text-[#0F172A] focus:outline-none focus:border-[#2563EB]"
              />
            </div>

            <div className="flex justify-end gap-2 pt-2">
              <button
                disabled={submittingDecision}
                onClick={() => setDecisionModal({ isOpen: false, decision: null, title: '', description: '', notes: '', requiresNotes: false })}
                className="px-4 py-2 text-[12px] font-semibold text-[#64748B] hover:text-[#0F172A] bg-slate-100 rounded-lg"
              >
                Cancel
              </button>
              <button
                disabled={submittingDecision || (decisionModal.requiresNotes && !decisionModal.notes.trim())}
                onClick={executeApplicantDecision}
                className={`px-4 py-2 text-[12px] font-semibold text-white rounded-lg shadow-xs flex items-center gap-1.5 ${
                  decisionModal.decision === 'verified'
                    ? 'bg-emerald-700 hover:bg-emerald-800'
                    : decisionModal.decision === 'rejected'
                    ? 'bg-red-700 hover:bg-red-800'
                    : 'bg-[#0F172A] hover:bg-[#1E293B]'
                } disabled:opacity-50`}
              >
                {submittingDecision ? 'Submitting...' : 'Confirm Decision'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
