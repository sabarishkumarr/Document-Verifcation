import React, { useState, useEffect } from 'react';
import { api } from '../api';

const SlidersIcon = ({ className = "w-5 h-5" }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 6V4m0 2a2 2 0 100 4m0-4a2 2 0 110 4m-6 8a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4m6 6v10m6-2a2 2 0 100-4m0 4a2 2 0 110-4m0 4v2m0-6V4" />
  </svg>
);
const SparklesIcon = ({ className = "w-4 h-4" }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M5 3v4M3 5h4M6 17v4m-2-2h4m5-16l2.286 6.857L21 12l-5.714 2.143L13 21l-2.286-6.857L5 12l5.714-2.143L13 3z" />
  </svg>
);
const HistoryIcon = ({ className = "w-4 h-4" }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 8v4l3 3m6-3a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);
const SaveIcon = ({ className = "w-4 h-4" }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M8 7H5a2 2 0 00-2 2v9a2 2 0 002 2h14a2 2 0 002-2V9a2 2 0 00-2-2h-3m-1 4l-3 3m0 0l-3-3m3 3V4" />
  </svg>
);
const CheckCircleIcon = ({ className = "w-4 h-4" }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m6 2a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);
const AlertTriangleIcon = ({ className = "w-4 h-4" }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 9v2m0 4h.01m-6.938 4h13.856c1.54 0 2.502-1.667 1.732-3L13.732 4c-.77-1.333-2.694-1.333-3.464 0L3.34 16c-.77 1.333.192 3 1.732 3z" />
  </svg>
);
const XCircleIcon = ({ className = "w-4 h-4" }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M10 14l2-2m0 0l2-2m-2 2l-2-2m2 2l2 2m7-2a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);
const PlusIcon = ({ className = "w-4 h-4" }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M12 4v16m8-8H4" />
  </svg>
);
const RotateCcwIcon = ({ className = "w-4 h-4" }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
  </svg>
);
const ShieldCheckIcon = ({ className = "w-4 h-4" }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12l2 2 4-4m5.618-4.016A11.955 11.955 0 0112 2.944a11.955 11.955 0 01-8.618 3.04A12.02 12.02 0 003 9c0 5.591 3.824 10.29 9 11.622 5.176-1.332 9-6.03 9-11.622 0-1.042-.133-2.052-.382-3.016z" />
  </svg>
);
const ArrowRightIcon = ({ className = "w-3 h-3" }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M14 5l7 7m0 0l-7 7m7-7H3" />
  </svg>
);
const InfoIcon = ({ className = "w-4 h-4" }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M13 16h-1v-4h-1m1-4h.01M21 12a9 9 0 11-18 0 9 9 0 0118 0z" />
  </svg>
);
const RefreshCwIcon = ({ className = "w-5 h-5" }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M4 4v5h.582m15.356 2A8.001 8.001 0 004.582 9m0 0H9m11 11v-5h-.581m0 0a8.003 8.003 0 01-15.357-2m15.357 2H15" />
  </svg>
);
const FileTextIcon = ({ className = "w-3 h-3" }) => (
  <svg className={className} fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 12h6m-6 4h6m2 5H7a2 2 0 01-2-2V5a2 2 0 012-2h5.586a1 1 0 01.707.293l5.414 5.414a1 1 0 01.293.707V19a2 2 0 01-2 2z" />
  </svg>
);

const NORMALIZATION_OPTIONS = [
  { value: 'normalized_text', label: 'Normalized Text (Case/Punctuation Insensitive)' },
  { value: 'exact', label: 'Exact Match' },
  { value: 'date_iso', label: 'Date (ISO YYYY-MM-DD)' },
  { value: 'fuzzy_text', label: 'Fuzzy Text (Address Matching)' },
  { value: 'currency', label: 'Currency / Number' },
  { value: 'identifier', label: 'Identifier / Alphanumeric Scheme' }
];

