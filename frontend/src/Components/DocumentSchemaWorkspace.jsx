import React, { useState, useEffect, useRef } from 'react';
import { api } from '../api';

/**
 * Normalizes any bounding box representation (array, dict, JSON string)
 * into a standard 4-element array [ymin, xmin, ymax, xmax] in 0-1000 scale.
 */
function normalizeBoundingBox(rawBbox) {
  if (!rawBbox) return null;
  let parsed = rawBbox;
  if (typeof parsed === 'string') {
    try {
      parsed = JSON.parse(parsed);
    } catch {
      return null;
    }
  }
  if (Array.isArray(parsed) && parsed.length >= 4) {
    const ymin = Number(parsed[0]);
    const xmin = Number(parsed[1]);
    const ymax = Number(parsed[2]);
    const xmax = Number(parsed[3]);
    if (!isNaN(ymin) && !isNaN(xmin) && !isNaN(ymax) && !isNaN(xmax) && (xmax > xmin || ymax > ymin)) {
      return [ymin, xmin, ymax, xmax];
    }
    return null;
  }
  if (typeof parsed === 'object' && parsed !== null) {
    const ymin = Number(parsed.ymin ?? parsed.top ?? parsed.y ?? 0);
    const xmin = Number(parsed.xmin ?? parsed.left ?? parsed.x ?? 0);
    const ymax = Number(parsed.ymax ?? parsed.bottom ?? (parsed.y !== undefined && parsed.height !== undefined ? parsed.y + parsed.height : 0));
    const xmax = Number(parsed.xmax ?? parsed.right ?? (parsed.x !== undefined && parsed.width !== undefined ? parsed.x + parsed.width : 0));
    if (!isNaN(ymin) && !isNaN(xmin) && !isNaN(ymax) && !isNaN(xmax) && (xmax > xmin || ymax > ymin)) {
      return [ymin, xmin, ymax, xmax];
    }
  }
  return null;
}

