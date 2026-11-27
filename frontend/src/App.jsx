import React, { useState, useEffect } from 'react';
import Header from './Components/Header';
import WelcomeView from './Components/WelcomeView';
import DashboardView from './Components/DashboardView';
import UploadView from './Components/UploadView';
import VerificationView from './Components/VerificationView';
import ReportsView from './Components/ReportsView';
import RepositoryView from './Components/RepositoryView';
import TriangulationView from './Components/TriangulationView';
import WelcomeDrawer from './Components/WelcomeDrawer';

export default function App() {
  // Operational workspace landing
  const [activeTab, setActiveTab] = useState('overview');
  const [queueDocId, setQueueDocId] = useState(null);
  const [applicantId, setApplicantId] = useState(null);
  const [isWelcomeOpen, setIsWelcomeOpen] = useState(false);

  // Review Officer name persisted in localStorage
  const [officerName, setOfficerName] = useState(() => {
    return localStorage.getItem('veridoc_officer_name') || 'Arjun Mehta';
  });

  const handleUpdateOfficerName = (newName) => {
    setOfficerName(newName);
    localStorage.setItem('veridoc_officer_name', newName);
  };

  const handleToggleWelcome = () => {
    setIsWelcomeOpen((prev) => !prev);
  };

  const handleNavigateToQueue = (docId = null) => {
    setQueueDocId(docId);
    setActiveTab('verification');
  };

  const handleNavigateToApplicant = (targetApplicantId) => {
    setApplicantId(targetApplicantId);
    setActiveTab('verification');
  };

  const handleNavigateToUpload = () => {
    setActiveTab('upload');
  };

  const handleNavigateToWelcome = () => {
    setIsWelcomeOpen(true);
  };

  return (
    <div className="min-h-screen bg-[#F8F9FA] text-[#0F172A] flex flex-col justify-between font-sans">
      
      {/* Top Navigation Bar with Search, Blue Dot & Profile */}
      <Header
        activeTab={activeTab}
        onSelectTab={(tab) => {
          setActiveTab(tab);
          if (tab !== 'queue') setQueueDocId(null);
          if (tab !== 'applicants') setApplicantId(null);
        }}
        officerName={officerName}
        onUpdateOfficerName={handleUpdateOfficerName}
        onNavigateToDocument={handleNavigateToQueue}
        onNavigateToApplicant={handleNavigateToApplicant}
        onToggleWelcome={handleToggleWelcome}
      />

      {/* Slide-over Welcome Desk Drawer */}
      <WelcomeDrawer
        isOpen={isWelcomeOpen}
        onClose={() => setIsWelcomeOpen(false)}
        officerName={officerName}
        onUpdateOfficerName={handleUpdateOfficerName}
        onNavigateTab={(tab) => {
          setActiveTab(tab);
          if (tab !== 'queue') setQueueDocId(null);
          if (tab !== 'applicants') setApplicantId(null);
        }}
      />

      {/* Main Workspace Views */}
      <main className="w-full pt-16 flex-grow">
        {activeTab === 'overview' && (
          <DashboardView
            onNavigateToUpload={handleNavigateToUpload}
            onNavigateToQueue={handleNavigateToQueue}
          />
        )}

        {activeTab === 'repository' && (
          <RepositoryView
            onNavigateToUpload={handleNavigateToUpload}
          />
        )}

        {activeTab === 'upload' && (
          <UploadView
            onNavigateToQueue={handleNavigateToQueue}
          />
        )}

        {(activeTab === 'verification' || activeTab === 'queue' || activeTab === 'applicants') && (
          <VerificationView
            initialApplicantId={applicantId || queueDocId}
            initialDocId={queueDocId}
            officerName={officerName}
          />
        )}

        {activeTab === 'triangulation' && (
          <TriangulationView
            initialApplicantId={applicantId}
            onNavigateToQueue={handleNavigateToQueue}
            onNavigateToUpload={handleNavigateToUpload}
          />
        )}

        {activeTab === 'reports' && (
          <ReportsView />
        )}
      </main>

      {/* Workspace Global Footer */}
      <footer className="w-full bg-white border-t border-[#E2E8F0] py-4 mt-auto">
        <div className="max-w-[1520px] mx-auto px-6 lg:px-8 flex flex-col sm:flex-row items-center justify-between gap-3 text-[12px] text-[#64748B]">
          <div className="flex items-center gap-2">
            <span className="w-2 h-2 rounded-full bg-[#2563EB]"></span>
            <span className="text-[#0F172A] font-bold">VeriDoc AI</span>
            <span>·</span>
            <span>Housing Finance KYC Intelligence Portal</span>
          </div>
          <div>Internal Operations & Verification System · Masked PII Active</div>
        </div>
      </footer>

    </div>
  );
}
