import React, { useState, useEffect, useRef } from 'react';
import { api } from '../api';

export default function Header({
  activeTab,
  onSelectTab,
  officerName = 'Arjun Mehta',
  onUpdateOfficerName,
  onNavigateToDocument,
  onNavigateToApplicant,
  onToggleWelcome,
}) {
  // Navigation tabs - 6 focused enterprise pages
  const navItems = [
    { id: 'overview', label: 'Overview' },
    { id: 'repository', label: 'Document Repository' },
    { id: 'upload', label: 'Upload Documents' },
    { id: 'verification', label: 'Verification' },
    { id: 'triangulation', label: 'Triangulation' },
    { id: 'reports', label: 'Reports' },
  ];

  // Search state
  const [searchQuery, setSearchQuery] = useState('');
  const [searchResults, setSearchResults] = useState(null);
  const [isSearching, setIsSearching] = useState(false);
  const [isSearchOpen, setIsSearchOpen] = useState(false);
  const searchContainerRef = useRef(null);

  // Profile dropdown state
  const [isProfileOpen, setIsProfileOpen] = useState(false);
  const [isEditingName, setIsEditingName] = useState(false);
  const [editedName, setEditedName] = useState(officerName);
  const [demoNotice, setDemoNotice] = useState(null);
  const profileContainerRef = useRef(null);

  // Sync editedName when officerName prop updates
  useEffect(() => {
    setEditedName(officerName);
  }, [officerName]);

  // Click outside listener for search & profile dropdowns
  useEffect(() => {
    const handleClickOutside = (e) => {
      if (searchContainerRef.current && !searchContainerRef.current.contains(e.target)) {
        setIsSearchOpen(false);
      }
      if (profileContainerRef.current && !profileContainerRef.current.contains(e.target)) {
        setIsProfileOpen(false);
        setIsEditingName(false);
      }
    };
    document.addEventListener('mousedown', handleClickOutside);
    return () => document.removeEventListener('mousedown', handleClickOutside);
  }, []);

  // Debounced search effect
  useEffect(() => {
    if (!searchQuery.trim()) {
      setSearchResults(null);
      setIsSearching(false);
      return;
    }

    setIsSearching(true);
    setIsSearchOpen(true);
    const timer = setTimeout(async () => {
      try {
        const res = await api.search(searchQuery.trim());
        setSearchResults(res.data);
      } catch (err) {
        console.error('Search failed:', err);
        setSearchResults({ applicants: [], documents: [] });
      } finally {
        setIsSearching(false);
      }
    }, 250);

    return () => clearTimeout(timer);
  }, [searchQuery]);

  const handleClearSearch = () => {
    setSearchQuery('');
    setSearchResults(null);
    setIsSearchOpen(false);
  };

  const handleSaveName = (e) => {
    e.preventDefault();
    if (editedName.trim()) {
      onUpdateOfficerName(editedName.trim());
      setIsEditingName(false);
    }
  };

  const handleResetDemo = async () => {
    try {
      setDemoNotice('Resetting dataset...');
      const res = await api.resetDemo();
      setDemoNotice('Demo dataset reset to benchmark state.');
      setTimeout(() => {
        setDemoNotice(null);
        window.location.reload();
      }, 900);
    } catch (err) {
      setDemoNotice('Reset failed: ' + err.message);
      setTimeout(() => setDemoNotice(null), 3000);
    }
  };

  const getInitials = (name) => {
    if (!name) return 'RO';
    return name
      .split(' ')
      .map((n) => n[0])
      .join('')
      .substring(0, 2)
      .toUpperCase();
  };

  return (
    <header className="fixed top-0 left-0 right-0 z-50 bg-white/95 backdrop-blur-md border-b border-[#E2E8F0]">
      <div className="max-w-[1520px] mx-auto h-16 px-6 lg:px-8 flex items-center justify-between gap-6">
        
        {/* Brand & Blue Dot Welcome Trigger */}
        <div className="flex items-center gap-3 shrink-0">
          <button
            type="button"
            onClick={onToggleWelcome}
            className="w-3 h-3 rounded-full bg-[#2563EB] hover:scale-125 hover:ring-4 hover:ring-blue-100 transition-all focus:outline-none cursor-pointer"
            title="Welcome Desk & Guide (Click to open)"
            aria-label="Welcome Desk"
          />
          <button
            type="button"
            onClick={() => onSelectTab('overview')}
            className="font-bold text-[14px] tracking-wide text-[#0F172A] hover:text-[#2563EB] transition-colors focus:outline-none cursor-pointer"
          >
            VERIDOC AI
          </button>
        </div>

        {/* Navigation Links (Desktop) */}
        <nav className="hidden xl:flex items-center gap-5 h-full">
          {navItems.map((item) => {
            const isActive = activeTab === item.id;
            return (
              <button
                key={item.id}
                onClick={() => onSelectTab(item.id)}
                className={`h-full flex items-center text-[13px] transition-colors border-b-2 font-medium ${
                  isActive
                    ? 'text-[#0F172A] border-[#2563EB] font-semibold text-[#2563EB]'
                    : 'text-[#64748B] border-transparent hover:text-[#0F172A]'
                }`}
              >
                {item.label}
              </button>
            );
          })}
        </nav>

        {/* Navigation Selector for Tablet & Smaller Viewports */}
        <div className="flex xl:hidden items-center">
          <select
            value={activeTab}
            onChange={(e) => onSelectTab(e.target.value)}
            className="bg-[#F8FAFC] border border-[#CBD5E1] text-[12px] font-medium text-[#0F172A] rounded-md px-2.5 py-1 focus:outline-none focus:ring-1 focus:ring-[#2563EB]"
          >
            {navItems.map((item) => (
              <option key={item.id} value={item.id}>
                {item.label}
              </option>
            ))}
          </select>
        </div>

        {/* Search & Officer Profile */}
        <div className="flex items-center gap-4 shrink-0">
          
          {/* Functional Global Search */}
          <div className="relative" ref={searchContainerRef}>
            <div className="flex items-center bg-[#F8FAFC] border border-[#E2E8F0] px-3 py-1.5 rounded-md focus-within:border-[#2563EB] focus-within:bg-white transition-all w-48 sm:w-64 lg:w-72">
              <span className="material-symbols-outlined text-[#94A3B8] text-[18px] mr-2 shrink-0">
                {isSearching ? 'progress_activity' : 'search'}
              </span>
              <input
                className="bg-transparent border-0 outline-none p-0 text-[13px] text-[#0F172A] placeholder:text-[#94A3B8] w-full focus:ring-0"
                placeholder="Search applicants, docs, IDs..."
                type="text"
                value={searchQuery}
                onChange={(e) => setSearchQuery(e.target.value)}
                onFocus={() => {
                  if (searchQuery.trim() && searchResults) setIsSearchOpen(true);
                }}
              />
              {searchQuery && (
                <button
                  type="button"
                  onClick={handleClearSearch}
                  className="text-[#94A3B8] hover:text-[#0F172A] ml-1 text-[13px] font-bold"
                >
                  ✕
                </button>
              )}
            </div>

            {/* Dropdown Results Box */}
            {isSearchOpen && (
              <div className="absolute right-0 top-full mt-2 w-80 sm:w-96 bg-white border border-[#E2E8F0] rounded-lg shadow-xl overflow-hidden z-50 max-h-[460px] flex flex-col">
                <div className="p-2.5 bg-[#F8FAFC] border-b border-[#E2E8F0] flex items-center justify-between text-[11px] font-bold tracking-wider uppercase text-[#64748B]">
                  <span>Search Results</span>
                  {isSearching && <span className="animate-pulse text-[#2563EB]">Searching...</span>}
                </div>

                <div className="overflow-y-auto divide-y divide-[#F1F5F9]">
                  {/* Empty State */}
                  {searchResults &&
                    searchResults.applicants.length === 0 &&
                    searchResults.documents.length === 0 && (
                      <div className="p-6 text-center text-[#64748B] text-[13px]">
                        <span className="material-symbols-outlined text-[28px] text-[#94A3B8] block mb-1">
                          search_off
                        </span>
                        No records match <span className="font-semibold text-[#0F172A]">"{searchQuery}"</span>
                      </div>
                    )}

                  {/* Applicants Group */}
                  {searchResults?.applicants?.length > 0 && (
                    <div className="p-2">
                      <div className="px-2 py-1 text-[11px] font-bold uppercase tracking-wider text-[#94A3B8]">
                        Applicants ({searchResults.applicants.length})
                      </div>
                      {searchResults.applicants.map((app) => (
                        <div
                          key={app.id}
                          onClick={() => {
                            onNavigateToApplicant(app.id);
                            setIsSearchOpen(false);
                            setSearchQuery('');
                          }}
                          className="p-2 rounded hover:bg-[#F8FAFC] cursor-pointer transition-colors flex items-center justify-between"
                        >
                          <div>
                            <div className="text-[13px] font-semibold text-[#0F172A]">
                              {app.name}
                            </div>
                            <div className="text-[11px] text-[#64748B] flex items-center gap-2">
                              <span>{app.id}</span>
                              {app.phone && <span>· {app.phone}</span>}
                            </div>
                          </div>
                          <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded ${
                            app.status === 'verified'
                              ? 'bg-[#EDF4EE] text-[#2E5A36]'
                              : app.status === 'requires_attention'
                              ? 'bg-[#F9EFEB] text-[#8C3B30]'
                              : 'bg-[#EDF3F8] text-[#3B6282]'
                          }`}>
                            {app.status}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                  {/* Documents Group */}
                  {searchResults?.documents?.length > 0 && (
                    <div className="p-2">
                      <div className="px-2 py-1 text-[11px] font-bold uppercase tracking-wider text-[#94A3B8]">
                        Documents ({searchResults.documents.length})
                      </div>
                      {searchResults.documents.map((doc) => (
                        <div
                          key={doc.id}
                          onClick={() => {
                            onNavigateToDocument(doc.id);
                            setIsSearchOpen(false);
                            setSearchQuery('');
                          }}
                          className="p-2 rounded hover:bg-[#F8FAFC] cursor-pointer transition-colors flex items-center justify-between"
                        >
                          <div className="min-w-0 pr-2">
                            <div className="text-[13px] font-semibold text-[#0F172A] truncate">
                              {doc.original_filename}
                            </div>
                            <div className="text-[11px] text-[#64748B] flex items-center gap-1.5 truncate">
                              <span className="font-medium text-[#2563EB]">
                                {(doc.classified_type || doc.document_type || 'UNKNOWN').toUpperCase()}
                              </span>
                              <span>·</span>
                              <span>{doc.applicant_name}</span>
                            </div>
                          </div>
                          <span className={`text-[10px] font-semibold uppercase px-2 py-0.5 rounded shrink-0 ${
                            doc.review_status === 'approved'
                              ? 'bg-[#EDF4EE] text-[#2E5A36]'
                              : doc.review_status === 'manual_review' || doc.review_status === 'rejected'
                              ? 'bg-[#F9EFEB] text-[#8C3B30]'
                              : 'bg-[#EDF3F8] text-[#3B6282]'
                          }`}>
                            {doc.review_status}
                          </span>
                        </div>
                      ))}
                    </div>
                  )}

                </div>
              </div>
            )}
          </div>

          {/* Officer Profile Badge (Icon-only) & Interactive Compact Dropdown */}
          <div className="relative" ref={profileContainerRef}>
            <button
              type="button"
              onClick={() => setIsProfileOpen(!isProfileOpen)}
              className="flex items-center justify-center focus:outline-none group p-0.5 rounded-full hover:ring-2 hover:ring-[#2563EB]/30 transition-all"
              title={`Review Officer: ${officerName}`}
              aria-label="Officer Profile Menu"
            >
              <div className="w-8 h-8 rounded-full bg-[#0F172A] text-white flex items-center justify-center font-semibold text-[12px] tracking-wide shadow-xs group-hover:bg-[#2563EB] transition-colors">
                {getInitials(officerName)}
              </div>
            </button>

            {/* Profile Dropdown Menu */}
            {isProfileOpen && (
              <div className="absolute right-0 top-full mt-2 w-72 bg-white border border-[#E2E8F0] rounded-lg shadow-xl overflow-hidden z-50 animate-in fade-in">
                
                {/* Header profile info */}
                <div className="p-4 bg-[#F8FAFC] border-b border-[#E2E8F0]">
                  <div className="flex items-center gap-3">
                    <div className="w-10 h-10 rounded-full bg-[#0F172A] text-white flex items-center justify-center font-bold text-[14px]">
                      {getInitials(officerName)}
                    </div>
                    <div>
                      <div className="text-[14px] font-bold text-[#0F172A]">{officerName}</div>
                      <div className="text-[11px] font-medium text-[#2563EB]">Review Officer</div>
                      <div className="text-[10px] text-[#64748B]">Housing Finance Verification Desk</div>
                    </div>
                  </div>
                </div>

                {/* Edit Officer Name Form */}
                <div className="p-3 border-b border-[#E2E8F0]">
                  {!isEditingName ? (
                    <button
                      type="button"
                      onClick={() => setIsEditingName(true)}
                      className="w-full text-left text-[12px] text-[#2563EB] hover:underline font-medium flex items-center justify-between"
                    >
                      <span>Edit Officer Name</span>
                      <span className="material-symbols-outlined text-[15px]">edit</span>
                    </button>
                  ) : (
                    <form onSubmit={handleSaveName} className="space-y-2">
                      <label className="text-[11px] font-bold uppercase text-[#64748B]">Update Name</label>
                      <input
                        type="text"
                        value={editedName}
                        onChange={(e) => setEditedName(e.target.value)}
                        className="w-full px-2.5 py-1 text-[13px] border border-[#CBD5E1] rounded focus:border-[#2563EB] focus:outline-none"
                        placeholder="Enter officer name"
                        autoFocus
                      />
                      <div className="flex items-center gap-2 pt-1">
                        <button
                          type="submit"
                          className="px-3 py-1 bg-[#0F172A] text-white text-[11px] font-semibold rounded hover:bg-[#1E293B]"
                        >
                          Save
                        </button>
                        <button
                          type="button"
                          onClick={() => {
                            setEditedName(officerName);
                            setIsEditingName(false);
                          }}
                          className="px-2 py-1 text-[11px] text-[#64748B] hover:text-[#0F172A]"
                        >
                          Cancel
                        </button>
                      </div>
                    </form>
                  )}
                </div>

                {/* Dropdown Actions */}
                <div className="p-2 space-y-1">
                  <button
                    type="button"
                    onClick={() => {
                      setIsProfileOpen(false);
                      onNavigateToWelcome();
                    }}
                    className="w-full text-left px-3 py-2 text-[13px] text-[#0F172A] hover:bg-[#F8FAFC] rounded flex items-center gap-2 transition-colors"
                  >
                    <span className="material-symbols-outlined text-[17px] text-[#64748B]">home</span>
                    <span>Exit to Welcome Page</span>
                  </button>

                  <button
                    type="button"
                    onClick={handleResetDemo}
                    className="w-full text-left px-3 py-2 text-[13px] text-[#8C3B30] hover:bg-[#F9EFEB] rounded flex items-center gap-2 transition-colors"
                  >
                    <span className="material-symbols-outlined text-[17px]">restart_alt</span>
                    <span>Reset Synthetic Demo Dataset</span>
                  </button>
                </div>

                {/* Status Notice */}
                {demoNotice && (
                  <div className="p-2.5 bg-blue-50 border-t border-blue-200 text-[11px] text-blue-800 text-center">
                    {demoNotice}
                  </div>
                )}

              </div>
            )}
          </div>

        </div>

      </div>
    </header>
  );
}