export default function DocumentSchemaWorkspace({
  typeKeyOrId,
  onClose,
  onSchemaUpdated,
}) {
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [successNotice, setSuccessNotice] = useState(null);

  // Type & Schema State
  const [typeData, setTypeData] = useState(null);
  const [sampleDocId, setSampleDocId] = useState(null);
  const [sampleFilename, setSampleFilename] = useState('');
  const [attributes, setAttributes] = useState([]);
  const [selectedAttrKey, setSelectedAttrKey] = useState(null);
  const [hoveredAttrKey, setHoveredAttrKey] = useState(null);
  const [searchAttrQuery, setSearchAttrQuery] = useState('');

  // Multi-page & Preview State
  const [pagesInfo, setPagesInfo] = useState({ page_count: 1, pages: [] });
  const [currentPage, setCurrentPage] = useState(1);
  const [zoomLevel, setZoomLevel] = useState(1.0);
  const [isMarqueeMode, setIsMarqueeMode] = useState(false);

  // Marquee Drag State
  const [isDrawing, setIsDrawing] = useState(false);
  const [marqueeStart, setMarqueeStart] = useState(null);
  const [marqueeCurrent, setMarqueeCurrent] = useState(null);
  const [isExtractingText, setIsExtractingText] = useState(false);

  // Add/Edit Attribute Modal State
  const [isAttrModalOpen, setIsAttrModalOpen] = useState(false);
  const [editingAttrIndex, setEditingAttrIndex] = useState(null); // null if new
  const [attrForm, setAttrForm] = useState({
    attribute_key: '',
    display_label: '',
    data_type: 'string',
    sample_value: '',
    required: false,
    validation_rule: '',
    extraction_guidance: '',
    confidence_threshold: 0.8,
    bounding_box: null,
    source_type: 'employee_created',
  });

  // Rollback Modal State
  const [isRollbackOpen, setIsRollbackOpen] = useState(false);
  const [targetRollbackVersion, setTargetRollbackVersion] = useState('');
  const [isPublishing, setIsPublishing] = useState(false);

  const containerRef = useRef(null);
  const imageRef = useRef(null);
  const attrListRef = useRef(null);

  useEffect(() => {
    loadWorkspaceData();
  }, [typeKeyOrId]);

  const loadWorkspaceData = async () => {
    try {
      setLoading(true);
      setError(null);

      // 1. Fetch sample document & type details
      const sampleRes = await api.getDocumentTypeSample(typeKeyOrId);
      const data = sampleRes.data || {};
      setTypeData(data.document_type || {});
      setSampleDocId(data.sample_document_id || null);
      setSampleFilename(data.sample_filename || 'specimen_preview.pdf');

      // 2. Load configured attributes from schema
      const activeSchema = data.details?.active_schema || {};
      const schemaAttrs = activeSchema.attributes || data.details?.attributes || [];

      // 3. If sample doc exists, load actual page info and sample extracted attributes
      if (data.sample_document_id) {
        try {
          const [pagesRes, attrsRes] = await Promise.all([
            api.getDocumentPagesInfo(data.sample_document_id),
            api.getDocumentAttributes(data.sample_document_id),
          ]);
          setPagesInfo(pagesRes.data || { page_count: 1, pages: [] });

          const extractedAttrs = attrsRes.data?.attributes || [];

          // Comprehensive alias map for KYC and document fields
          const ALIASES = {
            name: ['applicant_name', 'employee_name', 'customer_name', 'full_name'],
            applicant_name: ['name', 'employee_name', 'customer_name', 'full_name'],
            employee_name: ['name', 'applicant_name', 'full_name'],
            dob: ['date_of_birth', 'birth_date'],
            date_of_birth: ['dob', 'birth_date'],
            id_number: ['identification_number', 'aadhaar_number', 'pan_number', 'passport_number', 'licence_number', 'voter_id_number', 'employee_id'],
            identification_number: ['id_number', 'aadhaar_number', 'pan_number', 'passport_number', 'licence_number', 'voter_id_number'],
            aadhaar_number: ['identification_number', 'id_number'],
            pan_number: ['id_number', 'identification_number'],
            passport_number: ['id_number', 'identification_number'],
            licence_number: ['id_number', 'identification_number'],
            voter_id_number: ['id_number', 'identification_number'],
            employee_id: ['id_number', 'identification_number', 'emp_id'],
            gross_earnings: ['gross_salary', 'earnings', 'total_earnings'],
            net_pay: ['net_salary', 'total_net_pay', 'net_payable_amount'],
          };

          const findMatchingExtracted = (extractedList, schemaKey) => {
            const sk = (schemaKey || '').toLowerCase();
            let found = extractedList.find((ea) => (ea.attribute_key || '').toLowerCase() === sk);
            if (found) return found;
            const aliases = ALIASES[sk] || [];
            for (const alias of aliases) {
              found = extractedList.find((ea) => (ea.attribute_key || '').toLowerCase() === alias);
              if (found) return found;
            }
            return null;
          };

          let merged = [];

          if (schemaAttrs && schemaAttrs.length > 0) {
            // Merge schema attribute definitions with actual specimen extracted values
            merged = schemaAttrs.map((sa) => {
              const found = findMatchingExtracted(extractedAttrs, sa.attribute_key);
              const val = found?.normalized_value || found?.raw_value || sa.sample_value || '';
              return {
                ...sa,
                display_label: sa.display_label || sa.attribute_label || (sa.attribute_key || 'field').replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
                sample_value: val,
                bounding_box: normalizeBoundingBox(found?.bounding_box) || normalizeBoundingBox(sa.bounding_box),
                source_type: sa.source_type || found?.source_type || (data.document_type?.is_system ? 'system_standard' : 'employee_created'),
                confidence: found?.confidence || sa.confidence || null,
                page_number: found?.page_number || sa.page_number || 1,
              };
            });

            // Also include any extra discovered attributes from sample not yet in schema
            extractedAttrs.forEach((ea) => {
              const alreadyInMerged = merged.some((m) => {
                const mk = (m.attribute_key || '').toLowerCase();
                const eak = (ea.attribute_key || '').toLowerCase();
                return mk === eak || (ALIASES[mk] && ALIASES[mk].includes(eak));
              });
              if (!alreadyInMerged) {
                const val = ea.normalized_value || ea.raw_value || '';
                merged.push({
                  attribute_key: ea.attribute_key,
                  display_label: ea.attribute_label || ea.attribute_key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
                  data_type: ea.data_type || 'string',
                  sample_value: val,
                  bounding_box: normalizeBoundingBox(ea.bounding_box),
                  source_type: ea.source_type || 'ai_discovered',
                  confidence: ea.confidence || 0.95,
                  required: false,
                  validation_rule: '',
                  extraction_guidance: '',
                  page_number: ea.page_number || 1,
                });
              }
            });
          } else {
            // No prior versioned schema: populate attributes directly from specimen extraction
            merged = extractedAttrs.map((ea) => {
              const val = ea.normalized_value || ea.raw_value || '';
              return {
                attribute_key: ea.attribute_key,
                display_label: ea.attribute_label || ea.attribute_key.replace(/_/g, ' ').replace(/\b\w/g, (c) => c.toUpperCase()),
                data_type: ea.data_type || 'string',
                sample_value: val,
                bounding_box: normalizeBoundingBox(ea.bounding_box),
                source_type: ea.source_type || (data.document_type?.is_system ? 'system_standard' : 'ai_discovered'),
                confidence: ea.confidence || 0.95,
                required: false,
                validation_rule: '',
                extraction_guidance: '',
                page_number: ea.page_number || 1,
              };
            });
          }

          setAttributes(merged);
          if (merged.length > 0 && !selectedAttrKey) {
            setSelectedAttrKey(merged[0].attribute_key);
          }
        } catch (fetchErr) {
          console.warn('Could not load sample preview pages:', fetchErr);
          setAttributes(schemaAttrs);
        }
      } else {
        // No sample document exists in database for this type
        setAttributes(schemaAttrs);
      }
    } catch (err) {
      console.error('Failed to load document schema workspace:', err);
      setError(err.message || 'Failed to load document schema workspace');
    } finally {
      setLoading(false);
    }
  };

  const handleUploadSpecimenFallback = async (e) => {
    const file = e.target.files?.[0];
    if (!file) return;
    try {
      setLoading(true);
      await api.uploadDocumentTypeSample(typeKeyOrId, file);
      setSuccessNotice('Specimen document uploaded and linked successfully!');
      setTimeout(() => setSuccessNotice(null), 4000);
      await loadWorkspaceData();
    } catch (err) {
      console.error('Failed to upload fallback specimen:', err);
      setError(err.message || 'Failed to upload specimen document');
    } finally {
      setLoading(false);
    }
  };

  // --------------------------------------------------------------------------
  // Marquee Drag Handling (0-1000 Normalized Coordinates)
  // --------------------------------------------------------------------------
  const getRelativeCoordinates = (e) => {
    if (!imageRef.current) return null;
    const rect = imageRef.current.getBoundingClientRect();
    const clientX = e.clientX ?? (e.touches && e.touches[0]?.clientX);
    const clientY = e.clientY ?? (e.touches && e.touches[0]?.clientY);

    const x = Math.max(0, Math.min(rect.width, clientX - rect.left));
    const y = Math.max(0, Math.min(rect.height, clientY - rect.top));

    // Convert to normalized 0-1000 scale
    return {
      xNorm: Math.round((x / rect.width) * 1000),
      yNorm: Math.round((y / rect.height) * 1000),
    };
  };

  const handleMouseDown = (e) => {
    if (!isMarqueeMode) return;
    e.preventDefault();
    const coords = getRelativeCoordinates(e);
    if (coords) {
      setIsDrawing(true);
      setMarqueeStart(coords);
      setMarqueeCurrent(coords);
    }
  };

  const handleMouseMove = (e) => {
    if (!isDrawing || !isMarqueeMode) return;
    const coords = getRelativeCoordinates(e);
    if (coords) {
      setMarqueeCurrent(coords);
    }
  };

  const handleMouseUp = async () => {
    if (!isDrawing || !isMarqueeMode || !marqueeStart || !marqueeCurrent) {
      setIsDrawing(false);
      return;
    }
    setIsDrawing(false);

    const ymin = Math.min(marqueeStart.yNorm, marqueeCurrent.yNorm);
    const xmin = Math.min(marqueeStart.xNorm, marqueeCurrent.xNorm);
    const ymax = Math.max(marqueeStart.yNorm, marqueeCurrent.yNorm);
    const xmax = Math.max(marqueeStart.xNorm, marqueeCurrent.xNorm);

    // Filter tiny accidental clicks (< 15x15 units)
    if (xmax - xmin < 15 || ymax - ymin < 15) {
      setMarqueeStart(null);
      setMarqueeCurrent(null);
      return;
    }

    const bbox = [ymin, xmin, ymax, xmax];

    // Attempt server-side OCR extraction inside bbox
    let extractedText = '';
    if (sampleDocId) {
      try {
        setIsExtractingText(true);
        const res = await api.marqueeExtractText(sampleDocId, bbox, currentPage);
        extractedText = res.data?.extracted_text || '';
      } catch (err) {
        console.warn('Marquee extraction fallback:', err);
      } finally {
        setIsExtractingText(false);
      }
    }

    // Auto-suggest attribute key and label from text
    const cleanWord = extractedText.replace(/[^a-zA-Z0-9\s]/g, '').trim().split(/\s+/)[0] || 'custom_field';
    const suggestedKey = cleanWord.toLowerCase().substring(0, 24);
    const suggestedLabel = cleanWord.charAt(0).toUpperCase() + cleanWord.slice(1);

    // Open add attribute modal prefilled with region selection
    setAttrForm({
      attribute_key: suggestedKey,
      display_label: suggestedLabel,
      data_type: 'string',
      sample_value: extractedText,
      required: false,
      validation_rule: '',
      extraction_guidance: `Located at bbox [${ymin}, ${xmin}, ${ymax}, ${xmax}]`,
      confidence_threshold: 0.85,
      bounding_box: bbox,
      source_type: 'employee_created',
    });
    setEditingAttrIndex(null);
    setIsAttrModalOpen(true);
    setMarqueeStart(null);
    setMarqueeCurrent(null);
  };

  // --------------------------------------------------------------------------
  // Save or Update Attribute
  // --------------------------------------------------------------------------
  const handleSaveAttribute = (e) => {
    e.preventDefault();
    if (!attrForm.attribute_key.trim() || !attrForm.display_label.trim()) {
      alert('Attribute Key and Display Label are required.');
      return;
    }

    const cleanedKey = attrForm.attribute_key
      .toLowerCase()
      .replace(/[^a-z0-9_]/g, '_')
      .replace(/^_+|_+$/g, '');

    const newAttr = {
      ...attrForm,
      attribute_key: cleanedKey,
      display_label: attrForm.display_label.trim(),
      confidence_threshold: Number(attrForm.confidence_threshold) || 0.8,
    };

    if (editingAttrIndex !== null) {
      // Update existing
      setAttributes((prev) => {
        const next = [...prev];
        next[editingAttrIndex] = newAttr;
        return next;
      });
    } else {
      // Append new
      setAttributes((prev) => [...prev, newAttr]);
    }

    setSelectedAttrKey(cleanedKey);
    setIsAttrModalOpen(false);
    setSuccessNotice(`Attribute '${newAttr.display_label}' saved to draft schema.`);
    setTimeout(() => setSuccessNotice(null), 3000);
  };

  const handleRemoveAttribute = (indexToRemove) => {
    const target = attributes[indexToRemove];
    if (!target) return;
    if (!window.confirm(`Remove attribute '${target.display_label}' from this schema?`)) return;

    setAttributes((prev) => prev.filter((_, i) => i !== indexToRemove));
    if (selectedAttrKey === target.attribute_key) {
      setSelectedAttrKey(null);
    }
  };

  const openEditModal = (attr, idx) => {
    setAttrForm({
      attribute_key: attr.attribute_key,
      display_label: attr.display_label || attr.attribute_label,
      data_type: attr.data_type || 'string',
      sample_value: attr.sample_value || attr.normalized_value || '',
      required: !!attr.required,
      validation_rule: attr.validation_rule || '',
      extraction_guidance: attr.extraction_guidance || '',
      confidence_threshold: attr.confidence_threshold || 0.8,
      bounding_box: attr.bounding_box || null,
      source_type: attr.source_type || 'employee_created',
    });
    setEditingAttrIndex(idx);
    setIsAttrModalOpen(true);
  };

  // --------------------------------------------------------------------------
  // Publish New Schema Version
  // --------------------------------------------------------------------------
  const handlePublishSchema = async () => {
    if (attributes.length === 0) {
      alert('Cannot publish an empty schema. Add at least one attribute.');
      return;
    }
    try {
      setIsPublishing(true);
      const cleanDefs = attributes.map((a) => ({
        attribute_key: a.attribute_key,
        display_label: a.display_label || a.attribute_label,
        data_type: a.data_type || 'string',
        required: !!a.required,
        validation_rule: a.validation_rule || '',
        extraction_guidance: a.extraction_guidance || '',
        confidence_threshold: Number(a.confidence_threshold) || 0.8,
        bounding_box: a.bounding_box || null,
      }));

      const res = await api.publishDocumentSchema(typeData.id || typeKeyOrId, {
        schema_name: `${typeData.display_name} Schema v${(typeData.active_version || 1) + 1}`,
        attribute_definitions: cleanDefs,
      });

      setSuccessNotice(`Schema Version ${res.data?.active_version || 'new'} published successfully!`);
      if (onSchemaUpdated) onSchemaUpdated();
      setTimeout(() => setSuccessNotice(null), 4000);
      loadWorkspaceData();
    } catch (err) {
      alert(`Publishing failed: ${err.message}`);
    } finally {
      setIsPublishing(false);
    }
  };

  // --------------------------------------------------------------------------
  // Rollback to Previous Version
  // --------------------------------------------------------------------------
  const handleRollbackSchema = async () => {
    if (!targetRollbackVersion) return;
    try {
      setIsPublishing(true);
      await api.rollbackDocumentSchema(typeData.id || typeKeyOrId, targetRollbackVersion);
      setIsRollbackOpen(false);
      setSuccessNotice(`Reverted schema to Version ${targetRollbackVersion}.`);
      if (onSchemaUpdated) onSchemaUpdated();
      setTimeout(() => setSuccessNotice(null), 4000);
      loadWorkspaceData();
    } catch (err) {
      alert(`Rollback failed: ${err.message}`);
    } finally {
      setIsPublishing(false);
    }
  };

  // Filtered attributes
  const filteredAttributes = attributes.filter((a) => {
    if (!searchAttrQuery.trim()) return true;
    const q = searchAttrQuery.toLowerCase();
    return (
      a.attribute_key.toLowerCase().includes(q) ||
      (a.display_label || '').toLowerCase().includes(q) ||
      (a.sample_value || '').toLowerCase().includes(q)
    );
  });

  // Calculate live marquee drawing box in SVG scale
  const currentDrawBox = (() => {
    if (!isDrawing || !marqueeStart || !marqueeCurrent) return null;
    const ymin = Math.min(marqueeStart.yNorm, marqueeCurrent.yNorm);
    const xmin = Math.min(marqueeStart.xNorm, marqueeCurrent.xNorm);
    const ymax = Math.max(marqueeStart.yNorm, marqueeCurrent.yNorm);
    const xmax = Math.max(marqueeStart.xNorm, marqueeCurrent.xNorm);
    return { x: xmin, y: ymin, width: xmax - xmin, height: ymax - ymin };
  })();

  const activeVersion = typeData?.active_version || 1;
  const versionsList = typeData?.schemas || [];

  return (
    <div className="fixed inset-0 z-[100] bg-[#0F172A] flex flex-col font-sans">
      {/* Top Workspace Header */}
      <header className="h-14 bg-white border-b border-[#E2E8F0] px-6 flex items-center justify-between shrink-0">
        <div className="flex items-center gap-3">
          <button
            onClick={onClose}
            className="w-8 h-8 rounded-md flex items-center justify-center text-[#64748B] hover:text-[#0F172A] hover:bg-slate-100 transition-colors"
            title="Close Workspace"
          >
            <span className="text-[16px]">✕</span>
          </button>
          
          <div className="flex items-center gap-2.5">
            <h1 className="text-[15px] font-bold text-[#0F172A] tracking-tight">
              {typeData?.display_name || 'Document Attribute Mapping'}
            </h1>
            <span className="font-mono text-[11px] text-[#64748B] bg-slate-100 px-2 py-0.5 rounded">
              {typeData?.type_key}
            </span>
            <span className="px-2 py-0.5 rounded text-[11px] font-semibold bg-[#EFF6FF] text-[#2563EB]">
              Schema v{activeVersion}
            </span>
            {sampleDocId && (
              <span className="px-2 py-0.5 rounded text-[10px] font-medium bg-slate-100 text-[#475569] max-w-xs truncate" title={sampleFilename || sampleDocId}>
                Specimen: {sampleFilename || sampleDocId}
              </span>
            )}
          </div>
        </div>

        {/* Action Controls */}
        <div className="flex items-center gap-2.5">
          {successNotice && (
            <span className="text-[12px] font-medium text-emerald-700 bg-emerald-50 px-2.5 py-1 rounded border border-emerald-200 flex items-center gap-1.5 animate-in fade-in">
              <span>✓</span> {successNotice}
            </span>
          )}

          {/* Rollback button if multiple versions */}
          {versionsList.length > 1 && (
            <button
              onClick={() => setIsRollbackOpen(true)}
              className="px-3 py-1.5 text-[12px] font-medium text-[#64748B] hover:text-[#0F172A] border border-[#CBD5E1] rounded-md hover:bg-slate-50 transition-colors"
            >
              Rollback...
            </button>
          )}

          {/* Add Attribute Manual button */}
          <button
            onClick={() => {
              setAttrForm({
                attribute_key: '',
                display_label: '',
                data_type: 'string',
                sample_value: '',
                required: false,
                validation_rule: '',
                extraction_guidance: '',
                confidence_threshold: 0.8,
                bounding_box: null,
                source_type: 'employee_created',
              });
              setEditingAttrIndex(null);
              setIsAttrModalOpen(true);
            }}
            className="inline-flex items-center gap-1 px-3 py-1.5 text-[12px] font-medium bg-white border border-[#CBD5E1] hover:bg-slate-50 text-[#0F172A] rounded-md transition-colors"
          >
            <span>+</span> Add Attribute
          </button>

          {/* Publish New Schema Version */}
          <button
            onClick={handlePublishSchema}
            disabled={isPublishing}
            className="inline-flex items-center gap-1 px-3.5 py-1.5 text-[12px] font-medium bg-[#2563EB] hover:bg-[#1D4ED8] text-white rounded-md transition-colors disabled:opacity-50"
          >
            {isPublishing ? 'Publishing...' : `Publish Version (v${activeVersion + 1})`}
          </button>
        </div>
      </header>

      {/* Main Two-Panel Workspace */}
      <div className="flex-grow flex overflow-hidden">
        
        {/* ================================================================= */}
        {/* LEFT PANEL: Document Preview & Interactive SVG Overlay */}
        {/* ================================================================= */}
        <div className="flex-1 bg-[#0F172A] flex flex-col overflow-hidden relative select-none">
          
          {/* Viewer Toolbar */}
          <div className="h-12 bg-slate-900 border-b border-slate-800 px-4 flex items-center justify-between text-white text-[12px] shrink-0">
            {/* Zoom Controls */}
            <div className="flex items-center gap-2">
              <button
                onClick={() => setZoomLevel((z) => Math.max(0.6, z - 0.15))}
                className="w-7 h-7 rounded bg-slate-800 hover:bg-slate-700 flex items-center justify-center font-bold"
                title="Zoom Out"
              >
                -
              </button>
              <span className="font-mono text-[11px] w-12 text-center text-slate-300">
                {Math.round(zoomLevel * 100)}%
              </span>
              <button
                onClick={() => setZoomLevel((z) => Math.min(2.0, z + 0.15))}
                className="w-7 h-7 rounded bg-slate-800 hover:bg-slate-700 flex items-center justify-center font-bold"
                title="Zoom In"
              >
                +
              </button>
              <button
                onClick={() => setZoomLevel(1.0)}
                className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 text-[11px]"
                title="Reset Zoom to 100%"
              >
                Fit
              </button>
            </div>

            {/* Page Navigation */}
            {pagesInfo.page_count > 1 && (
              <div className="flex items-center gap-2">
                <button
                  disabled={currentPage <= 1}
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40"
                >
                  ‹ Prev
                </button>
                <span className="font-mono text-[11px] text-slate-300">
                  Page {currentPage} of {pagesInfo.page_count}
                </span>
                <button
                  disabled={currentPage >= pagesInfo.page_count}
                  onClick={() => setCurrentPage((p) => Math.min(pagesInfo.page_count, p + 1))}
                  className="px-2 py-1 rounded bg-slate-800 hover:bg-slate-700 disabled:opacity-40"
                >
                  Next ›
                </button>
              </div>
            )}

            {/* Tool Toggle: Inspect Mode vs Marquee Region Tool */}
            <div className="flex items-center gap-2 bg-slate-800 p-1 rounded-lg">
              <button
                onClick={() => setIsMarqueeMode(false)}
                className={`px-2.5 py-1 rounded text-[11px] font-semibold transition-colors ${
                  !isMarqueeMode
                    ? 'bg-[#2563EB] text-white'
                    : 'text-slate-300 hover:text-white'
                }`}
                title="Click bounding boxes to highlight attributes"
              >
                Inspect Mode
              </button>
              <button
                onClick={() => setIsMarqueeMode(true)}
                className={`px-2.5 py-1 rounded text-[11px] font-semibold transition-colors flex items-center gap-1 ${
                  isMarqueeMode
                    ? 'bg-[#2563EB] text-white shadow-xs'
                    : 'text-slate-300 hover:text-white'
                }`}
                title="Drag rectangle on document to capture text and add attribute"
              >
                <span>⛶</span> Select Region
              </button>
            </div>
          </div>

          {/* Document Canvas Container with Security Controls */}
          <div
            ref={containerRef}
            onContextMenu={(e) => {
              e.preventDefault();
              return false;
            }}
            className="flex-grow overflow-auto p-8 flex items-center justify-center relative select-none"
          >
            {loading ? (
              <div className="text-center text-slate-400">
                <div className="inline-block animate-spin w-8 h-8 border-4 border-[#2563EB] border-t-transparent rounded-full mb-2" />
                <p className="text-[12px]">Rendering high-DPI document preview...</p>
              </div>
            ) : sampleDocId ? (
              <div
                className="relative shadow-2xl transition-transform origin-center overflow-hidden rounded"
                style={{ transform: `scale(${zoomLevel})` }}
                onContextMenu={(e) => {
                  e.preventDefault();
                  return false;
                }}
              >
                {/* Rendered Document Page Image */}
                <img
                  ref={imageRef}
                  src={api.getDocumentPreviewUrl(sampleDocId, currentPage)}
                  alt="Sample Document Specimen"
                  className={`max-w-[780px] w-auto h-auto block select-none pointer-events-auto rounded bg-white ${
                    isMarqueeMode ? 'cursor-crosshair' : 'cursor-default'
                  }`}
                  onMouseDown={handleMouseDown}
                  onMouseMove={handleMouseMove}
                  onMouseUp={handleMouseUp}
                  draggable={false}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    return false;
                  }}
                />

                {/* Security Watermark Overlay */}
                <div
                  className="absolute inset-0 pointer-events-none select-none z-10 flex flex-col justify-around items-center overflow-hidden"
                  style={{
                    opacity: 0.12,
                    transform: 'rotate(-25deg) scale(1.15)',
                  }}
                >
                  <div className="text-[14px] font-mono font-bold tracking-widest text-slate-900 uppercase">
                    CONFIDENTIAL · VERIDOC KYC · SPECIMEN MAPPING · AUTHORIZED ACCESS ONLY
                  </div>
                  <div className="text-[12px] font-mono font-bold tracking-wider text-slate-900 uppercase">
                    DO NOT DISTRIBUTE · {new Date().toISOString().slice(0, 10)}
                  </div>
                </div>

                {/* Interactive SVG Bounding Box Layer */}
                <svg
                  className="absolute inset-0 w-full h-full pointer-events-none"
                  viewBox="0 0 1000 1000"
                  preserveAspectRatio="none"
                >
                  {/* Extracted Attributes Bounding Boxes */}
                  {attributes.map((attr, idx) => {
                    const bbox = normalizeBoundingBox(attr.bounding_box);
                    if (!bbox) return null;
                    const [ymin, xmin, ymax, xmax] = bbox;
                    const isSelected = selectedAttrKey === attr.attribute_key;
                    const isHovered = hoveredAttrKey === attr.attribute_key;

                    return (
                      <g
                        key={attr.attribute_key || idx}
                        className="cursor-pointer pointer-events-auto transition-all"
                        onClick={() => {
                          if (!isMarqueeMode) {
                            setSelectedAttrKey(attr.attribute_key);
                            // Scroll attribute card into view
                            const el = document.getElementById(`attr-item-${attr.attribute_key}`);
                            if (el) el.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
                          }
                        }}
                        onMouseEnter={() => setHoveredAttrKey(attr.attribute_key)}
                        onMouseLeave={() => setHoveredAttrKey(null)}
                      >
                        {/* Highlight Box */}
                        <rect
                          x={xmin}
                          y={ymin}
                          width={Math.max(10, xmax - xmin)}
                          height={Math.max(10, ymax - ymin)}
                          fill={isSelected ? 'rgba(37, 99, 235, 0.25)' : isHovered ? 'rgba(59, 130, 246, 0.15)' : 'rgba(37, 99, 235, 0.05)'}
                          stroke={isSelected ? '#2563EB' : isHovered ? '#60A5FA' : 'rgba(37, 99, 235, 0.5)'}
                          strokeWidth={isSelected ? '3' : isHovered ? '2.5' : '1.5'}
                          strokeDasharray={isSelected ? 'none' : '4,2'}
                          rx="3"
                        />

                        {/* Attribute Label Tag */}
                        {(isSelected || isHovered) && (
                          <g>
                            <rect
                              x={xmin}
                              y={Math.max(0, ymin - 22)}
                              width={Math.max(60, (attr.display_label?.length || 10) * 8 + 16)}
                              height="20"
                              fill="#0F172A"
                              rx="3"
                            />
                            <text
                              x={xmin + 6}
                              y={Math.max(14, ymin - 7)}
                              fill="#FFFFFF"
                              fontSize="11"
                              fontWeight="bold"
                              fontFamily="sans-serif"
                            >
                              {attr.display_label || attr.attribute_key}
                            </text>
                          </g>
                        )}
                      </g>
                    );
                  })}

                  {/* Active Marquee Selection Box */}
                  {currentDrawBox && (
                    <rect
                      x={currentDrawBox.x}
                      y={currentDrawBox.y}
                      width={currentDrawBox.width}
                      height={currentDrawBox.height}
                      fill="rgba(37, 99, 235, 0.20)"
                      stroke="#2563EB"
                      strokeWidth="2.5"
                      strokeDasharray="4,2"
                      rx="2"
                    />
                  )}
                </svg>

                {/* Marquee Extraction Spinner overlay */}
                {isExtractingText && (
                  <div className="absolute inset-0 bg-black/40 backdrop-blur-2xs flex items-center justify-center rounded">
                    <div className="bg-white px-4 py-2.5 rounded-lg shadow-xl text-[12px] font-semibold text-[#0F172A] flex items-center gap-2">
                      <div className="w-4 h-4 border-2 border-[#2563EB] border-t-transparent rounded-full animate-spin" />
                      Capturing spatial OCR region...
                    </div>
                  </div>
                )}
              </div>
            ) : (
              <div className="text-center text-slate-400 p-8 border border-dashed border-slate-700 rounded-xl max-w-md">
                <div className="w-12 h-12 rounded-full bg-slate-800 text-slate-400 flex items-center justify-center mx-auto mb-3">
                  <span className="material-symbols-outlined text-[28px]">description</span>
                </div>
                <p className="font-semibold text-[14px] text-white">No Specimen Document in Database</p>
                <p className="text-[12px] mt-1.5 text-slate-400 leading-relaxed">
                  No uploaded document exists for document type <span className="text-blue-400 font-semibold">{typeData?.display_name || typeKeyOrId}</span> in the database yet.
                </p>
                <div className="mt-4 pt-4 border-t border-slate-800 flex flex-col items-center gap-2">
                  <label className="inline-flex items-center gap-2 px-4 py-2 bg-[#2563EB] hover:bg-blue-600 text-white text-[12px] font-semibold rounded-lg cursor-pointer transition-colors shadow-sm">
                    <span className="material-symbols-outlined text-[16px]">upload_file</span>
                    Upload Specimen Document
                    <input
                      type="file"
                      accept=".pdf,.png,.jpg,.jpeg"
                      className="hidden"
                      onChange={handleUploadSpecimenFallback}
                    />
                  </label>
                  <span className="text-[11px] text-slate-500">Upload a representative sample to activate visual spatial mapping</span>
                </div>
              </div>
            )}
          </div>

          {/* Marquee Guidance Strip */}
          {isMarqueeMode && (
            <div className="h-8 bg-blue-600 text-white text-[11px] font-semibold px-4 flex items-center justify-between shrink-0">
              <span>⛶ Marquee Active: Drag a rectangle over text on the document to capture and configure it as an attribute.</span>
              <button
                onClick={() => setIsMarqueeMode(false)}
                className="underline hover:text-blue-100"
              >
                Cancel Selection
              </button>
            </div>
          )}
        </div>

        {/* ================================================================= */}
        {/* RIGHT PANEL: Extracted Attributes & Schema Configuration */}
        {/* ================================================================= */}
        <div className="w-[480px] bg-white border-l border-[#E2E8F0] flex flex-col shrink-0">
          
          {/* Panel Header & Search Filter */}
          <div className="p-4 border-b border-[#E2E8F0] bg-[#F8FAFC] space-y-3 shrink-0">
            <div className="flex items-center justify-between">
              <div>
                <h2 className="text-[13px] font-bold text-[#0F172A] uppercase tracking-wider">
                  Configured Attributes ({attributes.length})
                </h2>
                <p className="text-[11px] text-[#64748B]">
                  Click attribute to highlight bounding box on specimen canvas
                </p>
              </div>
            </div>

            {/* Quick Search */}
            <div className="relative">
              <input
                type="text"
                value={searchAttrQuery}
                onChange={(e) => setSearchAttrQuery(e.target.value)}
                placeholder="Filter attributes by label or key..."
                className="w-full px-3 py-1.5 pl-8 text-[12px] rounded-lg border border-[#CBD5E1] bg-white text-[#0F172A] focus:outline-none focus:ring-2 focus:ring-[#2563EB]"
              />
              <span className="material-symbols-outlined text-[16px] text-slate-400 absolute left-2.5 top-2">
                search
              </span>
            </div>
          </div>

          {/* Attribute Cards List */}
          <div
            ref={attrListRef}
            className="flex-grow overflow-y-auto p-4 space-y-2.5 divide-y divide-slate-100"
          >
            {filteredAttributes.length > 0 ? (
              filteredAttributes.map((attr, idx) => {
                const isSelected = selectedAttrKey === attr.attribute_key;
                const bbox = normalizeBoundingBox(attr.bounding_box);

                return (
                  <div
                    key={attr.attribute_key || idx}
                    id={`attr-item-${attr.attribute_key}`}
                    onClick={() => setSelectedAttrKey(attr.attribute_key)}
                    onMouseEnter={() => setHoveredAttrKey(attr.attribute_key)}
                    onMouseLeave={() => setHoveredAttrKey(null)}
                    className={`pt-2.5 first:pt-0 p-3 rounded-xl border transition-all cursor-pointer ${
                      isSelected
                        ? 'border-[#2563EB] bg-[#EFF6FF]/60 shadow-xs ring-1 ring-[#2563EB]'
                        : 'border-[#E2E8F0] hover:border-slate-300 hover:bg-slate-50'
                    }`}
                  >
                    {/* Top Row: Label & Source Badge */}
                    <div className="flex items-center justify-between gap-2">
                      <div className="flex items-center gap-2 truncate">
                        <span className={`w-2 h-2 rounded-full ${isSelected ? 'bg-[#2563EB]' : 'bg-slate-400'}`} />
                        <span className="font-bold text-[13px] text-[#0F172A] truncate">
                          {attr.display_label || attr.attribute_key}
                        </span>
                        {attr.required && (
                          <span className="text-[10px] font-bold text-rose-600 bg-rose-50 px-1.5 py-0.2 rounded border border-rose-200">
                            REQ
                          </span>
                        )}
                      </div>

                      <div className="flex items-center gap-1 shrink-0">
                        <span className="text-[10px] font-mono uppercase bg-slate-100 text-[#475569] px-2 py-0.5 rounded">
                          {attr.data_type || 'string'}
                        </span>
                        <span className={`text-[10px] font-semibold px-2 py-0.5 rounded ${
                          attr.source_type === 'system_standard'
                            ? 'bg-blue-50 text-blue-700 border border-blue-200'
                            : attr.source_type === 'ai_discovered'
                            ? 'bg-purple-50 text-purple-700 border border-purple-200'
                            : 'bg-emerald-50 text-emerald-700 border border-emerald-200'
                        }`}>
                          {attr.source_type === 'system_standard' ? 'Standard' : attr.source_type === 'ai_discovered' ? 'Discovered' : 'Custom'}
                        </span>
                      </div>
                    </div>

                    {/* Slug Key & Sample Value */}
                    <div className="mt-2 space-y-1 text-[12px]">
                      <div className="flex items-center justify-between text-[#64748B] flex-wrap gap-1">
                        <span className="font-mono text-[11px]">key: {attr.attribute_key}</span>
                        {bbox ? (
                          <span className="inline-flex items-center gap-1 text-[10px] text-emerald-700 bg-emerald-50 px-1.5 py-0.5 rounded border border-emerald-200 font-medium">
                            <span className="material-symbols-outlined text-[11px]">crop_free</span>
                            Region [{bbox[0]}, {bbox[1]}, {bbox[2]}, {bbox[3]}]
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 text-[10px] text-amber-700 bg-amber-50 px-1.5 py-0.5 rounded border border-amber-200 font-medium" title="Click 'Associate Region' to draw and link canvas coordinates">
                            <span className="material-symbols-outlined text-[11px]">highlight_off</span>
                            No Spatial Coordinates
                          </span>
                        )}
                      </div>

                      <div className="bg-white border border-[#E2E8F0] p-2 rounded-md font-mono text-[11px] text-[#0F172A] break-words">
                        {attr.sample_value ? (
                          <span>{attr.sample_value}</span>
                        ) : (
                          <span className="text-slate-400 italic">No sample value mapped</span>
                        )}
                      </div>
                    </div>

                    {/* Action Buttons */}
                    <div className="mt-2 pt-2 border-t border-[#F1F5F9] flex items-center justify-between text-[11px]">
                      <div className="flex items-center gap-2">
                        {bbox ? (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setSelectedAttrKey(attr.attribute_key);
                            }}
                            className="text-[#2563EB] hover:underline font-semibold"
                          >
                            Highlight on Specimen
                          </button>
                        ) : sampleDocId && (
                          <button
                            type="button"
                            onClick={(e) => {
                              e.stopPropagation();
                              setIsMarqueeMode(true);
                              setSelectedAttrKey(attr.attribute_key);
                            }}
                            className="text-amber-700 hover:underline font-semibold flex items-center gap-1"
                          >
                            <span className="material-symbols-outlined text-[13px]">crop</span>
                            Associate Region
                          </button>
                        )}
                      </div>

                      <div className="flex items-center gap-3">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            openEditModal(attr, idx);
                          }}
                          className="text-[#475569] hover:text-[#0F172A] font-semibold"
                        >
                          Configure Rule
                        </button>
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            handleRemoveAttribute(idx);
                          }}
                          className="text-rose-600 hover:text-rose-800 font-semibold"
                        >
                          Remove
                        </button>
                      </div>
                    </div>
                  </div>
                );
              })
            ) : (
              <div className="text-center py-12 text-[#64748B] text-[12px]">
                No attributes match your filter.
              </div>
            )}
          </div>

          {/* Panel Footer: Explicit In-Context Learning Disclaimer */}
          <div className="p-3 bg-[#F8FAFC] border-t border-[#E2E8F0] text-[11px] text-[#64748B] space-y-1 shrink-0">
            <div className="flex items-center gap-1.5 font-bold text-[#0F172A]">
              <span className="w-1.5 h-1.5 rounded-full bg-[#2563EB]" />
              In-Context Schema Learning
            </div>
            <p className="leading-tight">
              Schema updates configure anchor phrases and in-context few-shot extraction rules. Underlying foundation model weights are not modified.
            </p>
          </div>

        </div>
      </div>

      {/* ================================================================= */}
      {/* Modal: Add or Edit Attribute */}
      {/* ================================================================= */}
      {isAttrModalOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6 border border-[#E2E8F0] space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-[#F1F5F9]">
              <h3 className="font-bold text-[15px] text-[#0F172A]">
                {editingAttrIndex !== null ? 'Configure Attribute' : 'Add New Attribute'}
              </h3>
              <button
                onClick={() => setIsAttrModalOpen(false)}
                className="text-[#94A3B8] hover:text-[#0F172A]"
              >
                ✕
              </button>
            </div>

            <form onSubmit={handleSaveAttribute} className="space-y-3 text-[13px]">
              <div>
                <label className="block font-semibold text-[#334155] mb-1">Display Label</label>
                <input
                  type="text"
                  value={attrForm.display_label}
                  onChange={(e) => {
                    const val = e.target.value;
                    const autoKey = val.toLowerCase().replace(/[^a-z0-9_]/g, '_').replace(/^_+|_+$/g, '');
                    setAttrForm((prev) => ({
                      ...prev,
                      display_label: val,
                      attribute_key: prev.attribute_key ? prev.attribute_key : autoKey,
                    }));
                  }}
                  className="w-full px-3 py-2 rounded-lg border border-[#CBD5E1] text-[13px] focus:outline-none focus:ring-2 focus:ring-[#2563EB]"
                  placeholder="e.g. Permanent Account Number"
                  required
                />
              </div>

              <div>
                <label className="block font-semibold text-[#334155] mb-1">Slug Key</label>
                <input
                  type="text"
                  value={attrForm.attribute_key}
                  onChange={(e) => setAttrForm({ ...attrForm, attribute_key: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-[#CBD5E1] font-mono text-[12px] focus:outline-none focus:ring-2 focus:ring-[#2563EB]"
                  placeholder="e.g. pan_number"
                  required
                />
              </div>

              <div className="grid grid-cols-2 gap-3">
                <div>
                  <label className="block font-semibold text-[#334155] mb-1">Data Type</label>
                  <select
                    value={attrForm.data_type}
                    onChange={(e) => setAttrForm({ ...attrForm, data_type: e.target.value })}
                    className="w-full px-3 py-2 rounded-lg border border-[#CBD5E1] text-[12px]"
                  >
                    <option value="string">String / Text</option>
                    <option value="date">ISO Date (YYYY-MM-DD)</option>
                    <option value="number">Numeric</option>
                    <option value="currency">Currency / Amount</option>
                  </select>
                </div>

                <div>
                  <label className="block font-semibold text-[#334155] mb-1">Confidence Threshold</label>
                  <input
                    type="number"
                    step="0.05"
                    min="0.1"
                    max="1.0"
                    value={attrForm.confidence_threshold}
                    onChange={(e) => setAttrForm({ ...attrForm, confidence_threshold: parseFloat(e.target.value) })}
                    className="w-full px-3 py-2 rounded-lg border border-[#CBD5E1] text-[12px]"
                  />
                </div>
              </div>

              <div>
                <label className="block font-semibold text-[#334155] mb-1">Sample Value</label>
                <input
                  type="text"
                  value={attrForm.sample_value}
                  onChange={(e) => setAttrForm({ ...attrForm, sample_value: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-[#CBD5E1] font-mono text-[12px]"
                  placeholder="Extracted or verified specimen text"
                />
              </div>

              <div>
                <label className="block font-semibold text-[#334155] mb-1">Regex Validation Pattern (Optional)</label>
                <input
                  type="text"
                  value={attrForm.validation_rule}
                  onChange={(e) => setAttrForm({ ...attrForm, validation_rule: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-[#CBD5E1] font-mono text-[11px]"
                  placeholder="e.g. ^[A-Z]{5}[0-9]{4}[A-Z]$"
                />
              </div>

              <div>
                <label className="block font-semibold text-[#334155] mb-1">Anchor Phrase / Extraction Guidance</label>
                <input
                  type="text"
                  value={attrForm.extraction_guidance}
                  onChange={(e) => setAttrForm({ ...attrForm, extraction_guidance: e.target.value })}
                  className="w-full px-3 py-2 rounded-lg border border-[#CBD5E1] text-[12px]"
                  placeholder="e.g. Preceded by label 'Permanent Account Number'"
                />
              </div>

              <div className="flex items-center gap-2 pt-1">
                <input
                  type="checkbox"
                  id="req_check"
                  checked={attrForm.required}
                  onChange={(e) => setAttrForm({ ...attrForm, required: e.target.checked })}
                  className="rounded border-[#CBD5E1] text-[#2563EB]"
                />
                <label htmlFor="req_check" className="font-semibold text-[#334155] text-[12px]">
                  Field is mandatory for document validity
                </label>
              </div>

              <div className="flex justify-end gap-2 pt-3 border-t border-[#F1F5F9]">
                <button
                  type="button"
                  onClick={() => setIsAttrModalOpen(false)}
                  className="px-4 py-2 rounded-lg border border-[#CBD5E1] text-[12px] font-semibold text-[#64748B] hover:bg-slate-50"
                >
                  Cancel
                </button>
                <button
                  type="submit"
                  className="px-4 py-2 rounded-lg bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-[12px] font-semibold shadow-xs"
                >
                  Save Attribute
                </button>
              </div>
            </form>
          </div>
        </div>
      )}

      {/* ================================================================= */}
      {/* Modal: Rollback Schema */}
      {/* ================================================================= */}
      {isRollbackOpen && (
        <div className="fixed inset-0 z-50 bg-black/50 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-sm w-full p-6 border border-[#E2E8F0] space-y-4">
            <div className="flex items-center justify-between pb-2 border-b border-[#F1F5F9]">
              <h3 className="font-bold text-[15px] text-[#0F172A]">Revert Schema Version</h3>
              <button onClick={() => setIsRollbackOpen(false)} className="text-[#94A3B8]">✕</button>
            </div>
            <p className="text-[12px] text-[#64748B]">
              Select a prior version to atomically restore. The selected definitions will immediately become active for extraction.
            </p>
            <div>
              <select
                value={targetRollbackVersion}
                onChange={(e) => setTargetRollbackVersion(e.target.value)}
                className="w-full px-3 py-2 rounded-lg border border-[#CBD5E1] text-[13px]"
              >
                <option value="">Choose version to restore...</option>
                {versionsList.map((v) => (
                  <option key={v.version} value={v.version}>
                    Version {v.version} ({v.created_at ? v.created_at.slice(0, 10) : 'Archived'})
                  </option>
                ))}
              </select>
            </div>
            <div className="flex justify-end gap-2 pt-2">
              <button
                onClick={() => setIsRollbackOpen(false)}
                className="px-3 py-1.5 rounded-lg border border-[#CBD5E1] text-[12px]"
              >
                Cancel
              </button>
              <button
                onClick={handleRollbackSchema}
                disabled={!targetRollbackVersion || isPublishing}
                className="px-4 py-1.5 rounded-lg bg-[#2563EB] text-white text-[12px] font-semibold disabled:opacity-50"
              >
                {isPublishing ? 'Restoring...' : 'Confirm Rollback'}
              </button>
            </div>
          </div>
        </div>
      )}

    </div>
  );
}