export default function TriangulationView() {
  const [combinations, setCombinations] = useState([]);
  const [registeredTypes, setRegisteredTypes] = useState([]);
  const [selectedCombinationKey, setSelectedCombinationKey] = useState('');
  
  // Active Policy Configuration State
  const [currentConfig, setCurrentConfig] = useState(null);
  const [rules, setRules] = useState([]);
  const [activeVersion, setActiveVersion] = useState(1);
  const [loading, setLoading] = useState(true);
  const [discovering, setDiscovering] = useState(false);
  const [saving, setSaving] = useState(false);
  const [statusMessage, setStatusMessage] = useState(null);
  const [errorMessage, setErrorMessage] = useState(null);

  // Custom Combination Modal State
  const [isCustomModalOpen, setIsCustomModalOpen] = useState(false);
  const [selectedCustomTypes, setSelectedCustomTypes] = useState([]);

  // Version History Modal State
  const [isHistoryModalOpen, setIsHistoryModalOpen] = useState(false);
  const [versionHistory, setVersionHistory] = useState([]);
  const [loadingHistory, setLoadingHistory] = useState(false);
  const [changeSummary, setChangeSummary] = useState('');

  useEffect(() => {
    loadCombinationsCatalog();
  }, []);

  useEffect(() => {
    if (selectedCombinationKey) {
      loadCombinationRules(selectedCombinationKey);
    }
  }, [selectedCombinationKey]);

  const loadCombinationsCatalog = async () => {
    try {
      setLoading(true);
      setErrorMessage(null);
      const res = await api.getTriangulationCombinations();
      if (res.success) {
        setCombinations(res.combinations || []);
        setRegisteredTypes(res.registered_document_types || []);
        if (res.combinations?.length > 0 && !selectedCombinationKey) {
          setSelectedCombinationKey(res.combinations[0].combination_key);
        }
      }
    } catch (err) {
      setErrorMessage(err.message || 'Failed to load document combination catalog.');
    } finally {
      setLoading(false);
    }
  };

  const loadCombinationRules = async (comboKey) => {
    try {
      setLoading(true);
      setErrorMessage(null);
      const res = await api.getCombinationRules(comboKey);
      if (res.success && res.data) {
        setCurrentConfig(res.data.configuration);
        setActiveVersion(res.data.active_version);
        setRules(res.data.rules || []);
      }
    } catch (err) {
      setErrorMessage(err.message || `Could not load rules for combination: ${comboKey}`);
    } finally {
      setLoading(false);
    }
  };

  const handleDiscoverRules = async () => {
    if (!selectedCombinationKey) return;
    try {
      setDiscovering(true);
      setErrorMessage(null);
      const res = await api.discoverCombinationRules(selectedCombinationKey);
      if (res.success && res.data?.rules) {
        setRules(res.data.rules);
        setStatusMessage({
          type: 'success',
          text: `AI attribute discovery analyzed schemas and suggested ${res.data.total_rules_discovered} comparison rules. Review recommendations and click "Publish Version" to persist.`
        });
      }
    } catch (err) {
      setErrorMessage(err.message || 'AI rule discovery encountered an error.');
    } finally {
      setDiscovering(false);
    }
  };

  const handleToggleRule = (index) => {
    setRules((prevRules) => {
      const updated = [...prevRules];
      updated[index] = {
        ...updated[index],
        is_enabled: !updated[index].is_enabled
      };
      return updated;
    });
  };

  const handleNormalizationChange = (index, value) => {
    setRules((prevRules) => {
      const updated = [...prevRules];
      updated[index] = {
        ...updated[index],
        normalization: value
      };
      return updated;
    });
  };

  const handlePublishVersion = async () => {
    if (!selectedCombinationKey) return;
    try {
      setSaving(true);
      setErrorMessage(null);
      const payload = {
        rules: rules,
        published_by: 'Compliance Reviewer',
        change_summary: changeSummary.trim() || 'Updated attribute comparison rules and normalizations'
      };

      const res = await api.saveCombinationRules(selectedCombinationKey, payload);
      if (res.success && res.data) {
        setActiveVersion(res.data.version);
        setChangeSummary('');
        setStatusMessage({
          type: 'success',
          text: `Policy Version ${res.data.version} published and activated across platform verification engine.`
        });
        loadCombinationsCatalog();
      }
    } catch (err) {
      setErrorMessage(err.message || 'Failed to publish new policy version.');
    } finally {
      setSaving(false);
    }
  };

  const openHistoryModal = async () => {
    if (!selectedCombinationKey) return;
    setIsHistoryModalOpen(true);
    setLoadingHistory(true);
    try {
      const res = await api.getCombinationVersions(selectedCombinationKey);
      if (res.success) {
        setVersionHistory(res.versions || []);
      }
    } catch (err) {
      setErrorMessage('Could not load version history.');
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleRollbackVersion = async (targetVersion) => {
    if (!selectedCombinationKey) return;
    try {
      setLoadingHistory(true);
      const res = await api.rollbackCombinationVersion(selectedCombinationKey, targetVersion);
      if (res.success) {
        setIsHistoryModalOpen(false);
        setStatusMessage({
          type: 'success',
          text: `Successfully rolled back to Policy Version ${targetVersion}.`
        });
        loadCombinationRules(selectedCombinationKey);
        loadCombinationsCatalog();
      }
    } catch (err) {
      setErrorMessage(err.message || 'Rollback failed.');
    } finally {
      setLoadingHistory(false);
    }
  };

  const handleCreateCustomCombination = () => {
    if (selectedCustomTypes.length < 2) {
      setErrorMessage('Please select at least 2 document types to configure a comparison combination.');
      return;
    }
    const cleanTypes = [...new Set(selectedCustomTypes)].sort();
    const newKey = cleanTypes.join('+');
    setIsCustomModalOpen(false);
    setSelectedCustomTypes([]);
    setSelectedCombinationKey(newKey);
  };

  const renderRecommendationBadge = (recommendation) => {
    switch (recommendation) {
      case 'COMPARE':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-emerald-50 text-emerald-700 border border-emerald-200">
            <CheckCircleIcon className="w-3 h-3 text-emerald-600" />
            Compare
          </span>
        );
      case 'CONDITIONAL':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-amber-50 text-amber-700 border border-amber-200">
            <AlertTriangleIcon className="w-3 h-3 text-amber-600" />
            Conditional
          </span>
        );
      case 'NOT_RECOMMENDED':
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-rose-50 text-rose-700 border border-rose-200">
            <XCircleIcon className="w-3 h-3 text-rose-600" />
            Not Recommended
          </span>
        );
      case 'SINGLE_DOC':
      default:
        return (
          <span className="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-medium bg-slate-100 text-slate-600 border border-slate-200">
            <FileTextIcon className="w-3 h-3 text-slate-500" />
            Single Doc
          </span>
        );
    }
  };

  const enabledRulesCount = rules.filter((r) => r.is_enabled).length;

  return (
    <div className="space-y-6">
      {/* Top Banner & Header */}
      <div className="bg-white border border-slate-200 rounded-xl p-6 shadow-sm">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-4">
          <div>
            <div className="flex items-center gap-3">
              <div className="p-2.5 bg-blue-50 text-blue-700 rounded-lg border border-blue-100">
                <SlidersIcon className="w-6 h-6" />
              </div>
              <div>
                <h1 className="text-xl font-bold text-slate-900 tracking-tight">
                  Cross-Document Comparison Rules
                </h1>
                <p className="text-xs text-slate-500 mt-0.5">
                  Configure authoritative attribute-level comparison policies enforced by the platform verification engine.
                </p>
              </div>
            </div>
          </div>

          {/* Quick Stats & Controls */}
          <div className="flex items-center gap-2">
            <button
              onClick={() => setIsCustomModalOpen(true)}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-slate-700 bg-slate-50 hover:bg-slate-100 border border-slate-200 rounded-lg transition-colors cursor-pointer"
            >
              <PlusIcon className="w-4 h-4 text-slate-500" />
              New Combination
            </button>
            <button
              onClick={openHistoryModal}
              className="inline-flex items-center gap-1.5 px-3 py-2 text-xs font-medium text-slate-700 bg-white hover:bg-slate-50 border border-slate-200 rounded-lg transition-colors cursor-pointer"
            >
              <HistoryIcon className="w-4 h-4 text-slate-500" />
              Version History
            </button>
            <button
              onClick={handleDiscoverRules}
              disabled={discovering || !selectedCombinationKey}
              className="inline-flex items-center gap-1.5 px-3.5 py-2 text-xs font-semibold text-blue-700 bg-blue-50 hover:bg-blue-100 border border-blue-200 rounded-lg transition-colors disabled:opacity-50 cursor-pointer"
            >
              <SparklesIcon className={`w-4 h-4 ${discovering ? 'animate-spin' : 'text-blue-600'}`} />
              {discovering ? 'Analyzing Schemas...' : 'AI Discover Rules'}
            </button>
            <button
              onClick={handlePublishVersion}
              disabled={saving || rules.length === 0}
              className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm transition-colors disabled:opacity-50 cursor-pointer"
            >
              <SaveIcon className="w-4 h-4" />
              {saving ? 'Publishing...' : 'Publish Version'}
            </button>
          </div>
        </div>

        {/* Status and Error Alerts */}
        {statusMessage && (
          <div className="mt-4 p-3 bg-emerald-50 border border-emerald-200 rounded-lg flex items-start justify-between text-xs text-emerald-800">
            <div className="flex items-center gap-2">
              <CheckCircleIcon className="w-4 h-4 text-emerald-600 flex-shrink-0" />
              <span>{statusMessage.text}</span>
            </div>
            <button
              onClick={() => setStatusMessage(null)}
              className="text-emerald-600 hover:text-emerald-800 font-semibold cursor-pointer"
            >
              Dismiss
            </button>
          </div>
        )}

        {errorMessage && (
          <div className="mt-4 p-3 bg-rose-50 border border-rose-200 rounded-lg flex items-start justify-between text-xs text-rose-800">
            <div className="flex items-center gap-2">
              <AlertTriangleIcon className="w-4 h-4 text-rose-600 flex-shrink-0" />
              <span>{errorMessage}</span>
            </div>
            <button
              onClick={() => setErrorMessage(null)}
              className="text-rose-600 hover:text-rose-800 font-semibold cursor-pointer"
            >
              Dismiss
            </button>
          </div>
        )}
      </div>

      {/* Main Workspace Grid */}
      <div className="grid grid-cols-1 lg:grid-cols-4 gap-6">
        {/* Left Column: Combination Selector & Policy Details */}
        <div className="lg:col-span-1 space-y-4">
          <div className="bg-white border border-slate-200 rounded-xl p-4 shadow-sm space-y-4">
            <div>
              <label className="block text-xs font-semibold text-slate-700 uppercase tracking-wider mb-2">
                Document Combination
              </label>
              <select
                value={selectedCombinationKey}
                onChange={(e) => setSelectedCombinationKey(e.target.value)}
                className="w-full text-xs rounded-lg border-slate-200 focus:border-blue-500 focus:ring-blue-500 bg-slate-50 font-medium p-2.5 border"
              >
                {combinations.map((c) => (
                  <option key={c.combination_key} value={c.combination_key}>
                    {c.name || c.combination_key.replace(/\+/g, ' + ').toUpperCase()}
                  </option>
                ))}
              </select>
            </div>

            {currentConfig && (
              <div className="pt-3 border-t border-slate-100 space-y-3">
                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-500">Active Policy:</span>
                  <span className="inline-flex items-center gap-1 px-2 py-0.5 rounded font-bold bg-blue-50 text-blue-700 border border-blue-200">
                    <ShieldCheckIcon className="w-3.5 h-3.5" />
                    Version {activeVersion}
                  </span>
                </div>

                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-500">Participating Types:</span>
                  <span className="font-semibold text-slate-800">
                    {currentConfig.document_types?.length || 2} documents
                  </span>
                </div>

                <div className="flex items-center justify-between text-xs">
                  <span className="text-slate-500">Active Rules:</span>
                  <span className="font-semibold text-slate-800">
                    {enabledRulesCount} of {rules.length} enabled
                  </span>
                </div>

                <div className="p-3 bg-slate-50 rounded-lg border border-slate-100 text-xs text-slate-600 space-y-1">
                  <p className="font-medium text-slate-700">Policy Description:</p>
                  <p className="text-slate-500 leading-relaxed text-xs">
                    {currentConfig.description || 'Configured cross-document matching and discrepancy detection rules.'}
                  </p>
                </div>
              </div>
            )}
          </div>

          {/* Policy Compliance Guideline */}
          <div className="bg-blue-50/50 border border-blue-100 rounded-xl p-4 text-xs text-blue-900 space-y-2">
            <div className="flex items-center gap-2 font-semibold text-blue-800">
              <InfoIcon className="w-4 h-4 text-blue-600" />
              Policy Enforcement Rules
            </div>
            <p className="text-slate-600 leading-relaxed">
              <strong>Disabled rules</strong> are strictly excluded from execution during automated applicant verification and will not trigger discrepancy flags.
            </p>
            <p className="text-slate-600 leading-relaxed">
              <strong>Missing values</strong> on single documents are categorized as <code className="bg-slate-200 px-1 py-0.5 rounded">MISSING</code>, never treated as hard fraud mismatches.
            </p>
          </div>
        </div>

        {/* Right Column: Interactive Rules Configuration Table */}
        <div className="lg:col-span-3">
          <div className="bg-white border border-slate-200 rounded-xl shadow-sm overflow-hidden">
            <div className="px-5 py-4 border-b border-slate-100 flex items-center justify-between bg-slate-50/50">
              <div>
                <h2 className="text-sm font-bold text-slate-900">
                  Configured Comparison Rules
                </h2>
                <p className="text-xs text-slate-500 mt-0.5">
                  Toggle rules on/off and assign normalization routines. Results apply to all subsequent verifications.
                </p>
              </div>
              <div className="text-xs font-semibold text-slate-600">
                {enabledRulesCount} / {rules.length} Rules Active
              </div>
            </div>

            {loading ? (
              <div className="p-12 text-center text-xs text-slate-500">
                <RefreshCwIcon className="w-6 h-6 animate-spin mx-auto text-blue-600 mb-2" />
                Loading policy rules...
              </div>
            ) : rules.length === 0 ? (
              <div className="p-12 text-center">
                <SlidersIcon className="w-8 h-8 text-slate-300 mx-auto mb-2" />
                <h3 className="text-sm font-semibold text-slate-800">No Comparison Rules Defined</h3>
                <p className="text-xs text-slate-500 max-w-sm mx-auto mt-1 mb-4">
                  Run AI attribute discovery to automatically compare the registered schemas and generate rules.
                </p>
                <button
                  onClick={handleDiscoverRules}
                  disabled={discovering}
                  className="inline-flex items-center gap-1.5 px-4 py-2 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg shadow-sm cursor-pointer"
                >
                  <SparklesIcon className="w-4 h-4" />
                  Run AI Attribute Discovery
                </button>
              </div>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-left text-xs text-slate-700">
                  <thead className="bg-slate-50 border-b border-slate-200 text-slate-600 font-semibold uppercase tracking-wider text-[11px]">
                    <tr>
                      <th className="px-4 py-3 text-center w-16">Active</th>
                      <th className="px-4 py-3">Attribute Comparison</th>
                      <th className="px-4 py-3 w-32">Recommendation</th>
                      <th className="px-4 py-3">AI Explanation / Justification</th>
                      <th className="px-4 py-3 w-56">Normalization Strategy</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-100">
                    {rules.map((rule, idx) => (
                      <tr
                        key={rule.id || idx}
                        className={`hover:bg-slate-50/80 transition-colors ${
                          !rule.is_enabled ? 'opacity-50 bg-slate-50/40' : ''
                        }`}
                      >
                        {/* Enable/Disable Toggle */}
                        <td className="px-4 py-3.5 text-center">
                          <input
                            type="checkbox"
                            checked={rule.is_enabled}
                            onChange={() => handleToggleRule(idx)}
                            className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 h-4 w-4 cursor-pointer"
                          />
                        </td>

                        {/* Attribute Mapping */}
                        <td className="px-4 py-3.5">
                          <div className="font-semibold text-slate-900 flex items-center gap-1.5">
                            <span className="capitalize">{rule.source_doc_type.replace('_', ' ')}</span>
                            <span className="text-slate-400 font-mono text-[11px]">({rule.source_attribute})</span>
                            {rule.target_doc_type !== '-' && (
                              <>
                                <ArrowRightIcon className="w-3 h-3 text-slate-400" />
                                <span className="capitalize">{rule.target_doc_type.replace('_', ' ')}</span>
                                <span className="text-slate-400 font-mono text-[11px]">({rule.target_attribute})</span>
                              </>
                            )}
                          </div>
                          <div className="text-[11px] text-slate-500 mt-0.5">
                            {rule.source_label} {rule.target_label !== '-' ? `↔ ${rule.target_label}` : '(Single Document)'}
                          </div>
                        </td>

                        {/* AI Recommendation Badge */}
                        <td className="px-4 py-3.5 whitespace-nowrap">
                          {renderRecommendationBadge(rule.recommendation)}
                        </td>

                        {/* Explanation */}
                        <td className="px-4 py-3.5">
                          <p className="text-slate-600 text-xs leading-relaxed max-w-md">
                            {rule.explanation}
                          </p>
                        </td>

                        {/* Normalization Strategy */}
                        <td className="px-4 py-3.5">
                          <select
                            value={rule.normalization || 'exact'}
                            disabled={!rule.is_enabled}
                            onChange={(e) => handleNormalizationChange(idx, e.target.value)}
                            className="w-full text-xs rounded-md border-slate-200 focus:border-blue-500 focus:ring-blue-500 p-1.5 border bg-white disabled:bg-slate-100"
                          >
                            {NORMALIZATION_OPTIONS.map((opt) => (
                              <option key={opt.value} value={opt.value}>
                                {opt.label}
                              </option>
                            ))}
                          </select>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </div>
        </div>
      </div>

      {/* Version History Drawer / Modal */}
      {isHistoryModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 max-w-2xl w-full max-h-[80vh] flex flex-col">
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-slate-900">
                  Policy Version History — {selectedCombinationKey}
                </h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  View past revisions or restore an earlier approved comparison policy version.
                </p>
              </div>
              <button
                onClick={() => setIsHistoryModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 text-sm font-semibold p-1 cursor-pointer"
              >
                ✕
              </button>
            </div>

            <div className="p-6 overflow-y-auto space-y-3 flex-1">
              {loadingHistory ? (
                <div className="py-8 text-center text-xs text-slate-500">
                  <RefreshCwIcon className="w-5 h-5 animate-spin mx-auto text-blue-600 mb-2" />
                  Loading version history...
                </div>
              ) : versionHistory.length === 0 ? (
                <div className="text-center py-6 text-xs text-slate-500">
                  No historical versions recorded yet.
                </div>
              ) : (
                versionHistory.map((ver) => {
                  const isCurrent = ver.version === activeVersion;
                  return (
                    <div
                      key={ver.version}
                      className={`p-4 rounded-lg border transition-all ${
                        isCurrent
                          ? 'border-blue-300 bg-blue-50/50 shadow-sm'
                          : 'border-slate-200 bg-white hover:bg-slate-50'
                      }`}
                    >
                      <div className="flex items-center justify-between mb-2">
                        <div className="flex items-center gap-2">
                          <span className="font-bold text-sm text-slate-900">
                            Version {ver.version}
                          </span>
                          {isCurrent ? (
                            <span className="px-2 py-0.5 text-[10px] font-bold rounded-full bg-blue-100 text-blue-800 border border-blue-200">
                              CURRENT ACTIVE
                            </span>
                          ) : (
                            <span className="px-2 py-0.5 text-[10px] font-medium rounded-full bg-slate-100 text-slate-600">
                              Historical
                            </span>
                          )}
                        </div>
                        <div className="text-xs text-slate-500">
                          {ver.created_at ? new Date(ver.created_at).toLocaleString() : ''}
                        </div>
                      </div>

                      <p className="text-xs text-slate-600 mb-3">
                        {ver.change_summary || 'No change summary provided.'}
                      </p>

                      <div className="flex items-center justify-between text-xs pt-2 border-t border-slate-100">
                        <span className="text-slate-500">
                          Published by: <strong>{ver.published_by || 'System'}</strong> ({ver.enabled_rules} of {ver.total_rules} rules active)
                        </span>

                        {!isCurrent && (
                          <button
                            onClick={() => handleRollbackVersion(ver.version)}
                            className="inline-flex items-center gap-1 px-3 py-1 text-xs font-semibold text-blue-700 bg-white hover:bg-blue-50 border border-blue-200 rounded-md transition-colors shadow-2xs cursor-pointer"
                          >
                            <RotateCcwIcon className="w-3.5 h-3.5 text-blue-600" />
                            Rollback & Activate
                          </button>
                        )}
                      </div>
                    </div>
                  );
                })
              )}
            </div>

            <div className="px-6 py-3 border-t border-slate-100 bg-slate-50 flex justify-end rounded-b-xl">
              <button
                onClick={() => setIsHistoryModalOpen(false)}
                className="px-4 py-2 text-xs font-medium text-slate-700 bg-white border border-slate-200 rounded-lg hover:bg-slate-100 cursor-pointer"
              >
                Close
              </button>
            </div>
          </div>
        </div>
      )}

      {/* New Custom Combination Modal */}
      {isCustomModalOpen && (
        <div className="fixed inset-0 z-50 bg-slate-900/40 backdrop-blur-sm flex items-center justify-center p-4">
          <div className="bg-white rounded-xl shadow-xl border border-slate-200 max-w-md w-full">
            <div className="px-6 py-4 border-b border-slate-200 flex items-center justify-between">
              <div>
                <h3 className="text-sm font-bold text-slate-900">Configure New Combination</h3>
                <p className="text-xs text-slate-500 mt-0.5">
                  Select 2 or more document types to create an authoritative comparison policy.
                </p>
              </div>
              <button
                onClick={() => setIsCustomModalOpen(false)}
                className="text-slate-400 hover:text-slate-600 text-sm font-semibold p-1 cursor-pointer"
              >
                ✕
              </button>
            </div>

            <div className="p-6 space-y-3 max-h-80 overflow-y-auto">
              {registeredTypes.map((dt) => {
                const checked = selectedCustomTypes.includes(dt.type_key);
                return (
                  <label
                    key={dt.type_key}
                    className={`flex items-center justify-between p-3 rounded-lg border cursor-pointer transition-colors ${
                      checked
                        ? 'border-blue-400 bg-blue-50/50'
                        : 'border-slate-200 hover:bg-slate-50'
                    }`}
                  >
                    <div className="flex items-center gap-2.5">
                      <input
                        type="checkbox"
                        checked={checked}
                        onChange={() => {
                          if (checked) {
                            setSelectedCustomTypes((prev) => prev.filter((k) => k !== dt.type_key));
                          } else {
                            setSelectedCustomTypes((prev) => [...prev, dt.type_key]);
                          }
                        }}
                        className="rounded border-slate-300 text-blue-600 focus:ring-blue-500 h-4 w-4 cursor-pointer"
                      />
                      <div>
                        <div className="text-xs font-semibold text-slate-800">{dt.display_name}</div>
                        <div className="text-[10px] text-slate-400 font-mono">{dt.type_key}</div>
                      </div>
                    </div>
                    <span className="text-[10px] uppercase font-semibold text-slate-500 bg-slate-100 px-2 py-0.5 rounded">
                      {dt.category}
                    </span>
                  </label>
                );
              })}
            </div>

            <div className="px-6 py-3 border-t border-slate-100 bg-slate-50 flex items-center justify-between rounded-b-xl">
              <span className="text-xs text-slate-500">
                {selectedCustomTypes.length} type(s) selected
              </span>
              <div className="flex items-center gap-2">
                <button
                  onClick={() => setIsCustomModalOpen(false)}
                  className="px-3 py-1.5 text-xs font-medium text-slate-600 hover:text-slate-800 cursor-pointer"
                >
                  Cancel
                </button>
                <button
                  onClick={handleCreateCustomCombination}
                  disabled={selectedCustomTypes.length < 2}
                  className="px-4 py-1.5 text-xs font-semibold text-white bg-blue-600 hover:bg-blue-700 rounded-lg disabled:opacity-50 cursor-pointer"
                >
                  Create & Configure
                </button>
              </div>
            </div>
          </div>
        </div>
      )}
    </div>
  );
}
