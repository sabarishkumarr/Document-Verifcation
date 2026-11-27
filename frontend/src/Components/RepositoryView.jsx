import React, { useState, useEffect, useMemo } from 'react';
import { api } from '../api';
import DocumentSchemaWorkspace from './DocumentSchemaWorkspace';

export default function RepositoryView({ onNavigateToUpload }) {
  const [types, setTypes] = useState([]);
  const [stats, setStats] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  // Filters & Sorting
  const [selectedCategory, setSelectedCategory] = useState('all');
  const [selectedOrigin, setSelectedOrigin] = useState('all');
  const [searchQuery, setSearchQuery] = useState('');
  const [sortField, setSortField] = useState('display_name'); // 'display_name' | 'documents' | 'category' | 'schema'
  const [sortDirection, setSortDirection] = useState('asc');

  // Interactive Schema Workspace State
  const [workspaceTypeKey, setWorkspaceTypeKey] = useState(null);

  // New Type Wizard Modal State
  const [isWizardOpen, setIsWizardOpen] = useState(false);
  const [wizardStep, setWizardStep] = useState(1);
  const [wizardMode, setWizardMode] = useState('manual');
  const [wizardData, setWizardData] = useState({
    type_key: '',
    display_name: '',
    category: 'general',
    description: '',
    source_origin: 'employee_created',
    attributes: [
      {
        attribute_key: 'document_id',
        display_label: 'Document ID / Number',
        data_type: 'string',
        required: true,
        validation_rule: '',
        extraction_guidance: '',
        confidence_threshold: 0.8,
      },
    ],
  });
  const [sampleFiles, setSampleFiles] = useState([]);
  const [discovering, setDiscovering] = useState(false);
  const [wizardError, setWizardError] = useState(null);
  const [publishing, setPublishing] = useState(false);

  // Load Repository Types & Stats
  const loadRepositoryData = async () => {
    try {
      setLoading(true);
      setError(null);
      const [statsRes, typesRes] = await Promise.all([
        api.getRepositoryStats(),
        api.getRepositoryTypes({
          category: selectedCategory,
          source_origin: selectedOrigin,
          search: searchQuery,
        }),
      ]);
      setStats(statsRes.data);
      setTypes(typesRes.data.types || []);
    } catch (err) {
      console.error('Failed to load repository:', err);
      setError(err.message || 'Failed to load repository catalog');
    } finally {
      setLoading(false);
    }
  };

  useEffect(() => {
    loadRepositoryData();
  }, [selectedCategory, selectedOrigin]);

  const handleSearch = (e) => {
    e.preventDefault();
    loadRepositoryData();
  };

  // Sample file upload & attribute discovery
  const handleSampleFilesSelected = (e) => {
    if (e.target.files) {
      setSampleFiles(Array.from(e.target.files));
    }
  };

  const handleDiscoverAttributes = async () => {
    if (sampleFiles.length === 0) {
      setWizardError('Please select at least one sample document to analyze.');
      return;
    }
    try {
      setDiscovering(true);
      setWizardError(null);
      const formData = new FormData();
      sampleFiles.forEach((f) => formData.append('files', f));

      const res = await api.discoverRepositoryAttributes(formData);
      const disc = res.data || {};

      setWizardData((prev) => ({
        ...prev,
        type_key: disc.predicted_type && disc.predicted_type !== 'unknown' ? disc.predicted_type : prev.type_key,
        display_name: disc.display_name || prev.display_name,
        category: disc.category || prev.category,
        description: `Discovered from specimen: ${disc.sample_filenames?.join(', ')}`,
        source_origin: 'ai_discovered',
        attributes: disc.discovered_attributes?.length
          ? disc.discovered_attributes.map((a) => ({
              attribute_key: a.attribute_key,
              display_label: a.display_label || a.attribute_label,
              data_type: a.data_type || 'string',
              required: false,
              validation_rule: a.regex_pattern || '',
              extraction_guidance: a.anchor_phrase || '',
              confidence_threshold: 0.75,
            }))
          : prev.attributes,
      }));
      setWizardStep(3);
    } catch (err) {
      setWizardError(err.message || 'Sample discovery failed');
    } finally {
      setDiscovering(false);
    }
  };

  const handleCreateDocumentType = async () => {
    if (!wizardData.display_name.trim() || !wizardData.type_key.trim()) {
      setWizardError('Display Name and Slug Key are required.');
      return;
    }
    try {
      setPublishing(true);
      setWizardError(null);
      const res = await api.createDocumentType({
        ...wizardData,
        attribute_definitions: wizardData.attributes,
      });
      setIsWizardOpen(false);
      setWizardStep(1);
      setSampleFiles([]);
      loadRepositoryData();
      setWorkspaceTypeKey(res.data.type_key);
    } catch (err) {
      setWizardError(err.message || 'Registration failed');
    } finally {
      setPublishing(false);
    }
  };

  const categories = [
    { id: 'all', label: 'All' },
    { id: 'identity', label: 'Identity / KYC' },
    { id: 'financial', label: 'Financial' },
    { id: 'billing', label: 'Billing' },
    { id: 'tax', label: 'Tax' },
    { id: 'utility', label: 'Utility' },
    { id: 'general', label: 'General' },
  ];

  const handleToggleSort = (field) => {
    if (sortField === field) {
      setSortDirection((prev) => (prev === 'asc' ? 'desc' : 'asc'));
    } else {
      setSortField(field);
      setSortDirection('asc');
    }
  };

  const sortedTypes = useMemo(() => {
    let list = [...types];
    if (searchQuery.trim()) {
      const q = searchQuery.toLowerCase().trim();
      list = list.filter(
        (t) =>
          (t.display_name || '').toLowerCase().includes(q) ||
          (t.type_key || '').toLowerCase().includes(q) ||
          (t.category || '').toLowerCase().includes(q) ||
          (t.description || '').toLowerCase().includes(q)
      );
    }
    list.sort((a, b) => {
      let valA = a[sortField];
      let valB = b[sortField];

      if (sortField === 'display_name') {
        valA = (a.display_name || '').toLowerCase();
        valB = (b.display_name || '').toLowerCase();
      } else if (sortField === 'documents') {
        valA = a.document_count || 0;
        valB = b.document_count || 0;
      } else if (sortField === 'category') {
        valA = (a.category || '').toLowerCase();
        valB = (b.category || '').toLowerCase();
      } else if (sortField === 'schema') {
        valA = a.active_schema_version || a.active_version || 1;
        valB = b.active_schema_version || b.active_version || 1;
      }

      if (valA < valB) return sortDirection === 'asc' ? -1 : 1;
      if (valA > valB) return sortDirection === 'asc' ? 1 : -1;
      return 0;
    });
    return list;
  }, [types, sortField, sortDirection]);

  const totalTypesCount = stats?.total_types || types.length || 12;
  const totalDocsCount = stats?.total_documents_processed || 134;

  const getOriginLabel = (type) => {
    const orig = type.source_origin;
    if (orig === 'system_standard' || type.is_system || orig === 'system') return 'System Standard';
    if (orig === 'ai_discovered') return 'AI Discovered';
    return 'Employee Created';
  };

  const getOriginColor = (type) => {
    const orig = type.source_origin;
    if (orig === 'system_standard' || type.is_system || orig === 'system') return 'text-[#2563EB] bg-blue-50';
    if (orig === 'ai_discovered') return 'text-purple-700 bg-purple-50';
    return 'text-emerald-700 bg-emerald-50';
  };

  const getAttributeCount = (type) => {
    if (type.attribute_count && type.attribute_count > 0) return type.attribute_count;
    if (type.attributes && type.attributes.length > 0) return type.attributes.length;
    // Standard baseline KYC attributes count
    const key = (type.type_key || '').toLowerCase();
    if (key === 'pan' || key === 'aadhaar') return 5;
    if (key === 'passport') return 5;
    if (key === 'driving_licence' || key === 'voter_id') return 4;
    if (key === 'salary_slip') return 6;
    return 4;
  };

  return (
    <div className="max-w-[1520px] mx-auto px-6 lg:px-8 py-8 space-y-6">
      
      {/* 1. Repository Header */}
      <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-4 pb-4 border-b border-[#E2E8F0]">
        <div>
          <h1 className="text-[20px] font-bold text-[#0F172A] tracking-tight">
            Document Repository
          </h1>
          <p className="text-[13px] text-[#64748B] mt-0.5">
            {totalTypesCount} document types · {totalDocsCount} documents
          </p>
        </div>

        {/* Primary Action Button */}
        <div className="flex items-center gap-3">
          <button
            onClick={() => {
              setWizardStep(1);
              setWizardError(null);
              setIsWizardOpen(true);
            }}
            className="inline-flex items-center gap-2 bg-[#2563EB] hover:bg-[#1D4ED8] text-white px-4 py-2 rounded-md text-[13px] font-medium transition-colors shadow-xs"
          >
            <span>+</span>
            Register Document Type
          </button>
        </div>
      </div>

      {/* Alert Notices */}
      {error && (
        <div className="p-3 bg-red-50 border border-red-200 rounded-md text-red-700 text-[13px] flex items-center justify-between">
          <span>{error}</span>
          <button onClick={() => setError(null)} className="text-red-500 hover:text-red-800">✕</button>
        </div>
      )}

      {/* 2. Compact Filter Row */}
      <div className="flex flex-col lg:flex-row lg:items-center justify-between gap-3 bg-white p-2.5 rounded-lg border border-[#E2E8F0]">
        
        {/* Category Filter Buttons */}
        <div className="flex items-center gap-1 overflow-x-auto pb-1 lg:pb-0 scrollbar-none">
          {categories.map((cat) => (
            <button
              key={cat.id}
              onClick={() => setSelectedCategory(cat.id)}
              className={`px-3 py-1 rounded-md text-[12px] font-medium whitespace-nowrap transition-colors ${
                selectedCategory === cat.id
                  ? 'bg-[#0F172A] text-white'
                  : 'text-[#64748B] hover:text-[#0F172A] hover:bg-slate-100'
              }`}
            >
              {cat.label}
            </button>
          ))}
        </div>

        {/* Search & Origin Filter */}
        <div className="flex items-center gap-2 shrink-0">
          <form onSubmit={handleSearch} className="relative">
            <input
              type="text"
              placeholder="Search document types..."
              value={searchQuery}
              onChange={(e) => setSearchQuery(e.target.value)}
              className="w-48 sm:w-56 px-2.5 py-1.5 pl-8 text-[12px] rounded-md border border-[#CBD5E1] bg-white text-[#0F172A] focus:outline-none focus:ring-1 focus:ring-[#2563EB]"
            />
            <span className="material-symbols-outlined text-[16px] text-slate-400 absolute left-2 top-2">
              search
            </span>
          </form>

          <select
            value={selectedOrigin}
            onChange={(e) => setSelectedOrigin(e.target.value)}
            className="px-2.5 py-1.5 text-[12px] rounded-md border border-[#CBD5E1] bg-white text-[#334155] focus:outline-none"
          >
            <option value="all">All Origins</option>
            <option value="system_standard">System Standard</option>
            <option value="ai_discovered">AI Discovered</option>
            <option value="employee_created">Employee Created</option>
          </select>
        </div>
      </div>

      {/* 3. Document List / Compact Table Layout */}
      {loading ? (
        <div className="py-20 text-center text-[#64748B] bg-white rounded-lg border border-[#E2E8F0]">
          <div className="inline-block animate-spin w-6 h-6 border-2 border-[#2563EB] border-t-transparent rounded-full mb-2" />
          <p className="text-[13px] font-medium">Loading document catalog...</p>
        </div>
      ) : sortedTypes.length > 0 ? (
        <div className="bg-white rounded-lg border border-[#E2E8F0] overflow-hidden">
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="bg-[#F8FAFC] border-b border-[#E2E8F0] text-[11px] font-semibold text-[#64748B] uppercase tracking-wider select-none">
                  <th
                    onClick={() => handleToggleSort('display_name')}
                    className="py-3 px-4 cursor-pointer hover:text-[#0F172A]"
                  >
                    <div className="flex items-center gap-1">
                      <span>Document Type</span>
                      {sortField === 'display_name' && (
                        <span>{sortDirection === 'asc' ? '↑' : '↓'}</span>
                      )}
                    </div>
                  </th>
                  <th
                    onClick={() => handleToggleSort('category')}
                    className="py-3 px-4 cursor-pointer hover:text-[#0F172A]"
                  >
                    <div className="flex items-center gap-1">
                      <span>Category</span>
                      {sortField === 'category' && (
                        <span>{sortDirection === 'asc' ? '↑' : '↓'}</span>
                      )}
                    </div>
                  </th>
                  <th className="py-3 px-4">Origin</th>
                  <th
                    onClick={() => handleToggleSort('schema')}
                    className="py-3 px-4 cursor-pointer hover:text-[#0F172A]"
                  >
                    <div className="flex items-center gap-1">
                      <span>Schema</span>
                      {sortField === 'schema' && (
                        <span>{sortDirection === 'asc' ? '↑' : '↓'}</span>
                      )}
                    </div>
                  </th>
                  <th className="py-3 px-4 text-center">Attributes</th>
                  <th
                    onClick={() => handleToggleSort('documents')}
                    className="py-3 px-4 text-right cursor-pointer hover:text-[#0F172A]"
                  >
                    <div className="flex items-center justify-end gap-1">
                      <span>Documents</span>
                      {sortField === 'documents' && (
                        <span>{sortDirection === 'asc' ? '↑' : '↓'}</span>
                      )}
                    </div>
                  </th>
                  <th className="py-3 px-4 text-center">Specimen</th>
                  <th className="py-3 px-4 text-right">Action</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-[#E2E8F0] text-[13px]">
                {sortedTypes.map((type) => {
                  const version = type.active_schema_version || type.active_version || 1;
                  const docCount = type.document_count || 0;
                  const attrCount = getAttributeCount(type);
                  const originLabel = getOriginLabel(type);
                  const originColor = getOriginColor(type);
                  const hasSpecimen = type.has_specimen || docCount > 0;

                  return (
                    <tr
                      key={type.id || type.type_key}
                      onClick={() => setWorkspaceTypeKey(type.type_key || type.id)}
                      className="hover:bg-[#F8FAFC] transition-colors cursor-pointer group"
                    >
                      {/* Document Type Name & Key */}
                      <td className="py-3 px-4">
                        <div className="font-semibold text-[#0F172A] group-hover:text-[#2563EB] transition-colors">
                          {type.display_name}
                        </div>
                        <div className="font-mono text-[11px] text-[#64748B]">
                          {type.type_key}
                        </div>
                      </td>

                      {/* Category */}
                      <td className="py-3 px-4">
                        <span className="inline-flex px-2 py-0.5 rounded text-[11px] font-medium bg-slate-100 text-[#475569] capitalize">
                          {type.category?.replace(/_/g, ' ') || 'General'}
                        </span>
                      </td>

                      {/* Origin */}
                      <td className="py-3 px-4">
                        <span className={`inline-flex px-2 py-0.5 rounded text-[11px] font-medium ${originColor}`}>
                          {originLabel}
                        </span>
                      </td>

                      {/* Schema Version */}
                      <td className="py-3 px-4">
                        <span className="font-mono text-[12px] font-semibold text-[#334155]">
                          v{version}
                        </span>
                      </td>

                      {/* Attribute Count */}
                      <td className="py-3 px-4 text-center">
                        <span className="inline-block text-[#334155] font-medium">
                          {attrCount}
                        </span>
                      </td>

                      {/* Associated Documents Count */}
                      <td className="py-3 px-4 text-right">
                        <span className="font-mono font-medium text-[#0F172A]">
                          {docCount}
                        </span>
                      </td>

                      {/* Specimen Status */}
                      <td className="py-3 px-4 text-center">
                        {hasSpecimen ? (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-emerald-50 text-emerald-700 border border-emerald-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-emerald-500"></span>
                            Available
                          </span>
                        ) : (
                          <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded-full text-[11px] font-semibold bg-slate-100 text-slate-500 border border-slate-200">
                            <span className="w-1.5 h-1.5 rounded-full bg-slate-400"></span>
                            Missing
                          </span>
                        )}
                      </td>

                      {/* Action Button */}
                      <td className="py-3 px-4 text-right">
                        <button
                          type="button"
                          onClick={(e) => {
                            e.stopPropagation();
                            setWorkspaceTypeKey(type.type_key || type.id);
                          }}
                          className="px-3 py-1 bg-blue-50 hover:bg-blue-100 text-[#2563EB] rounded text-[12px] font-semibold transition-colors"
                        >
                          Inspect
                        </button>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>
      ) : (
        <div className="py-16 text-center text-[#64748B] bg-white rounded-lg border border-[#E2E8F0] p-6">
          <p className="font-medium text-[13px] text-[#0F172A]">No document types match your criteria</p>
          <p className="text-[12px] text-[#64748B] mt-0.5">Try clearing filters or search query.</p>
        </div>
      )}

      {/* =================================================================== */}
      {/* Interactive Two-Panel Document Schema Workspace                     */}
      {/* =================================================================== */}
      {workspaceTypeKey && (
        <DocumentSchemaWorkspace
          typeKeyOrId={workspaceTypeKey}
          onClose={() => setWorkspaceTypeKey(null)}
          onSchemaUpdated={loadRepositoryData}
        />
      )}

      {/* =================================================================== */}
      {/* Registration Wizard Modal                                           */}
      {/* =================================================================== */}
      {isWizardOpen && (
        <div className="fixed inset-0 z-50 bg-[#0F172A]/50 flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl max-w-lg w-full p-5 border border-[#E2E8F0] space-y-4">
            <div className="flex items-center justify-between pb-3 border-b border-[#E2E8F0]">
              <div>
                <h3 className="font-bold text-[15px] text-[#0F172A]">
                  Register New Document Type
                </h3>
                <p className="text-[12px] text-[#64748B]">
                  Step {wizardStep} of 3
                </p>
              </div>
              <button
                onClick={() => setIsWizardOpen(false)}
                className="text-[#94A3B8] hover:text-[#0F172A] text-[16px]"
              >
                ✕
              </button>
            </div>

            {wizardError && (
              <div className="p-2.5 bg-red-50 border border-red-200 rounded-md text-red-700 text-[12px]">
                {wizardError}
              </div>
            )}

            {/* Step 1: Metadata */}
            {wizardStep === 1 && (
              <div className="space-y-3 text-[13px]">
                <div>
                  <label className="block font-medium text-[#334155] mb-1 text-[12px]">
                    Document Type Display Name *
                  </label>
                  <input
                    type="text"
                    value={wizardData.display_name}
                    onChange={(e) => {
                      const name = e.target.value;
                      const slug = name.toLowerCase().replace(/[^a-z0-9_]/g, '_').replace(/^_+|_+$/g, '');
                      setWizardData((prev) => ({
                        ...prev,
                        display_name: name,
                        type_key: prev.type_key ? prev.type_key : slug,
                      }));
                    }}
                    placeholder="e.g. GST Registration Certificate"
                    className="w-full px-3 py-1.5 rounded-md border border-[#CBD5E1] text-[13px] focus:outline-none focus:ring-1 focus:ring-[#2563EB]"
                  />
                </div>

                <div>
                  <label className="block font-medium text-[#334155] mb-1 text-[12px]">
                    Slug Key *
                  </label>
                  <input
                    type="text"
                    value={wizardData.type_key}
                    onChange={(e) => setWizardData({ ...wizardData, type_key: e.target.value })}
                    placeholder="e.g. gst_registration_cert"
                    className="w-full px-3 py-1.5 rounded-md border border-[#CBD5E1] font-mono text-[12px] focus:outline-none focus:ring-1 focus:ring-[#2563EB]"
                  />
                </div>

                <div>
                  <label className="block font-medium text-[#334155] mb-1 text-[12px]">Category</label>
                  <select
                    value={wizardData.category}
                    onChange={(e) => setWizardData({ ...wizardData, category: e.target.value })}
                    className="w-full px-3 py-1.5 rounded-md border border-[#CBD5E1] text-[13px] bg-white"
                  >
                    <option value="identity">Identity / KYC</option>
                    <option value="financial">Financial</option>
                    <option value="billing">Billing</option>
                    <option value="tax">Tax</option>
                    <option value="utility">Utility</option>
                    <option value="general">General</option>
                  </select>
                </div>

                <div>
                  <label className="block font-medium text-[#334155] mb-1 text-[12px]">Description</label>
                  <textarea
                    rows={2}
                    value={wizardData.description}
                    onChange={(e) => setWizardData({ ...wizardData, description: e.target.value })}
                    placeholder="Brief description of the document purpose..."
                    className="w-full px-3 py-1.5 rounded-md border border-[#CBD5E1] text-[13px]"
                  />
                </div>

                <div className="flex justify-end gap-2 pt-3 border-t border-[#E2E8F0]">
                  <button
                    onClick={() => setIsWizardOpen(false)}
                    className="px-3 py-1.5 rounded-md border border-[#CBD5E1] text-[12px] font-medium text-[#64748B] hover:bg-slate-50"
                  >
                    Cancel
                  </button>
                  <button
                    onClick={() => {
                      if (!wizardData.display_name.trim() || !wizardData.type_key.trim()) {
                        setWizardError('Display Name and Slug Key are required.');
                        return;
                      }
                      setWizardError(null);
                      setWizardStep(2);
                    }}
                    className="px-4 py-1.5 rounded-md bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-[12px] font-medium"
                  >
                    Continue →
                  </button>
                </div>
              </div>
            )}

            {/* Step 2: Attribute Setup Mode */}
            {wizardStep === 2 && (
              <div className="space-y-3 text-[13px]">
                <div className="grid grid-cols-2 gap-3">
                  <div
                    onClick={() => setWizardMode('sample_ai')}
                    className={`p-3 rounded-lg border cursor-pointer transition-all ${
                      wizardMode === 'sample_ai'
                        ? 'border-[#2563EB] bg-[#EFF6FF]'
                        : 'border-[#E2E8F0] hover:bg-slate-50'
                    }`}
                  >
                    <div className="font-semibold text-[#0F172A] text-[12px]">Upload Sample Specimen</div>
                    <div className="text-[11px] text-[#64748B] mt-0.5">
                      AI discovers fields and spatial regions from sample.
                    </div>
                  </div>

                  <div
                    onClick={() => setWizardMode('manual')}
                    className={`p-3 rounded-lg border cursor-pointer transition-all ${
                      wizardMode === 'manual'
                        ? 'border-[#2563EB] bg-[#EFF6FF]'
                        : 'border-[#E2E8F0] hover:bg-slate-50'
                    }`}
                  >
                    <div className="font-semibold text-[#0F172A] text-[12px]">Standard Attributes</div>
                    <div className="text-[11px] text-[#64748B] mt-0.5">
                      Initialize standard fields and edit in workspace.
                    </div>
                  </div>
                </div>

                {wizardMode === 'sample_ai' ? (
                  <div className="space-y-2.5 p-3 bg-slate-50 border border-[#E2E8F0] rounded-lg">
                    <label className="block font-medium text-[#334155] text-[11px]">
                      Select Sample Document(s) (PDF, JPG, PNG)
                    </label>
                    <input
                      type="file"
                      accept=".pdf,.png,.jpg,.jpeg"
                      multiple
                      onChange={handleSampleFilesSelected}
                      className="w-full text-[12px]"
                    />
                    <button
                      onClick={handleDiscoverAttributes}
                      disabled={discovering || sampleFiles.length === 0}
                      className="w-full py-1.5 bg-[#2563EB] hover:bg-[#1D4ED8] text-white rounded-md text-[12px] font-medium transition-colors disabled:opacity-50"
                    >
                      {discovering ? 'Analyzing Specimen Document...' : 'Discover Attributes with AI'}
                    </button>
                  </div>
                ) : (
                  <div className="p-3 bg-slate-50 border border-[#E2E8F0] rounded-lg text-[12px] text-[#64748B]">
                    Initial Schema v1 will be generated with standard document fields. You can immediately configure spatial regions in the interactive workspace.
                  </div>
                )}

                <div className="flex justify-between pt-3 border-t border-[#E2E8F0]">
                  <button
                    onClick={() => setWizardStep(1)}
                    className="px-3 py-1.5 rounded-md border border-[#CBD5E1] text-[12px] font-medium text-[#64748B]"
                  >
                    ← Back
                  </button>
                  <button
                    onClick={() => setWizardStep(3)}
                    className="px-4 py-1.5 rounded-md bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-[12px] font-medium"
                  >
                    Review & Publish →
                  </button>
                </div>
              </div>
            )}

            {/* Step 3: Review & Publish */}
            {wizardStep === 3 && (
              <div className="space-y-3 text-[13px]">
                <div className="p-3 bg-slate-50 rounded-md border border-[#E2E8F0] space-y-1 text-[12px]">
                  <div><strong className="text-[#0F172A]">Type Name:</strong> {wizardData.display_name}</div>
                  <div><strong className="text-[#0F172A]">Slug Key:</strong> <code className="font-mono text-[11px]">{wizardData.type_key}</code></div>
                  <div><strong className="text-[#0F172A]">Category:</strong> {wizardData.category}</div>
                  <div><strong className="text-[#0F172A]">Attributes:</strong> {wizardData.attributes.length} configured</div>
                </div>

                <div className="max-h-40 overflow-y-auto space-y-1 p-2 border border-[#E2E8F0] rounded-md">
                  {wizardData.attributes.map((attr, i) => (
                    <div key={i} className="flex justify-between items-center text-[11px] p-1.5 bg-white rounded border border-slate-100">
                      <span className="font-medium text-[#0F172A]">{attr.display_label}</span>
                      <span className="font-mono text-[10px] text-[#64748B]">{attr.attribute_key}</span>
                    </div>
                  ))}
                </div>

                <div className="flex justify-between pt-3 border-t border-[#E2E8F0]">
                  <button
                    onClick={() => setWizardStep(2)}
                    className="px-3 py-1.5 rounded-md border border-[#CBD5E1] text-[12px] font-medium text-[#64748B]"
                  >
                    ← Back
                  </button>
                  <button
                    onClick={handleCreateDocumentType}
                    disabled={publishing}
                    className="px-4 py-1.5 rounded-md bg-[#2563EB] hover:bg-[#1D4ED8] text-white text-[12px] font-medium disabled:opacity-50"
                  >
                    {publishing ? 'Publishing...' : 'Confirm & Open Workspace'}
                  </button>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

    </div>
  );
}
