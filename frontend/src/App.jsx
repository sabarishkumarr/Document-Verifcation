import React, { useState, useEffect } from 'react';
import Header from './Components/Header';
import WelcomeView from './Components/WelcomeView';
import DashboardView from './Components/DashboardView';
import UploadView from './Components/UploadView';
import VerificationQueueView from './Components/VerificationQueueView';
import ApplicantsView from './Components/ApplicantsView';
import ReportsView from './Components/ReportsView';

export default function App() {
  // Default landing view is 'welcome' as requested by Stitch specifications
  const [activeTab, setActiveTab] = useState('welcome');
  const [queueDocId, setQueueDocId] = useState(null);
  const [applicantId, setApplicantId] = useState(null);

  // Review Officer name persisted in localStorage
  const [officerName, setOfficerName] = useState(() => {
    return localStorage.getItem('veridoc_officer_name') || 'Arjun Mehta';
  });

  const handleUpdateOfficerName = (newName) => {
    setOfficerName(newName);
    localStorage.setItem('veridoc_officer_name', newName);
  };

  const handleNavigateToQueue = (docId = null) => {
    setQueueDocId(docId);
    setActiveTab('queue');
  };

  const handleNavigateToApplicant = (targetApplicantId) => {
    setApplicantId(targetApplicantId);
    setActiveTab('applicants');
  };

  const handleNavigateToUpload = () => {
    setActiveTab('upload');
  };

  const handleNavigateToWelcome = () => {
    setActiveTab('welcome');
  };

  // 1. Initial Landing Page: Stitch Welcome Component
  if (activeTab === 'welcome') {
    return (
      <WelcomeView
        officerName={officerName}
        onEnterWorkspace={() => setActiveTab('overview')}
      />
    );
  }

  // 2. Operational KYC Intelligence Workspace
  return (
    <div className="min-h-screen bg-[#F8F9FA] text-[#0F172A] flex flex-col justify-between font-sans">
      
      {/* Top Navigation Bar with Search & Profile */}
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
        onNavigateToWelcome={handleNavigateToWelcome}
      />

      {/* Main Workspace Views */}
      <main className="w-full pt-16 flex-grow">
        {activeTab === 'overview' && (
          <DashboardView
            onNavigateToUpload={handleNavigateToUpload}
            onNavigateToQueue={handleNavigateToQueue}
          />
        )}

        {activeTab === 'upload' && (
          <UploadView
            onNavigateToQueue={handleNavigateToQueue}
          />
        )}

        {activeTab === 'queue' && (
          <VerificationQueueView
            initialApplicantId={queueDocId}
            initialDocId={queueDocId}
            officerName={officerName}
          />
        )}

        {activeTab === 'applicants' && (
          <ApplicantsView
            initialApplicantId={applicantId}
            onNavigateToQueue={handleNavigateToQueue}
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
