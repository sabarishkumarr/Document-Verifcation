import React, { useState, useEffect, useRef, Component } from 'react';
import { api } from '../api';

/**
 * Normalizes any bounding box representation (array, dict, JSON string)
 * into a standard 4-element array [ymin, xmin, ymax, xmax] in 0-1000 scale.
 */
export function normalizeBoundingBox(rawBbox) {
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
    if (!isNaN(ymin) && !isNaN(xmin) && !isNaN(ymax) && !isNaN(xmax)) {
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

class VisualWorkspaceErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }
  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }
  componentDidCatch(error, errorInfo) {
    console.error('VisualDocumentWorkspace runtime crash caught by ErrorBoundary:', error, errorInfo);
  }
  render() {
    if (this.state.hasError) {
      return (
        <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-4">
          <div className="bg-white rounded-2xl shadow-2xl max-w-lg w-full p-6 border border-red-200 space-y-4">
            <div className="flex items-center gap-3 text-red-600">
              <span className="material-symbols-outlined text-[32px]">error</span>
              <div>
                <h3 className="font-bold text-[16px] text-slate-900">Workspace Inspection Error</h3>
                <p className="text-[12px] text-slate-500">A runtime error occurred while rendering the document workspace.</p>
              </div>
            </div>
            <div className="p-3 bg-red-50 border border-red-200 rounded-lg text-[12px] font-mono text-red-800 break-words">
              {this.state.error?.message || 'Unknown inspection error'}
            </div>
            <div className="flex justify-end pt-2">
              <button
                onClick={this.props.onClose}
                className="px-4 py-2 bg-slate-900 hover:bg-slate-800 text-white rounded-lg text-[12px] font-semibold"
              >
                Close Workspace
              </button>
            </div>
          </div>
        </div>
      );
    }
    return this.props.children;
  }
}

/**
 * VeriDoc AI 2.0 — Visual Document Workspace & Interactive Marquee Extraction
 * 
 * Features:
 * - Side-by-side interactive document canvas & attribute inspector
 * - Multi-page rendering with PyMuPDF high-DPI image previews
 * - Interactive SVG Bounding Box overlay with 0-1000 normalized coordinates
 * - Bi-directional highlight synchronization (table hover <-> document canvas)
 * - Click-and-drag Marquee tool for custom OCR / spatial token extraction
 * - Custom attribute creation & persistence
 */
