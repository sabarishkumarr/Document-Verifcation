import React, { useState, useEffect, useRef } from 'react';
import { api } from '../api';
import ComparisonMatrix from './ComparisonMatrix';

const STAGES = [
  { id: 'uploading', label: '1. Ingestion', desc: 'Secure storage & integrity verification' },
  { id: 'extracting', label: '2. Text Extraction', desc: 'Digital & OCR text extraction' },
  { id: 'classifying', label: '3. Classification', desc: 'Multi-category identity classification' },
  { id: 'validating', label: '4. Format Rules', desc: 'RegEx & expiry date validation' },
  { id: 'comparing', label: '5. Cross-Check', desc: 'Deterministic attribute matching' },
  { id: 'complete', label: '6. Persistence', desc: 'Audit logging & compliance persistence' },
];

export default function UploadView({ onNavigateToQueue, onNavigateToApplicant }) {
  const [applicants, setApplicants] = useState([]);
  const [isNewApplicant, setIsNewApplicant] = useState(false);
  const [selectedApplicantId, setSelectedApplicantId] = useState('');
  const [newApplicantId, setNewApplicantId] = useState('');
  const [newApplicantName, setNewApplicantName] = useState('');

  const [files, setFiles] = useState([]);
  const [fileStatuses, setFileStatuses] = useState([]);
  const [uploading, setUploading] = useState(false);
  const [currentStageIndex, setCurrentStageIndex] = useState(0);
  const [elapsedSeconds, setElapsedSeconds] = useState(0);
  const [processingStatusText, setProcessingStatusText] = useState('');
  const [processedResults, setProcessedResults] = useState([]);
  const [crossComparison, setCrossComparison] = useState(null);
  const [error, setError] = useState(null);

  const fileInputRef = useRef(null);
  const timerRef = useRef(null);

  useEffect(() => {
    loadApplicants();
    return () => {
      if (timerRef.current) clearInterval(timerRef.current);
    };
  }, []);

  const loadApplicants = async () => {
    try {
      const res = await api.getApplicants();
      const list = res.data.applicants || [];
      setApplicants(list);
      if (list.length > 0 && !selectedApplicantId) {
        setSelectedApplicantId(list[0].id);
      }
    } catch (err) {
      console.warn('Could not load applicants:', err);
    }
  };

  const handleFileChange = (e) => {
    if (e.target.files) {
      const selected = Array.from(e.target.files);
      const newFiles = [...files, ...selected];
      setFiles(newFiles);
      setFileStatuses(newFiles.map(f => ({
        name: f.name,
        size: f.size,
        file: f,
        status: 'queued',
        stage: 'Queued',
        docId: null,
        error: null
      })));
    }
  };

  const removeFile = (idx) => {
    const updated = files.filter((_, i) => i !== idx);
    setFiles(updated);
    setFileStatuses(prev => prev.filter((_, i) => i !== idx));
  };

  const startTimer = () => {
    setElapsedSeconds(0);
    if (timerRef.current) clearInterval(timerRef.current);
    timerRef.current = setInterval(() => {
      setElapsedSeconds(s => s + 1);
    }, 1000);
  };

  const stopTimer = () => {
    if (timerRef.current) {
      clearInterval(timerRef.current);
      timerRef.current = null;
    }
  };

  const formatTimer = (totalSec) => {
    const m = Math.floor(totalSec / 60);
    const s = totalSec % 60;
    return `${m.toString().padStart(2, '0')}:${s.toString().padStart(2, '0')}`;
  };

  const handleUploadAndProcess = async () => {
    if (files.length === 0) {
      setError('Please select at least one document to upload.');
      return;
    }

    let applicantId = selectedApplicantId;
    let applicantName = '';
    if (isNewApplicant) {
      const cleanId = newApplicantId.trim() || `APP-${Math.floor(1000 + Math.random() * 9000)}`;
      const cleanName = newApplicantName.trim();
      applicantName = cleanName;
      try {
        await api.createApplicant({ id: cleanId, name: cleanName || null });
        applicantId = cleanId;
      } catch (err) {
        console.warn('Applicant creation note:', err);
        applicantId = cleanId;
      }
    } else {
      const found = applicants.find(a => a.id === selectedApplicantId);
      if (found) applicantName = found.name;
    }

    if (!applicantId) {
      applicantId = `APP-${Math.floor(1000 + Math.random() * 9000)}`;
    }

    setUploading(true);
    setError(null);
    setProcessedResults([]);
    setCrossComparison(null);
    startTimer();
    setCurrentStageIndex(0);
    setProcessingStatusText('Ingesting and storing documents securely in storage/uploads/...');

    try {
      // 1. Upload files
      const formData = new FormData();
      formData.append('applicant_id', applicantId);
      files.forEach((f) => {
        formData.append('files', f);
      });

      setFileStatuses(prev => prev.map(item => ({ ...item, status: 'uploading', stage: 'Uploading' })));
      const uploadRes = await api.uploadDocuments(formData);
      const uploadedDocs = uploadRes.uploaded || uploadRes.data?.uploaded || [];

      if (uploadedDocs.length === 0) {
        throw new Error('No files passed initial upload validation.');
      }

      // Map uploaded doc IDs back to file statuses
      setFileStatuses(prev => prev.map((item, idx) => {
        const doc = uploadedDocs[idx];
        return {
          ...item,
          docId: doc?.id,
          status: 'uploaded',
          stage: 'Uploaded',
          documentType: doc?.document_type || 'Detecting...'
        };
      }));

      // 2. Process each uploaded document through intelligence pipeline
      const pipelineResults = [];
      for (let i = 0; i < uploadedDocs.length; i++) {
        const doc = uploadedDocs[i];
        
        // Stage 2: OCR & Extraction
        setCurrentStageIndex(1);
        setProcessingStatusText(`Extracting text from ${doc.original_filename}...`);
        setFileStatuses(prev => prev.map((item, idx) => idx === i ? { ...item, status: 'processing', stage: 'OCR Reading' } : item));

        // Stage 3: AI Classification
        setCurrentStageIndex(2);
        setProcessingStatusText(`AI Classification & field extraction for ${doc.original_filename}...`);
        setFileStatuses(prev => prev.map((item, idx) => idx === i ? { ...item, status: 'processing', stage: 'AI Extraction' } : item));

        try {
          const procRes = await api.processDocument(doc.id);
          const result = procRes.data?.result;

          // Stage 4: Rule Checks
          setCurrentStageIndex(3);
          setProcessingStatusText(`Validating formats and business rules for ${doc.original_filename}...`);

          if (result) {
            pipelineResults.push(result);
            if (result.cross_comparison) {
              setCrossComparison(result.cross_comparison);
            }

            setFileStatuses(prev => prev.map((item, idx) => idx === i ? {
              ...item,
              status: 'completed',
              stage: 'Completed',
              documentType: result.classification?.classified_type || 'Unknown'
            } : item));
          }
        } catch (procErr) {
          console.error(`Failed processing doc ${doc.id}:`, procErr);
          setFileStatuses(prev => prev.map((item, idx) => idx === i ? {
            ...item,
            status: 'failed',
            stage: 'Failed',
            error: procErr.message || 'Processing failed'
          } : item));
        }
      }

      // Stage 5: Cross-Document Comparison
      setCurrentStageIndex(4);
      setProcessingStatusText('Executing deterministic cross-document comparison and matrix synthesis...');

      // Stage 6: Persistence
      setCurrentStageIndex(5);
      setProcessingStatusText('Finalizing verification records and audit ledger...');

      setProcessedResults(pipelineResults);
      setProcessingStatusText('Verification pipeline complete.');
      loadApplicants();

    } catch (err) {
      setError(err.message || 'Upload & Processing failed.');
    } finally {
      stopTimer();
      setUploading(false);
    }
  };

  const handleRetryFile = async (itemIdx) => {
    const target = fileStatuses[itemIdx];
    if (!target || !target.docId) return;

    setFileStatuses(prev => prev.map((item, idx) => idx === itemIdx ? { ...item, status: 'processing', stage: 'Retrying...', error: null } : item));
    try {
      const procRes = await api.processDocument(target.docId);
      const result = procRes.data?.result;
      if (result) {
        setProcessedResults(prev => [...prev.filter(r => r.document_id !== target.docId), result]);
        if (result.cross_comparison) {
          setCrossComparison(result.cross_comparison);
        }
        setFileStatuses(prev => prev.map((item, idx) => idx === itemIdx ? {
          ...item,
          status: 'completed',
          stage: 'Completed',
          documentType: result.classification?.classified_type || 'Unknown',
          error: null
        } : item));
      }
    } catch (retryErr) {
      setFileStatuses(prev => prev.map((item, idx) => idx === itemIdx ? {
        ...item,
        status: 'failed',
        stage: 'Failed',
        error: retryErr.message || 'Retry failed'
      } : item));
    }
  };

  const getDocTypeBadge = (type) => {
    const formatted = (type || 'unknown').toUpperCase();
    const colors = {
      PAN: 'bg-blue-100 text-blue-800 border-blue-300',
      AADHAAR: 'bg-emerald-100 text-emerald-800 border-emerald-300',
      PASSPORT: 'bg-purple-100 text-purple-800 border-purple-300',
      VOTER_ID: 'bg-amber-100 text-amber-800 border-amber-300',
      DRIVING_LICENCE: 'bg-indigo-100 text-indigo-800 border-indigo-300',
      UNKNOWN: 'bg-slate-100 text-slate-800 border-slate-300',
    };
    return (
      <span className={`inline-flex items-center px-2.5 py-0.5 rounded-full text-[11px] font-bold border ${colors[formatted] || colors.UNKNOWN}`}>
        {formatted.replace('_', ' ')}
      </span>
    );
  };

  return (
    <div className="w-full max-w-5xl mx-auto px-6 lg:px-8 py-8 space-y-8">
      
      {/* Header */}
      <header className="space-y-1.5 pb-2">
        <div className="flex items-center gap-2">
          <span className="text-[11px] font-bold tracking-widest uppercase text-[#64748B]">OPERATIONS</span>
          <span className="text-[#CBD5E1] text-[11px]">/</span>
          <span className="text-[11px] font-bold tracking-widest uppercase text-[#2563EB]">DOCUMENT INGESTION</span>
        </div>
        <h1 className="font-serif text-[38px] font-bold text-[#0F172A] leading-tight">
          Upload Documents<span className="text-[#2563EB]">.</span>
        </h1>
        <p className="text-[15px] text-[#64748B]">
          Submit applicant KYC documents for automated extraction, classification, format validation, and deterministic cross-comparison.
        </p>
      </header>

      {/* Applicant Selection Form */}
      <div className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-xs space-y-4">
        <h2 className="text-[15px] font-bold text-[#0F172A] flex items-center gap-2">
          <span className="material-symbols-outlined text-[18px] text-[#2563EB]">person</span>
          Applicant Association
        </h2>

        <div className="flex items-center gap-4 text-[13px]">
          <label className="flex items-center gap-2 cursor-pointer font-medium text-[#0F172A]">
            <input
              type="radio"
              checked={!isNewApplicant}
              onChange={() => setIsNewApplicant(false)}
              className="text-[#2563EB]"
            />
            Existing Applicant
          </label>
          <label className="flex items-center gap-2 cursor-pointer font-medium text-[#0F172A]">
            <input
              type="radio"
              checked={isNewApplicant}
              onChange={() => setIsNewApplicant(true)}
              className="text-[#2563EB]"
            />
            New Applicant
          </label>
        </div>

        {!isNewApplicant ? (
          <div>
            <label className="block text-[12px] font-semibold text-[#64748B] mb-1">Select Applicant Profile</label>
            <select
              value={selectedApplicantId}
              onChange={(e) => setSelectedApplicantId(e.target.value)}
              className="w-full bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg px-3 py-2 text-[13px] text-[#0F172A] focus:outline-none focus:border-[#2563EB]"
            >
              {applicants.length === 0 && <option value="">No existing applicants (will create new)</option>}
              {applicants.map((a) => (
                <option key={a.id} value={a.id}>
                  {a.name} ({a.id}) — {a.document_count || 0} document(s)
                </option>
              ))}
            </select>
          </div>
        ) : (
          <div className="grid grid-cols-1 sm:grid-cols-2 gap-4">
            <div>
              <label className="block text-[12px] font-semibold text-[#64748B] mb-1">
                Applicant Full Name <span className="text-[11px] font-normal text-slate-400">(Optional — auto-detected from documents)</span>
              </label>
              <input
                type="text"
                placeholder="Leave blank to automatically extract from documents"
                value={newApplicantName}
                onChange={(e) => setNewApplicantName(e.target.value)}
                className="w-full bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg px-3 py-2 text-[13px] text-[#0F172A] focus:outline-none focus:border-[#2563EB]"
              />
            </div>
            <div>
              <label className="block text-[12px] font-semibold text-[#64748B] mb-1">Custom Applicant ID (Optional)</label>
              <input
                type="text"
                placeholder="e.g. APP-3091 (auto-generated if empty)"
                value={newApplicantId}
                onChange={(e) => setNewApplicantId(e.target.value)}
                className="w-full bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg px-3 py-2 text-[13px] text-[#0F172A] focus:outline-none focus:border-[#2563EB]"
              />
            </div>
          </div>
        )}
      </div>

      {/* Upload Zone */}
      <div className="bg-white border-2 border-dashed border-[#CBD5E1] rounded-xl p-8 text-center space-y-4 shadow-xs hover:border-[#2563EB] transition-colors">
        <input
          type="file"
          ref={fileInputRef}
          multiple
          accept=".pdf,.jpg,.jpeg,.png"
          onChange={handleFileChange}
          className="hidden"
          id="doc-upload-input"
        />
        <label htmlFor="doc-upload-input" className="cursor-pointer block">
          <div className="w-12 h-12 rounded-full bg-blue-50 text-[#2563EB] mx-auto flex items-center justify-center mb-3">
            <span className="material-symbols-outlined text-[28px]">cloud_upload</span>
          </div>
          <div className="text-[15px] font-bold text-[#0F172A]">
            Click to browse or drag and drop KYC documents
          </div>
          <p className="text-[13px] text-[#64748B] mt-1">
            Accepts PDF, JPG, JPEG, and PNG (up to 16 MB per document)
          </p>
          <div className="inline-flex items-center gap-2 mt-4 px-4 py-2 bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg text-[13px] font-medium text-[#0F172A] hover:bg-[#F1F5F9] transition-colors">
            Select Documents
          </div>
        </label>
      </div>

      {/* Selected Files / Processing Queue Table */}
      {fileStatuses.length > 0 && (
        <div className="bg-white border border-[#E2E8F0] rounded-xl p-5 space-y-4 shadow-xs">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <h3 className="text-[14px] font-bold text-[#0F172A]">
                Document Queue ({fileStatuses.length})
              </h3>
              {uploading && (
                <span className="px-2 py-0.5 rounded text-[11px] font-mono font-bold bg-blue-50 text-[#2563EB] border border-blue-200">
                  Elapsed: {formatTimer(elapsedSeconds)}
                </span>
              )}
            </div>
            {!uploading && (
              <button
                onClick={() => {
                  setFiles([]);
                  setFileStatuses([]);
                  if (fileInputRef.current) fileInputRef.current.value = '';
                }}
                className="text-[12px] text-red-600 hover:underline font-medium"
              >
                Clear All
              </button>
            )}
          </div>

          {/* Per-File Progress Table */}
          <div className="overflow-x-auto border border-[#E2E8F0] rounded-lg">
            <table className="w-full text-left text-[12px]">
              <thead className="bg-[#F8FAFC] border-b border-[#E2E8F0] text-[#64748B] uppercase font-bold text-[10px]">
                <tr>
                  <th className="py-2.5 px-3">File Name</th>
                  <th className="py-2.5 px-3">Size</th>
                  <th className="py-2.5 px-3">Category</th>
                  <th className="py-2.5 px-3">Status</th>
                  <th className="py-2.5 px-3 text-right">Actions</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E2E8F0]">
                {fileStatuses.map((item, idx) => (
                  <tr key={idx} className="hover:bg-[#F8FAFC]">
                    <td className="py-2.5 px-3 font-medium text-[#0F172A] max-w-[220px] truncate" title={item.name}>
                      <div className="flex items-center gap-1.5">
                        <span className="material-symbols-outlined text-[16px] text-[#64748B]">description</span>
                        <span className="truncate">{item.name}</span>
                      </div>
                    </td>
                    <td className="py-2.5 px-3 text-[#64748B]">
                      {(item.size / 1024).toFixed(1)} KB
                    </td>
                    <td className="py-2.5 px-3">
                      {item.documentType ? getDocTypeBadge(item.documentType) : <span className="text-slate-400">Queued</span>}
                    </td>
                    <td className="py-2.5 px-3">
                      {item.status === 'queued' && (
                        <span className="px-2 py-0.5 rounded text-[11px] bg-slate-100 text-slate-600 font-medium">Ready</span>
                      )}
                      {item.status === 'uploading' && (
                        <span className="inline-flex items-center gap-1 text-[11px] text-blue-600 font-medium">
                          <span className="animate-spin material-symbols-outlined text-[13px]">progress_activity</span> Uploading...
                        </span>
                      )}
                      {item.status === 'processing' && (
                        <span className="inline-flex items-center gap-1 text-[11px] text-[#2563EB] font-medium">
                          <span className="animate-spin material-symbols-outlined text-[13px]">progress_activity</span> {item.stage}
                        </span>
                      )}
                      {item.status === 'completed' && (
                        <span className="inline-flex items-center gap-1 text-[11px] text-emerald-700 font-bold">
                          <span className="material-symbols-outlined text-[14px]">check_circle</span> Processed
                        </span>
                      )}
                      {item.status === 'failed' && (
                        <span className="inline-flex items-center gap-1 text-[11px] text-red-600 font-bold" title={item.error}>
                          <span className="material-symbols-outlined text-[14px]">error</span> Error
                        </span>
                      )}
                    </td>
                    <td className="py-2.5 px-3 text-right">
                      {item.status === 'failed' ? (
                        <button
                          onClick={() => handleRetryFile(idx)}
                          className="px-2 py-1 bg-amber-50 hover:bg-amber-100 text-amber-800 border border-amber-200 rounded text-[11px] font-bold"
                        >
                          Retry
                        </button>
                      ) : !uploading ? (
                        <button
                          onClick={() => removeFile(idx)}
                          className="text-red-500 hover:text-red-700 p-0.5"
                          title="Remove file"
                        >
                          <span className="material-symbols-outlined text-[16px]">close</span>
                        </button>
                      ) : null}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>

          {/* Action Bar */}
          <div className="pt-2 flex items-center justify-between">
            <span className="text-[12px] text-[#64748B]">
              Selected documents will be processed under applicant <strong>{isNewApplicant ? (newApplicantName || 'Provisional (Name auto-detected)') : (applicantName || selectedApplicantId)}</strong>.
            </span>
            <button
              disabled={uploading || files.length === 0}
              onClick={handleUploadAndProcess}
              className="px-6 py-2.5 bg-[#0F172A] hover:bg-[#1E293B] text-white rounded-lg text-[13px] font-semibold transition-colors disabled:opacity-50 flex items-center gap-2 shadow-xs"
            >
              {uploading ? (
                <>
                  <span className="animate-spin material-symbols-outlined text-[16px]">progress_activity</span>
                  <span>Processing Pipeline ({formatTimer(elapsedSeconds)})...</span>
                </>
              ) : (
                <>
                  <span className="material-symbols-outlined text-[16px]">bolt</span>
                  <span>Upload & Run Verification Pipeline</span>
                </>
              )}
            </button>
          </div>
        </div>
      )}

      {/* Multi-Stage Visual Pipeline Progress */}
      {uploading && (
        <div className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-xs space-y-4">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-2">
              <span className="animate-spin material-symbols-outlined text-[20px] text-[#2563EB]">sync</span>
              <h3 className="text-[14px] font-bold text-[#0F172A]">Processing Intelligence Pipeline</h3>
            </div>
            <div className="text-[12px] font-mono font-bold text-[#2563EB] bg-blue-50 px-2 py-0.5 rounded border border-blue-200">
              Elapsed: {formatTimer(elapsedSeconds)}
            </div>
          </div>

          {/* Stage Step Indicators */}
          <div className="grid grid-cols-2 sm:grid-cols-6 gap-2 pt-1">
            {STAGES.map((stg, sIdx) => {
              const isPast = sIdx < currentStageIndex;
              const isCurrent = sIdx === currentStageIndex;
              return (
                <div
                  key={stg.id}
                  className={`p-2.5 rounded-lg border text-left transition-all ${
                    isCurrent
                      ? 'bg-blue-50 border-[#2563EB] shadow-xs'
                      : isPast
                      ? 'bg-emerald-50/50 border-emerald-200 text-[#0F172A]'
                      : 'bg-[#F8FAFC] border-[#E2E8F0] text-slate-400'
                  }`}
                >
                  <div className="flex items-center justify-between mb-1">
                    <span className="text-[10px] font-bold uppercase tracking-wider">
                      {stg.label}
                    </span>
                    {isPast && <span className="material-symbols-outlined text-emerald-600 text-[14px]">check</span>}
                    {isCurrent && <span className="animate-spin material-symbols-outlined text-[#2563EB] text-[12px]">progress_activity</span>}
                  </div>
                  <div className="text-[11px] text-[#64748B] leading-tight hidden sm:block">
                    {stg.desc}
                  </div>
                </div>
              );
            })}
          </div>

          <p className="text-[13px] text-[#2563EB] font-medium pt-1">
            {processingStatusText}
          </p>
        </div>
      )}

      {/* Error Message */}
      {error && (
        <div className="p-4 bg-red-50 border border-red-200 rounded-lg text-red-800 text-[13px] flex items-center gap-2">
          <span className="material-symbols-outlined text-[18px]">error</span>
          <span>{error}</span>
        </div>
      )}

      {/* Structured Comparison Matrix Display */}
      {crossComparison?.matrix && (
        <div className="space-y-4">
          <ComparisonMatrix
            matrix={crossComparison.matrix}
            applicantId={selectedApplicantId || crossComparison.matrix.applicant_id}
            applicantName={newApplicantName || crossComparison.matrix.applicant_name}
            onNavigateToQueue={onNavigateToQueue}
            onNavigateToApplicant={onNavigateToApplicant}
          />
        </div>
      )}

      {/* Individual Processed Document Cards */}
      {processedResults.length > 0 && (
        <div className="space-y-6 pt-4">
          <div className="flex items-center justify-between">
            <h2 className="font-serif text-[22px] font-bold text-[#0F172A]">
              Extracted Document Cards ({processedResults.length})
            </h2>
            <button
              onClick={() => onNavigateToQueue(processedResults[0]?.document_id)}
              className="text-[13px] font-semibold text-[#2563EB] hover:underline"
            >
              Open in Verification Queue →
            </button>
          </div>

          {processedResults.map((res, idx) => {
            const fields = res.extracted_fields || {};
            const val = res.validation || {};
            const cls = res.classification || {};

            return (
              <div key={idx} className="bg-white border border-[#E2E8F0] rounded-xl p-6 shadow-xs space-y-4">
                {/* Document Top Bar */}
                <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3 pb-3 border-b border-[#E2E8F0]">
                  <div>
                    <span className="text-[12px] font-mono text-[#64748B]">#{res.document_id.slice(0, 8)}</span>
                    <h3 className="text-[16px] font-bold text-[#0F172A]">{res.filename}</h3>
                  </div>
                  <div className="flex items-center gap-3">
                    {getDocTypeBadge(cls.classified_type)}
                    <span className="text-[12px] text-[#64748B]">
                      Confidence: <strong>{Math.round((cls.confidence || 0) * 100)}%</strong>
                    </span>
                  </div>
                </div>

                {/* Extracted Fields Grid */}
                <div>
                  <h4 className="text-[11px] font-bold text-[#64748B] uppercase tracking-wider mb-2">
                    Extracted Identity Fields
                  </h4>
                  <div className="grid grid-cols-2 sm:grid-cols-4 gap-3 text-[13px]">
                    <div className="p-3 bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg">
                      <div className="text-[11px] text-[#64748B]">Applicant Name</div>
                      <div className="font-semibold text-[#0F172A] truncate">{fields.name || 'Not detected'}</div>
                    </div>
                    <div className="p-3 bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg">
                      <div className="text-[11px] text-[#64748B]">Date of Birth</div>
                      <div className="font-semibold text-[#0F172A]">{fields.dob || 'Not detected'}</div>
                    </div>
                    <div className="p-3 bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg">
                      <div className="text-[11px] text-[#64748B]">ID Number (Masked)</div>
                      <div className="font-semibold text-[#0F172A] font-mono">{fields.masked_id || fields.id_number || 'Not detected'}</div>
                    </div>
                    <div className="p-3 bg-[#F8FAFC] border border-[#E2E8F0] rounded-lg">
                      <div className="text-[11px] text-[#64748B]">Gender / Expiry</div>
                      <div className="font-semibold text-[#0F172A]">
                        {fields.gender || (fields.expiry_date ? `Exp: ${fields.expiry_date}` : 'N/A')}
                      </div>
                    </div>
                  </div>
                </div>

                {/* Validation Checks */}
                <div>
                  <h4 className="text-[11px] font-bold text-[#64748B] uppercase tracking-wider mb-2">
                    Format & Rule Validation Checks
                  </h4>
                  <div className="space-y-1.5">
                    {(val.checks || []).map((c, cIdx) => (
                      <div key={cIdx} className="p-2.5 bg-[#F8FAFC] rounded-lg flex items-center justify-between text-[13px] border border-[#E2E8F0]">
                        <span className="font-medium text-[#0F172A]">{c.message}</span>
                        <span className={`px-2 py-0.5 rounded text-[11px] font-bold uppercase ${
                          c.status === 'pass'
                            ? 'bg-emerald-100 text-emerald-800'
                            : c.status === 'warning'
                            ? 'bg-amber-100 text-amber-800'
                            : 'bg-red-100 text-red-800'
                        }`}>
                          {c.status}
                        </span>
                      </div>
                    ))}
                  </div>
                </div>

                <div className="pt-2 flex justify-end">
                  <button
                    onClick={() => onNavigateToQueue(res.document_id)}
                    className="px-4 py-2 bg-[#2563EB] hover:bg-blue-700 text-white rounded-lg text-[13px] font-medium transition-colors"
                  >
                    Review in Verification Queue →
                  </button>
                </div>
              </div>
            );
          })}
        </div>
      )}

    </div>
  );
}
