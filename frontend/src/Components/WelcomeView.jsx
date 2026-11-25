import React, { useState, useEffect } from 'react';
import { api } from '../api';

export default function WelcomeView({ onEnterWorkspace, officerName = 'Arjun Mehta' }) {
  const [showModal, setShowModal] = useState(false);
  const [scrollProgress, setScrollProgress] = useState(0);
  const [isSeeding, setIsSeeding] = useState(false);
  const [seedNotice, setSeedNotice] = useState(null);

  useEffect(() => {
    const handleScroll = () => {
      const winScroll = document.body.scrollTop || document.documentElement.scrollTop;
      const height = document.documentElement.scrollHeight - document.documentElement.clientHeight;
      const scrolled = height > 0 ? (winScroll / height) * 100 : 0;
      setScrollProgress(scrolled);
    };

    window.addEventListener('scroll', handleScroll);
    return () => window.removeEventListener('scroll', handleScroll);
  }, []);

  const handleResetDemoData = async () => {
    setIsSeeding(true);
    setSeedNotice(null);
    try {
      const res = await api.resetDemo();
      setSeedNotice({ type: 'success', text: res.message || 'Synthetic demo dataset reset successfully.' });
    } catch (err) {
      setSeedNotice({ type: 'error', text: err.message || 'Failed to reset demonstration dataset.' });
    } finally {
      setIsSeeding(false);
    }
  };

  const scrollToTop = () => {
    window.scrollTo({ top: 0, behavior: 'smooth' });
  };

  return (
    <div className="bg-[#F8F8F7] text-[#252525] font-sans antialiased min-h-screen flex flex-col justify-between selection:bg-[#111111] selection:text-white">
      
      {/* Top Horizontal Scroll Progress Bar */}
      <div className="fixed top-0 left-0 right-0 z-50 h-[2px] bg-transparent">
        <div
          className="h-full bg-[#527A9E] transition-all duration-75"
          style={{ width: `${scrollProgress}%` }}
        />
      </div>

      {/* Top Minimal Horizontal Header */}
      <header className="sticky top-0 z-40 bg-[#F8F8F7]/95 backdrop-blur-md border-b border-[#EEEEEC]">
        <div className="max-w-[1440px] mx-auto px-6 sm:px-8 lg:px-16 h-16 flex items-center justify-between">
          <div className="flex items-center space-x-3 group cursor-pointer" onClick={scrollToTop}>
            <span className="w-2 h-2 rounded-full bg-[#527A9E] transition-transform duration-200 group-hover:scale-125" />
            <span className="text-[14px] sm:text-[15px] font-sans font-medium tracking-wide uppercase text-[#111111]">
              DOCUMENT VERIFICATION SYSTEM
            </span>
          </div>

          <div className="flex items-center space-x-4 sm:space-x-6">
            <button
              onClick={() => setShowModal(true)}
              className="text-[14px] sm:text-[15px] font-sans text-[#767676] hover:text-[#527A9E] tracking-normal transition-colors focus:outline-none"
            >
              About the system
            </button>
            <div className="h-3.5 w-px bg-[#EEEEEC] hidden sm:block" />
            <div className="hidden sm:flex items-center space-x-2 text-[14px] sm:text-[15px] font-sans text-[#767676]">
              <span className="text-[#111111] font-normal">{officerName}</span>
              <span>·</span>
              <span>Review Officer</span>
            </div>
            <button
              onClick={onEnterWorkspace}
              className="inline-flex items-center space-x-2 px-4 py-1.5 bg-[#111111] text-white text-[13px] font-medium hover:bg-[#527A9E] transition-colors shadow-xs"
            >
              <span>Workspace</span>
              <span>↗</span>
            </button>
          </div>
        </div>
      </header>

      {/* Main Content Container */}
      <main className="flex-grow">
        
        {/* Section 1: Hero Section */}
        <section className="relative pt-16 pb-12 lg:pt-24 lg:pb-16 px-6 sm:px-8 lg:px-16 max-w-[1440px] mx-auto flex flex-col items-center text-center">
          <div className="inline-flex items-center space-x-2 mb-6">
            <span className="w-1.5 h-1.5 rounded-full bg-[#527A9E]" />
            <span className="text-[13px] font-sans font-medium uppercase tracking-widest text-[#527A9E]">
              OPERATIONAL VERIFICATION DESK
            </span>
          </div>

          <h1 className="font-serif text-4xl sm:text-6xl md:text-7xl lg:text-[84px] font-normal text-[#111111] tracking-tight leading-[1.06] max-w-4xl mx-auto mb-6">
            A clearer way to<br />verify documents.
          </h1>

          <p className="text-[17px] sm:text-[19px] text-[#767676] font-normal max-w-xl mx-auto mb-10 leading-relaxed font-sans">
            Upload, extract and review customer documents in one place.
          </p>

          <div className="flex flex-col sm:flex-row items-center gap-4">
            <button
              onClick={onEnterWorkspace}
              className="inline-flex items-center space-x-3 px-8 py-3.5 bg-[#111111] text-white text-[15px] font-medium tracking-wide rounded-none border border-[#111111] hover:bg-[#527A9E] hover:border-[#527A9E] active:scale-[0.99] transition-all duration-200 shadow-sm group"
            >
              <span>Enter workspace</span>
              <span className="text-[15px] inline-block transition-transform duration-200 text-[#527A9E] group-hover:text-white group-hover:translate-x-1 group-hover:-translate-y-0.5">
                ↗
              </span>
            </button>

            <button
              onClick={() => setShowModal(true)}
              className="inline-flex items-center space-x-2 px-6 py-3.5 bg-white text-[#252525] text-[15px] font-medium border border-[#EEEEEC] hover:border-[#527A9E] hover:text-[#527A9E] transition-colors"
            >
              <span>System Specifications</span>
            </button>
          </div>
        </section>

        {/* Hairline Separator */}
        <div className="max-w-[1200px] mx-auto px-6 sm:px-8 lg:px-16">
          <div className="h-px w-full bg-[#EEEEEC]" />
        </div>

        {/* Section 2: Process Section (Upload → Extract → Verify) */}
        <section className="py-16 lg:py-20 px-6 sm:px-8 lg:px-16 max-w-[1440px] mx-auto">
          <div className="max-w-[1200px] mx-auto">
            <div className="flex items-center justify-between mb-12 pb-3.5 border-b border-[#EEEEEC]">
              <div className="flex items-center space-x-2">
                <span className="w-1.5 h-1.5 rounded-full bg-[#527A9E] inline-block" />
                <span className="text-[13px] font-sans font-medium uppercase tracking-widest text-[#527A9E]">
                  CORE FLOW
                </span>
              </div>
              <span className="text-[13px] font-sans text-[#767676] flex items-center space-x-1.5">
                <span>Tri-Phase Verification</span>
              </span>
            </div>

            <div className="grid grid-cols-1 md:grid-cols-3 gap-8 lg:gap-12 relative">
              {/* STAGE 01 */}
              <div className="group flex flex-col justify-between pt-1 pb-4 hover:translate-y-[-2px] transition-transform duration-200">
                <div>
                  <div className="flex items-center justify-between pb-3.5 border-b border-[#EEEEEC] transition-colors duration-200 group-hover:border-[#527A9E]">
                    <span className="text-[13px] font-sans font-medium text-[#527A9E] uppercase tracking-widest">
                      STAGE 01
                    </span>
                    <div className="flex items-center space-x-1.5">
                      <span className="text-[13px] font-sans text-[#767676] group-hover:text-[#527A9E] transition-colors">
                        Intake
                      </span>
                      <span className="text-[#527A9E] text-[15px] font-sans transition-transform duration-300 group-hover:translate-x-1">
                        →
                      </span>
                    </div>
                  </div>
                  <div className="mt-6 flex items-baseline justify-between">
                    <h2 className="font-serif text-[36px] text-[#111111] font-normal tracking-tight">Upload</h2>
                  </div>
                  <p className="mt-3.5 text-[16px] text-[#767676] leading-relaxed font-sans">
                    Consolidate single or batch customer files into a unified dossier with automatic format standardisation.
                  </p>
                </div>
                <div className="mt-6 pt-3 border-t border-[#EEEEEC]/80 flex items-center justify-between text-[13px] font-sans text-[#767676]">
                  <span>Primary intake</span>
                  <span className="font-medium text-[#252525]">Step 1 of 3</span>
                </div>
              </div>

              {/* STAGE 02 */}
              <div className="group flex flex-col justify-between pt-1 pb-4 hover:translate-y-[-2px] transition-transform duration-200">
                <div>
                  <div className="flex items-center justify-between pb-3.5 border-b border-[#EEEEEC] transition-colors duration-200 group-hover:border-[#527A9E]">
                    <span className="text-[13px] font-sans font-medium text-[#527A9E] uppercase tracking-widest">
                      STAGE 02
                    </span>
                    <div className="flex items-center space-x-1.5">
                      <span className="text-[13px] font-sans text-[#767676] group-hover:text-[#527A9E] transition-colors">
                        Structure
                      </span>
                      <span className="text-[#527A9E] text-[15px] font-sans transition-transform duration-300 group-hover:translate-x-1">
                        →
                      </span>
                    </div>
                  </div>
                  <div className="mt-6 flex items-baseline justify-between">
                    <h2 className="font-serif text-[36px] text-[#111111] font-normal tracking-tight">Extract</h2>
                  </div>
                  <p className="mt-3.5 text-[16px] text-[#767676] leading-relaxed font-sans">
                    Automated extraction of names, registry IDs and transaction records into structured field comparisons.
                  </p>
                </div>
                <div className="mt-6 pt-3 border-t border-[#EEEEEC]/80 flex items-center justify-between text-[13px] font-sans text-[#767676]">
                  <span>Machine parsing</span>
                  <span className="font-medium text-[#252525]">Step 2 of 3</span>
                </div>
              </div>

              {/* STAGE 03 */}
              <div className="group flex flex-col justify-between pt-1 pb-4 hover:translate-y-[-2px] transition-transform duration-200">
                <div>
                  <div className="flex items-center justify-between pb-3.5 border-b border-[#EEEEEC] transition-colors duration-200 group-hover:border-[#527A9E]">
                    <span className="text-[13px] font-sans font-medium text-[#527A9E] uppercase tracking-widest">
                      STAGE 03
                    </span>
                    <div className="flex items-center space-x-1.5">
                      <span className="text-[13px] font-sans text-[#767676] group-hover:text-[#527A9E] transition-colors">
                        Sign-off
                      </span>
                      <span className="text-[#527A9E] text-[15px] font-sans">✓</span>
                    </div>
                  </div>
                  <div className="mt-6 flex items-baseline justify-between">
                    <h2 className="font-serif text-[36px] text-[#111111] font-normal tracking-tight">Verify</h2>
                  </div>
                  <p className="mt-3.5 text-[16px] text-[#767676] leading-relaxed font-sans">
                    Side-by-side officer review, field-level reconciliation, and immediate validation against authoritative sources.
                  </p>
                </div>
                <div className="mt-6 pt-3 border-t border-[#EEEEEC]/80 flex items-center justify-between text-[13px] font-sans text-[#767676]">
                  <span>Officer clearance</span>
                  <span className="font-medium text-[#252525]">Step 3 of 3</span>
                </div>
              </div>
            </div>

            <div className="mt-16 mb-14 h-px w-full bg-[#EEEEEC]" />

            {/* Closing Workspace CTA */}
            <div className="max-w-xl mx-auto flex flex-col items-center text-center pb-6">
              <span className="text-[13px] font-sans font-medium uppercase tracking-widest text-[#527A9E] mb-3">
                Workspace Access
              </span>
              <h2 className="font-serif text-3xl md:text-4xl text-[#111111] font-normal tracking-tight mb-6">
                Ready to begin review?
              </h2>
              <button
                onClick={onEnterWorkspace}
                className="inline-flex items-center space-x-3 px-8 py-3.5 bg-[#111111] text-white text-[15px] font-medium tracking-wide rounded-none border border-[#111111] hover:bg-[#527A9E] hover:border-[#527A9E] active:scale-[0.99] transition-all duration-200 shadow-sm group"
              >
                <span>Enter workspace</span>
                <span className="text-[15px] inline-block transition-transform duration-200 text-[#527A9E] group-hover:text-white group-hover:translate-x-1 group-hover:-translate-y-0.5">
                  ↗
                </span>
              </button>
            </div>

          </div>
        </section>

      </main>

      {/* Minimal Restrained Footer */}
      <footer className="border-t border-[#EEEEEC] bg-[#F8F8F7] py-6 px-6 sm:px-8 lg:px-16">
        <div className="max-w-[1440px] mx-auto flex flex-col md:flex-row items-center justify-between text-[14px] text-[#767676] font-sans space-y-3 md:space-y-0">
          <div className="flex items-center space-x-2">
            <span className="w-1.5 h-1.5 rounded-full bg-[#527A9E]" />
            <span className="text-[#252525] font-medium">DOCUMENT VERIFICATION SYSTEM</span>
            <span>·</span>
            <span>Internal Operations</span>
          </div>
          <div>
            <span>Authorized Personnel Only</span>
          </div>
          <div>
            <button
              onClick={scrollToTop}
              className="hover:text-[#111111] transition-colors flex items-center space-x-1"
            >
              <span>Top</span>
              <span className="text-[#527A9E]">↑</span>
            </button>
          </div>
        </div>
      </footer>

      {/* System Info Modal Dialog */}
      {showModal && (
        <div className="fixed inset-0 z-50 flex items-center justify-center p-4 bg-black/40 backdrop-blur-xs animate-in fade-in">
          <div className="bg-white border border-[#E2E2DF] max-w-lg w-full p-8 shadow-2xl space-y-6">
            <div className="flex items-baseline justify-between pb-4 border-b border-[#EEEEEC]">
              <div className="flex items-center space-x-2">
                <span className="w-2 h-2 rounded-full bg-[#527A9E]" />
                <h3 className="font-serif text-2xl text-[#111111] font-normal">About the System</h3>
              </div>
              <button
                onClick={() => setShowModal(false)}
                className="text-[12px] font-sans text-[#767676] hover:text-[#111111] uppercase tracking-wider focus:outline-none"
              >
                Close [esc]
              </button>
            </div>

            <div className="space-y-4 text-[14px] text-[#252525] font-sans leading-relaxed">
              <p>
                The <strong>Document Verification System</strong> is an internal processing desk for KYC document intelligence,
                extracting and reviewing applicant credentials across PAN, Aadhaar, Passport, Voter ID and Driving Licence records.
              </p>

              <div className="text-[13px] font-sans text-[#767676] pt-3 border-t border-[#EEEEEC] space-y-2">
                <div><strong className="text-[#111111] font-medium">Architecture:</strong> Flask REST Backend + React Vite Client + SQLite</div>
                <div><strong className="text-[#111111] font-medium">Workflow:</strong> Stage 01 (Upload) → Stage 02 (Extract) → Stage 03 (Verify)</div>
                <div><strong className="text-[#111111] font-medium">Security Boundary:</strong> Synthetic test data with masked PII active</div>
                <div><strong className="text-[#111111] font-medium">Assigned Officer:</strong> {officerName}</div>
              </div>

              {/* Seed Notice */}
              {seedNotice && (
                <div className={`p-3 text-[13px] border rounded ${
                  seedNotice.type === 'success' ? 'bg-emerald-50 border-emerald-200 text-emerald-800' : 'bg-red-50 border-red-200 text-red-800'
                }`}>
                  {seedNotice.text}
                </div>
              )}
            </div>

            <div className="pt-4 border-t border-[#EEEEEC] flex items-center justify-between gap-3">
              <button
                onClick={handleResetDemoData}
                disabled={isSeeding}
                className="text-[13px] font-medium text-[#527A9E] hover:underline disabled:opacity-50"
              >
                {isSeeding ? 'Resetting Data...' : '↻ Reload Synthetic Demo Dataset'}
              </button>

              <div className="flex items-center gap-2">
                <button
                  onClick={() => setShowModal(false)}
                  className="px-4 py-2 border border-[#EEEEEC] text-[#252525] text-[13px] hover:bg-[#F8F8F7]"
                >
                  Dismiss
                </button>
                <button
                  onClick={() => {
                    setShowModal(false);
                    onEnterWorkspace();
                  }}
                  className="inline-flex items-center space-x-2 px-5 py-2 bg-[#111111] text-white text-[13px] font-medium hover:bg-[#527A9E] transition-colors"
                >
                  <span>Enter Workspace</span>
                  <span>↗</span>
                </button>
              </div>
            </div>

          </div>
        </div>
      )}

    </div>
  );
}