function VisualDocumentWorkspaceInner({ documentId, onClose, onAttributeUpdated, officerName = 'Arjun Mehta' }) {
  // Document and Page State
  const [docInfo, setDocInfo] = useState(null);
  const [pagesInfo, setPagesInfo] = useState({ page_count: 1, pages: [] });
  const [currentPage, setCurrentPage] = useState(1);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);
  const [previewToken, setPreviewToken] = useState(null);

  // Attributes & Spatial Data
  const [attributes, setAttributes] = useState([]);
  const [spatialTokens, setSpatialTokens] = useState([]);
  const [activeHighlightId, setActiveHighlightId] = useState(null);
  const [searchTerm, setSearchTerm] = useState('');
  const [filterSource, setFilterSource] = useState('all'); // all, standard, discovered, custom

  // Viewport Zoom & Pan
  const [zoomLevel, setZoomLevel] = useState(1.0);
  const viewportRef = useRef(null);
  const imgRef = useRef(null);
  const overlayRef = useRef(null);

  // Marquee Selection Tool State
  const [isMarqueeMode, setIsMarqueeMode] = useState(false);
  const [isDragging, setIsDragging] = useState(false);
  const [dragStart, setDragStart] = useState(null);
  const [dragCurrent, setDragCurrent] = useState(null);
  const [marqueeExtracting, setMarqueeExtracting] = useState(false);

  // Custom Attribute Modal State
  const [customAttrModal, setCustomAttrModal] = useState({
    isOpen: false,
    key: '',
    label: '',
    value: '',
    dataType: 'string',
    bbox: null,
    page: 1,
    saving: false,
  });

  // Load document pages info and extracted attributes
  useEffect(() => {
    if (!documentId) return;
    loadDocumentWorkspace();
  }, [documentId]);

  const loadDocumentWorkspace = async () => {
    setLoading(true);
    setError(null);
    try {
      // 0. Request short-lived preview session token
      try {
        const tokenRes = await api.generateDocumentPreviewToken(documentId, officerName);
        if (tokenRes.data?.preview_token) {
          setPreviewToken(tokenRes.data.preview_token);
        }
      } catch (e) {
        console.warn('Authorized preview session note:', e);
      }

      // 1. Fetch document metadata
      const detailsRes = await api.getDocumentDetails(documentId);
      setDocInfo(detailsRes.data?.document || null);

      // 2. Fetch page dimensions and counts
      try {
        const pagesRes = await api.getDocumentPagesInfo(documentId);
        if (pagesRes.data?.pages?.length > 0) {
          setPagesInfo(pagesRes.data);
        }
      } catch (e) {
        console.warn('Page info fallback:', e);
      }

      // 3. Fetch normalized attributes and spatial tokens
      const attrRes = await api.getDocumentAttributes(documentId);
      const rawAttrs = attrRes.data?.attributes || [];
      const normalizedAttrs = rawAttrs.map((a) => ({
        ...a,
        bounding_box: normalizeBoundingBox(a.bounding_box),
      }));
      setAttributes(normalizedAttrs);
      setSpatialTokens(attrRes.data?.spatial_tokens || []);
    } catch (err) {
      console.error('Failed to load workspace data:', err);
      setError(err.message || 'Failed to load visual document workspace.');
    } finally {
      setLoading(false);
    }
  };

  // --------------------------------------------------------------------------
  // Marquee Drag Handlers (Normalized 0-1000 coordinate space)
  // --------------------------------------------------------------------------
  const getNormalizedCoords = (e) => {
    if (!overlayRef.current) return { x: 0, y: 0 };
    const rect = overlayRef.current.getBoundingClientRect();
    const clientX = e.clientX ?? (e.touches && e.touches[0]?.clientX);
    const clientY = e.clientY ?? (e.touches && e.touches[0]?.clientY);

    const relX = Math.max(0, Math.min(rect.width, clientX - rect.left));
    const relY = Math.max(0, Math.min(rect.height, clientY - rect.top));

    return {
      x: Math.round((relX / rect.width) * 1000),
      y: Math.round((relY / rect.height) * 1000),
    };
  };

  const handleMouseDown = (e) => {
    if (!isMarqueeMode) return;
    e.preventDefault();
    const coords = getNormalizedCoords(e);
    setIsDragging(true);
    setDragStart(coords);
    setDragCurrent(coords);
  };

  const handleMouseMove = (e) => {
    if (!isMarqueeMode || !isDragging) return;
    const coords = getNormalizedCoords(e);
    setDragCurrent(coords);
  };

  const handleMouseUp = async () => {
    if (!isMarqueeMode || !isDragging || !dragStart || !dragCurrent) {
      setIsDragging(false);
      return;
    }
    setIsDragging(false);

    const xmin = Math.min(dragStart.x, dragCurrent.x);
    const xmax = Math.max(dragStart.x, dragCurrent.x);
    const ymin = Math.min(dragStart.y, dragCurrent.y);
    const ymax = Math.max(dragStart.y, dragCurrent.y);

    // Filter out accidental clicks (minimum area threshold)
    if (xmax - xmin < 15 || ymax - ymin < 10) {
      setDragStart(null);
      setDragCurrent(null);
      return;
    }

    const bbox = [ymin, xmin, ymax, xmax];
    setDragStart(null);
    setDragCurrent(null);

    // Call Marquee extraction endpoint
    setMarqueeExtracting(true);
    try {
      const res = await api.marqueeExtractText(documentId, bbox, currentPage);
      const text = res.data?.extracted_text || '';
      
      // Auto-suggest a key name from text snippet
      let suggestedKey = text
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '_')
        .slice(0, 24)
        .replace(/^_+|_+$/g, '');
      if (!suggestedKey || suggestedKey.length < 2) suggestedKey = 'custom_field';

      let suggestedLabel = text.length > 0 && text.length < 30
        ? text
        : suggestedKey.replace(/_/g, ' ').replace(/\b\w/g, c => c.toUpperCase());

      // Open creation modal
      setCustomAttrModal({
        isOpen: true,
        key: suggestedKey,
        label: suggestedLabel,
        value: text,
        dataType: /\d{4}-\d{2}-\d{2}/.test(text) ? 'date' : /^\$?\d+(\.\d+)?$/.test(text) ? 'currency' : 'string',
        bbox: bbox,
        page: currentPage,
        saving: false,
      });
    } catch (err) {
      console.error('Marquee extract error:', err);
    } finally {
      setMarqueeExtracting(false);
    }
  };

  // --------------------------------------------------------------------------
  // Custom Attribute Operations
  // --------------------------------------------------------------------------
  const handleSaveCustomAttribute = async () => {
    if (!customAttrModal.key.trim() || customAttrModal.value === '') return;
    setCustomAttrModal((prev) => ({ ...prev, saving: true }));
    try {
      const res = await api.addCustomAttribute(documentId, {
        attribute_key: customAttrModal.key.trim(),
        attribute_label: customAttrModal.label.trim() || customAttrModal.key.trim(),
        raw_value: customAttrModal.value,
        data_type: customAttrModal.dataType,
        bounding_box: customAttrModal.bbox,
        page_number: customAttrModal.page,
        source_type: 'custom',
      });

      const newAttr = res.data;
      setAttributes((prev) => [...prev, newAttr]);
      setActiveHighlightId(newAttr.id);
      setCustomAttrModal((prev) => ({ ...prev, isOpen: false, saving: false }));
      if (onAttributeUpdated) onAttributeUpdated();
    } catch (err) {
      alert(`Failed to save attribute: ${err.message}`);
      setCustomAttrModal((prev) => ({ ...prev, saving: false }));
    }
  };

  const handleDeleteAttribute = async (attrId, e) => {
    e.stopPropagation();
    if (!window.confirm('Are you sure you want to delete this custom attribute?')) return;
    try {
      await api.deleteCustomAttribute(documentId, attrId);
      setAttributes((prev) => prev.filter((a) => a.id !== attrId));
      if (activeHighlightId === attrId) setActiveHighlightId(null);
      if (onAttributeUpdated) onAttributeUpdated();
    } catch (err) {
      alert(`Failed to delete attribute: ${err.message}`);
    }
  };

  // Copy JSON to clipboard
  const handleCopyJson = () => {
    const jsonStr = JSON.stringify(attributes, null, 2);
    navigator.clipboard.writeText(jsonStr);
    alert('Extracted attributes JSON copied to clipboard!');
  };

  // Filter attributes for display
  const filteredAttributes = attributes.filter((attr) => {
    const key = (attr.attribute_key || '').toLowerCase();
    const label = (attr.attribute_label || '').toLowerCase();
    const val = String(attr.normalized_value || attr.raw_value || '').toLowerCase();
    const matchesSearch = !searchTerm || key.includes(searchTerm.toLowerCase()) || label.includes(searchTerm.toLowerCase()) || val.includes(searchTerm.toLowerCase());

    const source = (attr.source_type || 'standard').toLowerCase();
    let matchesSource = true;
    if (filterSource === 'custom') matchesSource = source === 'custom';
    else if (filterSource === 'discovered') matchesSource = source === 'discovered';
    else if (filterSource === 'standard') matchesSource = source === 'standard';

    return matchesSearch && matchesSource;
  });

  const previewUrl = api.getDocumentPreviewUrl(documentId, currentPage, previewToken);

  // SVG Active drag rectangle
  const dragRect = isDragging && dragStart && dragCurrent ? {
    x: Math.min(dragStart.x, dragCurrent.x),
    y: Math.min(dragStart.y, dragCurrent.y),
    width: Math.abs(dragCurrent.x - dragStart.x),
    height: Math.abs(dragCurrent.y - dragStart.y),
  } : null;

  return (
    <div className="fixed inset-0 z-50 bg-black/60 backdrop-blur-xs flex items-center justify-center p-3 md:p-6 overflow-hidden">
      <div className="bg-white rounded-2xl shadow-2xl w-full max-w-[1440px] h-[92vh] flex flex-col border border-slate-200 overflow-hidden">
        
        {/* ================================================================= */}
        {/* Top Header & Toolbar */}
        {/* ================================================================= */}
        <header className="px-5 py-3.5 bg-slate-900 text-white flex items-center justify-between border-b border-slate-800 shrink-0">
          <div className="flex items-center gap-3">
            <div className="p-2 bg-blue-600 rounded-lg text-white shadow-xs">
              <span className="material-symbols-outlined text-[20px]">document_scanner</span>
            </div>
            <div>
              <div className="flex items-center gap-2">
                <h2 className="font-bold text-[15px] text-white truncate max-w-[320px]">
                  {docInfo?.original_filename || 'Document Workspace'}
                </h2>
                <span className="px-2 py-0.5 rounded text-[10px] font-mono font-bold uppercase bg-blue-500/20 text-blue-300 border border-blue-500/30">
                  {docInfo?.classified_type || docInfo?.document_type || 'Unknown'}
                </span>
                <span className="text-[11px] font-mono text-slate-400">
                  #{documentId.slice(0, 8)}
                </span>
              </div>
              <p className="text-[11px] text-slate-400">
                Visual Intelligence Workspace • {attributes.length} Extracted Attribute(s)
              </p>
            </div>
          </div>

          {/* Action Toolbar */}
          <div className="flex items-center gap-2.5">
            {/* Protected Viewer Security Badge */}
            <div className="hidden sm:flex items-center gap-1.5 px-2.5 py-1 rounded bg-slate-800 text-[11px] text-emerald-400 border border-emerald-500/30" title="Active document security: Context menu disabled, direct downloads restricted, access logged in audit ledger. Note: Operating system screenshot utilities and external cameras cannot be blocked by browser code.">
              <span className="material-symbols-outlined text-[14px]">shield</span>
              <span>Protected Inspection</span>
            </div>

            {/* Marquee Selection Tool Toggle */}
            <button
              onClick={() => setIsMarqueeMode(!isMarqueeMode)}
              className={`px-3 py-1.5 rounded-lg text-[12px] font-semibold flex items-center gap-1.5 transition-all shadow-xs ${
                isMarqueeMode
                  ? 'bg-amber-500 hover:bg-amber-600 text-slate-950 font-bold ring-2 ring-amber-300'
                  : 'bg-slate-800 hover:bg-slate-700 text-slate-200 border border-slate-700'
              }`}
              title="Click and drag on the document image to extract custom bounding boxes and text"
            >
              <span className="material-symbols-outlined text-[16px]">crop</span>
              {isMarqueeMode ? 'Marquee Mode Active' : 'Marquee OCR Tool'}
            </button>

            {/* Add Custom Attribute Manually */}
            <button
              onClick={() =>
                setCustomAttrModal({
                  isOpen: true,
                  key: '',
                  label: '',
                  value: '',
                  dataType: 'string',
                  bbox: null,
                  page: currentPage,
                  saving: false,
                })
              }
              className="px-3 py-1.5 bg-blue-600 hover:bg-blue-700 text-white rounded-lg text-[12px] font-semibold flex items-center gap-1.5 transition-colors shadow-xs"
            >
              <span className="material-symbols-outlined text-[16px]">add_circle</span>
              Add Attribute
            </button>

            {/* Export JSON */}
            <button
              onClick={handleCopyJson}
              className="px-3 py-1.5 bg-slate-800 hover:bg-slate-700 text-slate-300 rounded-lg text-[12px] font-medium flex items-center gap-1 transition-colors border border-slate-700"
              title="Copy all extracted attributes as JSON"
            >
              <span className="material-symbols-outlined text-[16px]">code</span>
              JSON
            </button>

            {/* Close Button */}
            <button
              onClick={onClose}
              className="p-1.5 rounded-lg hover:bg-slate-800 text-slate-400 hover:text-white transition-colors ml-2"
              title="Close Workspace"
            >
              <span className="material-symbols-outlined text-[22px]">close</span>
            </button>
          </div>
        </header>

        {/* ================================================================= */}
        {/* Main Split Layout: Document Canvas (Left) + Attribute Table (Right) */}
        {/* ================================================================= */}
        <div className="flex-1 flex flex-col lg:flex-row overflow-hidden bg-slate-100">
          
          {/* --------------------------------------------------------------- */}
          {/* LEFT: Document Canvas & Interactive Bounding Box Viewport */}
          {/* --------------------------------------------------------------- */}
          <div className="flex-1 flex flex-col bg-slate-900/95 overflow-hidden border-r border-slate-700/60 relative">
            
            {/* Viewport Control Bar */}
            <div className="h-10 bg-slate-800/90 border-b border-slate-700/70 px-4 flex items-center justify-between text-slate-300 text-[12px]">
              {/* Page Navigator */}
              <div className="flex items-center gap-1.5">
                <button
                  disabled={currentPage <= 1}
                  onClick={() => setCurrentPage((p) => Math.max(1, p - 1))}
                  className="p-1 rounded hover:bg-slate-700 disabled:opacity-30 disabled:hover:bg-transparent"
                >
                  <span className="material-symbols-outlined text-[16px]">chevron_left</span>
                </button>
                <span className="font-mono text-[11px] px-2 py-0.5 bg-slate-900 rounded border border-slate-700">
                  Page {currentPage} of {pagesInfo.page_count || 1}
                </span>
                <button
                  disabled={currentPage >= (pagesInfo.page_count || 1)}
                  onClick={() => setCurrentPage((p) => Math.min(pagesInfo.page_count || 1, p + 1))}
                  className="p-1 rounded hover:bg-slate-700 disabled:opacity-30 disabled:hover:bg-transparent"
                >
                  <span className="material-symbols-outlined text-[16px]">chevron_right</span>
                </button>
              </div>

              {/* Marquee Mode Indicator */}
              {isMarqueeMode && (
                <div className="flex items-center gap-1.5 text-amber-300 font-semibold text-[11px] animate-pulse">
                  <span className="material-symbols-outlined text-[14px]">crosshair</span>
                  <span>Drag across text to capture new attribute</span>
                </div>
              )}

              {/* Zoom Controls */}
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setZoomLevel((z) => Math.max(0.5, Math.round((z - 0.15) * 100) / 100))}
                  className="p-1 rounded hover:bg-slate-700"
                  title="Zoom Out"
                >
                  <span className="material-symbols-outlined text-[16px]">remove</span>
                </button>
                <span className="font-mono text-[11px] w-12 text-center">
                  {Math.round(zoomLevel * 100)}%
                </span>
                <button
                  onClick={() => setZoomLevel((z) => Math.min(2.5, Math.round((z + 0.15) * 100) / 100))}
                  className="p-1 rounded hover:bg-slate-700"
                  title="Zoom In"
                >
                  <span className="material-symbols-outlined text-[16px]">add</span>
                </button>
                <button
                  onClick={() => setZoomLevel(1.0)}
                  className="px-2 py-0.5 text-[10px] bg-slate-700 hover:bg-slate-600 rounded font-semibold ml-1"
                >
                  Reset
                </button>
              </div>
            </div>

            {/* Document Interactive Viewport with Anti-Tamper & Security Controls */}
            <div
              ref={viewportRef}
              onContextMenu={(e) => {
                e.preventDefault();
                return false;
              }}
              className={`flex-1 overflow-auto p-4 flex items-center justify-center select-none ${
                isMarqueeMode ? 'cursor-crosshair' : 'cursor-default'
              }`}
            >
              {loading ? (
                <div className="flex flex-col items-center justify-center text-slate-400 gap-2">
                  <span className="material-symbols-outlined text-[32px] animate-spin text-blue-500">progress_activity</span>
                  <p className="text-[13px]">Rendering high-resolution document canvas...</p>
                </div>
              ) : error ? (
                <div className="p-4 bg-red-900/50 border border-red-700 text-red-200 rounded-xl text-center max-w-md">
                  <span className="material-symbols-outlined text-[28px] mb-1">error</span>
                  <p className="text-[13px] font-semibold">{error}</p>
                </div>
              ) : (
                <div
                  className="relative shadow-2xl bg-white rounded-sm transition-transform duration-100 ease-out inline-block overflow-hidden"
                  style={{
                    transform: `scale(${zoomLevel})`,
                    transformOrigin: 'top center',
                  }}
                  onMouseDown={handleMouseDown}
                  onMouseMove={handleMouseMove}
                  onMouseUp={handleMouseUp}
                  onTouchStart={handleMouseDown}
                  onTouchMove={handleMouseMove}
                  onTouchEnd={handleMouseUp}
                  onContextMenu={(e) => {
                    e.preventDefault();
                    return false;
                  }}
                >
                  {/* High-DPI Document Image */}
                  <img
                    ref={imgRef}
                    src={previewUrl}
                    alt={docInfo?.original_filename || 'Document Page'}
                    className="max-w-[760px] md:max-w-[840px] w-auto h-auto block select-none pointer-events-none"
                    draggable={false}
                    onContextMenu={(e) => {
                      e.preventDefault();
                      return false;
                    }}
                    onError={(e) => {
                      // Fallback to raw file URL if rendered page endpoint encounters unsupported format
                      e.target.src = api.getDocumentFileUrl(documentId);
                    }}
                  />

                  {/* Anti-Copy Security Watermark Overlay */}
                  <div
                    className="absolute inset-0 pointer-events-none select-none z-10 flex flex-col justify-around items-center overflow-hidden"
                    style={{
                      opacity: 0.13,
                      transform: 'rotate(-25deg) scale(1.15)',
                    }}
                  >
                    <div className="text-[14px] font-mono font-bold tracking-widest text-slate-900 uppercase">
                      CONFIDENTIAL · VERIDOC KYC · {officerName || 'OFFICER'} · AUTHORIZED REVIEW
                    </div>
                    <div className="text-[12px] font-mono font-bold tracking-wider text-slate-900 uppercase">
                      DO NOT COPY · ACCESS AUDITED · {new Date().toISOString().slice(0, 10)}
                    </div>
                    <div className="text-[14px] font-mono font-bold tracking-widest text-slate-900 uppercase">
                      CONFIDENTIAL · VERIDOC KYC · {officerName || 'OFFICER'} · AUTHORIZED REVIEW
                    </div>
                  </div>

                  {/* SVG Coordinate Bounding Box Overlay */}
                  <svg
                    ref={overlayRef}
                    viewBox="0 0 1000 1000"
                    preserveAspectRatio="none"
                    className="absolute inset-0 w-full h-full pointer-events-auto"
                  >
                    {/* 1. Extracted Attributes Bounding Boxes */}
                    {attributes.map((attr) => {
                      const bbox = normalizeBoundingBox(attr.bounding_box);
                      if (!bbox || (attr.page_number && attr.page_number !== currentPage)) return null;
                      const [ymin, xmin, ymax, xmax] = bbox;
                      const isHighlighted = activeHighlightId === attr.id;
                      const isCustom = attr.source_type === 'custom';

                      return (
                        <g
                          key={attr.id}
                          className="cursor-pointer transition-all duration-150"
                          onMouseEnter={() => setActiveHighlightId(attr.id)}
                          onMouseLeave={() => {
                            if (activeHighlightId === attr.id) setActiveHighlightId(null);
                          }}
                          onClick={() => setActiveHighlightId(attr.id)}
                        >
                          {/* Rectangle Box */}
                          <rect
                            x={xmin}
                            y={ymin}
                            width={Math.max(4, xmax - xmin)}
                            height={Math.max(4, ymax - ymin)}
                            rx={3}
                            fill={
                              isHighlighted
                                ? isCustom ? 'rgba(245, 158, 11, 0.35)' : 'rgba(37, 99, 235, 0.35)'
                                : isCustom ? 'rgba(245, 158, 11, 0.12)' : 'rgba(37, 99, 235, 0.10)'
                            }
                            stroke={
                              isHighlighted
                                ? isCustom ? '#D97706' : '#1D4ED8'
                                : isCustom ? '#F59E0B' : '#2563EB'
                            }
                            strokeWidth={isHighlighted ? 4 : 2}
                            strokeDasharray={isCustom ? '4 2' : 'none'}
                          />

                          {/* Floating Attribute Label Tag on Hover / Highlight */}
                          {isHighlighted && (
                            <g>
                              <rect
                                x={xmin}
                                y={Math.max(0, ymin - 22)}
                                width={Math.max(90, (attr.attribute_label || attr.attribute_key).length * 8 + 16)}
                                height={20}
                                rx={4}
                                fill={isCustom ? '#B45309' : '#1E40AF'}
                                filter="drop-shadow(0px 2px 4px rgba(0,0,0,0.4))"
                              />
                              <text
                                x={xmin + 8}
                                y={Math.max(0, ymin - 22) + 14}
                                fill="#FFFFFF"
                                fontSize="11"
                                fontWeight="bold"
                                fontFamily="sans-serif"
                              >
                                {attr.attribute_label || attr.attribute_key}
                              </text>
                            </g>
                          )}
                        </g>
                      );
                    })}

                    {/* 2. Live Marquee Selection Drag Rectangle */}
                    {dragRect && (
                      <rect
                        x={dragRect.x}
                        y={dragRect.y}
                        width={dragRect.width}
                        height={dragRect.height}
                        fill="rgba(245, 158, 11, 0.25)"
                        stroke="#F59E0B"
                        strokeWidth={2}
                        strokeDasharray="6 3"
                        rx={2}
                      />
                    )}
                  </svg>
                </div>
              )}
            </div>

            {/* Marquee Extraction Floating Spinner */}
            {marqueeExtracting && (
              <div className="absolute inset-0 bg-slate-950/40 backdrop-blur-xs flex items-center justify-center z-30">
                <div className="px-5 py-3 bg-slate-900 border border-amber-500/40 rounded-xl shadow-2xl flex items-center gap-3 text-white">
                  <span className="material-symbols-outlined text-[24px] text-amber-400 animate-spin">progress_activity</span>
                  <div className="text-[13px]">
                    <p className="font-bold">Extracting Selected Region...</p>
                    <p className="text-slate-400 text-[11px]">OCR & Spatial Token Alignment</p>
                  </div>
                </div>
              </div>
            )}
          </div>

          {/* --------------------------------------------------------------- */}
          {/* RIGHT: Attribute Inspector & Entity Explorer */}
          {/* --------------------------------------------------------------- */}
          <div className="w-full lg:w-[460px] xl:w-[500px] flex flex-col bg-white overflow-hidden shrink-0 border-l border-slate-200">
            
            {/* Header & Search */}
            <div className="p-4 border-b border-slate-200 space-y-3 bg-slate-50/50">
              <div className="flex items-center justify-between">
                <div>
                  <h3 className="font-bold text-[14px] text-slate-900">Extracted Attributes</h3>
                  <p className="text-[11px] text-slate-500">Universal Schema & Dynamic Entity Inspector</p>
                </div>
                <span className="px-2 py-0.5 rounded-full text-[11px] font-bold bg-blue-50 text-blue-700 border border-blue-200">
                  {filteredAttributes.length} item(s)
                </span>
              </div>

              {/* Search Bar */}
              <div className="relative">
                <span className="material-symbols-outlined absolute left-2.5 top-2.5 text-[16px] text-slate-400">
                  search
                </span>
                <input
                  type="text"
                  placeholder="Filter attributes by key or value..."
                  value={searchTerm}
                  onChange={(e) => setSearchTerm(e.target.value)}
                  className="w-full pl-8 pr-3 py-1.5 bg-white border border-slate-200 rounded-lg text-[12px] text-slate-900 placeholder:text-slate-400 focus:outline-none focus:border-blue-500"
                />
              </div>

              {/* Source Filter Tabs */}
              <div className="flex items-center gap-1.5 text-[11px]">
                <button
                  onClick={() => setFilterSource('all')}
                  className={`px-2.5 py-1 rounded-md font-semibold transition-colors ${
                    filterSource === 'all'
                      ? 'bg-slate-900 text-white shadow-xs'
                      : 'bg-slate-200/60 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  All ({attributes.length})
                </button>
                <button
                  onClick={() => setFilterSource('standard')}
                  className={`px-2.5 py-1 rounded-md font-semibold transition-colors ${
                    filterSource === 'standard'
                      ? 'bg-blue-600 text-white shadow-xs'
                      : 'bg-slate-200/60 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  Predefined
                </button>
                <button
                  onClick={() => setFilterSource('discovered')}
                  className={`px-2.5 py-1 rounded-md font-semibold transition-colors ${
                    filterSource === 'discovered'
                      ? 'bg-purple-600 text-white shadow-xs'
                      : 'bg-slate-200/60 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  AI Discovered
                </button>
                <button
                  onClick={() => setFilterSource('custom')}
                  className={`px-2.5 py-1 rounded-md font-semibold transition-colors ${
                    filterSource === 'custom'
                      ? 'bg-amber-600 text-white shadow-xs'
                      : 'bg-slate-200/60 text-slate-600 hover:bg-slate-200'
                  }`}
                >
                  Custom
                </button>
              </div>
            </div>

            {/* Attributes List */}
            <div className="flex-1 overflow-y-auto p-4 space-y-2.5">
              {filteredAttributes.length === 0 ? (
                <div className="text-center py-12 text-slate-400 space-y-2">
                  <span className="material-symbols-outlined text-[36px] text-slate-300">inventory_2</span>
                  <p className="text-[13px] font-medium text-slate-600">No matching attributes found</p>
                  <p className="text-[11px] text-slate-400">Use the Marquee Tool to extract custom fields from the document image.</p>
                </div>
              ) : (
                filteredAttributes.map((attr) => {
                  const isHighlighted = activeHighlightId === attr.id;
                  const isCustom = attr.source_type === 'custom';
                  const isDiscovered = attr.source_type === 'discovered';
                  const bbox = normalizeBoundingBox(attr.bounding_box);
                  const hasBbox = !!bbox;

                  return (
                    <div
                      key={attr.id}
                      onMouseEnter={() => {
                        setActiveHighlightId(attr.id);
                        if (attr.page_number && attr.page_number !== currentPage) {
                          setCurrentPage(attr.page_number);
                        }
                      }}
                      onMouseLeave={() => {
                        if (activeHighlightId === attr.id) setActiveHighlightId(null);
                      }}
                      onClick={() => {
                        setActiveHighlightId(attr.id);
                        if (attr.page_number && attr.page_number !== currentPage) {
                          setCurrentPage(attr.page_number);
                        }
                      }}
                      className={`p-3 rounded-xl border transition-all cursor-pointer ${
                        isHighlighted
                          ? isCustom
                            ? 'bg-amber-50/80 border-amber-400 shadow-sm ring-1 ring-amber-400'
                            : 'bg-blue-50/80 border-blue-400 shadow-sm ring-1 ring-blue-400'
                          : 'bg-white border-slate-200 hover:border-slate-300 hover:bg-slate-50/60'
                      }`}
                    >
                      {/* Top Row: Label & Source Badge */}
                      <div className="flex items-center justify-between gap-1 mb-1">
                        <div className="flex items-center gap-1.5 min-w-0">
                          <span className="font-bold text-[13px] text-slate-900 truncate">
                            {attr.attribute_label || attr.attribute_key}
                          </span>
                          <span className="text-[10px] font-mono text-slate-400 truncate">
                            ({attr.attribute_key})
                          </span>
                        </div>

                        <div className="flex items-center gap-1 shrink-0">
                          {/* Source Badge */}
                          <span
                            className={`px-1.5 py-0.2 text-[9px] font-bold uppercase rounded font-mono ${
                              isCustom
                                ? 'bg-amber-100 text-amber-800 border border-amber-200'
                                : isDiscovered
                                ? 'bg-purple-100 text-purple-800 border border-purple-200'
                                : 'bg-slate-100 text-slate-700 border border-slate-200'
                            }`}
                          >
                            {isCustom ? 'Custom' : isDiscovered ? 'Discovered' : 'Standard'}
                          </span>

                          {/* Data Type Pill */}
                          <span className="px-1.5 py-0.2 text-[9px] font-bold uppercase rounded bg-slate-100 text-slate-600 font-mono">
                            {attr.data_type || 'str'}
                          </span>
                        </div>
                      </div>

                      {/* Value Display */}
                      <div className="p-2 bg-slate-50 rounded-lg border border-slate-200/80 text-[12px] font-mono font-medium text-slate-900 break-all select-all flex items-center justify-between gap-2">
                        <span>{String(attr.normalized_value || attr.raw_value || 'None')}</span>
                        {hasBbox && (
                          <span
                            className="material-symbols-outlined text-[14px] text-blue-600 shrink-0"
                            title="Mapped on document canvas"
                          >
                            pin_drop
                          </span>
                        )}
                      </div>

                      {/* Bottom Row: Metadata & Actions */}
                      <div className="flex items-center justify-between mt-2 text-[11px] text-slate-500">
                        <div className="flex items-center gap-2">
                          <span>Conf: {Math.round((attr.confidence || 1.0) * 100)}%</span>
                          {attr.page_number && (
                            <span>• Pg {attr.page_number}</span>
                          )}
                          {hasBbox && bbox && (
                            <span className="font-mono text-[10px] text-slate-400">
                              [{bbox[0]}, {bbox[1]}]
                            </span>
                          )}
                        </div>

                        {/* Custom Attribute Deletion */}
                        {isCustom && (
                          <button
                            onClick={(e) => handleDeleteAttribute(attr.id, e)}
                            className="p-1 rounded text-red-500 hover:text-red-700 hover:bg-red-50"
                            title="Delete custom attribute"
                          >
                            <span className="material-symbols-outlined text-[14px]">delete</span>
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            {/* Footer Summary */}
            <div className="p-3 bg-slate-50 border-t border-slate-200 text-[11px] text-slate-500 flex items-center justify-between">
              <span>{attributes.filter(a => a.source_type === 'custom').length} Custom Attribute(s)</span>
              <span>Coordinates: Normalized [0-1000]</span>
            </div>
          </div>
        </div>

        {/* ================================================================= */}
        {/* Modal: Add / Edit Custom Attribute (Marquee Result or Manual) */}
        {/* ================================================================= */}
        {customAttrModal.isOpen && (
          <div className="fixed inset-0 z-60 bg-black/50 flex items-center justify-center p-4">
            <div className="bg-white rounded-2xl shadow-2xl max-w-md w-full p-6 space-y-4 border border-slate-200">
              <div className="flex items-center justify-between pb-2 border-b border-slate-200">
                <div className="flex items-center gap-2">
                  <div className="p-1.5 bg-amber-100 text-amber-700 rounded-lg">
                    <span className="material-symbols-outlined text-[18px]">post_add</span>
                  </div>
                  <div>
                    <h3 className="font-bold text-[15px] text-slate-900">Add Custom Attribute</h3>
                    <p className="text-[11px] text-slate-500">Persist custom attribute into document schema</p>
                  </div>
                </div>
                <button
                  onClick={() => setCustomAttrModal(prev => ({ ...prev, isOpen: false }))}
                  className="p-1 rounded hover:bg-slate-100 text-slate-400"
                >
                  <span className="material-symbols-outlined text-[20px]">close</span>
                </button>
              </div>

              <div className="space-y-3 text-[12px]">
                <div>
                  <label className="block text-[11px] font-bold text-slate-700 mb-1">
                    Attribute Key (Identifier)
                  </label>
                  <input
                    type="text"
                    value={customAttrModal.key}
                    onChange={(e) => setCustomAttrModal(prev => ({ ...prev, key: e.target.value }))}
                    placeholder="e.g. tax_id, contract_date, total_gross"
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg font-mono text-slate-900 focus:outline-none focus:border-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-slate-700 mb-1">
                    Display Label
                  </label>
                  <input
                    type="text"
                    value={customAttrModal.label}
                    onChange={(e) => setCustomAttrModal(prev => ({ ...prev, label: e.target.value }))}
                    placeholder="e.g. Tax Identification Number"
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg text-slate-900 focus:outline-none focus:border-blue-500"
                  />
                </div>

                <div>
                  <label className="block text-[11px] font-bold text-slate-700 mb-1">
                    Extracted Value
                  </label>
                  <textarea
                    rows={2}
                    value={customAttrModal.value}
                    onChange={(e) => setCustomAttrModal(prev => ({ ...prev, value: e.target.value }))}
                    placeholder="Text snippet extracted from document"
                    className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg font-mono text-slate-900 focus:outline-none focus:border-blue-500"
                  />
                </div>

                <div className="grid grid-cols-2 gap-3">
                  <div>
                    <label className="block text-[11px] font-bold text-slate-700 mb-1">
                      Data Type
                    </label>
                    <select
                      value={customAttrModal.dataType}
                      onChange={(e) => setCustomAttrModal(prev => ({ ...prev, dataType: e.target.value }))}
                      className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg text-slate-900 focus:outline-none focus:border-blue-500"
                    >
                      <option value="string">String / Text</option>
                      <option value="currency">Currency / Amount</option>
                      <option value="number">Number</option>
                      <option value="date">Date</option>
                      <option value="boolean">Boolean</option>
                    </select>
                  </div>

                  <div>
                    <label className="block text-[11px] font-bold text-slate-700 mb-1">
                      Target Page
                    </label>
                    <input
                      type="number"
                      min={1}
                      max={pagesInfo.page_count || 1}
                      value={customAttrModal.page}
                      onChange={(e) => setCustomAttrModal(prev => ({ ...prev, page: parseInt(e.target.value) || 1 }))}
                      className="w-full px-3 py-2 bg-slate-50 border border-slate-300 rounded-lg text-slate-900 font-mono focus:outline-none focus:border-blue-500"
                    />
                  </div>
                </div>

                {customAttrModal.bbox && (
                  <div className="p-2.5 bg-amber-50 rounded-lg border border-amber-200 text-[11px] text-amber-900">
                    <span className="font-bold">Bounding Box: </span>
                    <span className="font-mono">[{customAttrModal.bbox.join(', ')}]</span>
                  </div>
                )}
              </div>

              <div className="flex items-center justify-end gap-2 pt-3 border-t border-slate-200">
                <button
                  type="button"
                  onClick={() => setCustomAttrModal(prev => ({ ...prev, isOpen: false }))}
                  className="px-4 py-2 bg-slate-100 hover:bg-slate-200 text-slate-700 rounded-lg font-semibold text-[12px]"
                >
                  Cancel
                </button>
                <button
                  type="button"
                  disabled={customAttrModal.saving || !customAttrModal.key.trim()}
                  onClick={handleSaveCustomAttribute}
                  className="px-4 py-2 bg-blue-600 hover:bg-blue-700 text-white rounded-lg font-semibold text-[12px] flex items-center gap-1.5 shadow-xs disabled:opacity-50"
                >
                  {customAttrModal.saving ? 'Saving...' : 'Save Attribute'}
                </button>
              </div>
            </div>
          </div>
        )}

      </div>
    </div>
  );
}

export default function VisualDocumentWorkspace(props) {
  return (
    <VisualWorkspaceErrorBoundary onClose={props.onClose}>
      <VisualDocumentWorkspaceInner {...props} />
    </VisualWorkspaceErrorBoundary>
  );
}
