---
name: Veda Housing Trust
colors:
  surface: '#f8f9ff'
  surface-dim: '#cbdbf5'
  surface-bright: '#f8f9ff'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#eff4ff'
  surface-container: '#e5eeff'
  surface-container-high: '#dce9ff'
  surface-container-highest: '#d3e4fe'
  on-surface: '#0b1c30'
  on-surface-variant: '#45464d'
  inverse-surface: '#213145'
  inverse-on-surface: '#eaf1ff'
  outline: '#76777d'
  outline-variant: '#c6c6cd'
  surface-tint: '#565e74'
  primary: '#000000'
  on-primary: '#ffffff'
  primary-container: '#131b2e'
  on-primary-container: '#7c839b'
  inverse-primary: '#bec6e0'
  secondary: '#4b41e1'
  on-secondary: '#ffffff'
  secondary-container: '#645efb'
  on-secondary-container: '#fffbff'
  tertiary: '#000000'
  on-tertiary: '#ffffff'
  tertiary-container: '#002114'
  on-tertiary-container: '#069669'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#dae2fd'
  primary-fixed-dim: '#bec6e0'
  on-primary-fixed: '#131b2e'
  on-primary-fixed-variant: '#3f465c'
  secondary-fixed: '#e2dfff'
  secondary-fixed-dim: '#c3c0ff'
  on-secondary-fixed: '#0f0069'
  on-secondary-fixed-variant: '#3323cc'
  tertiary-fixed: '#85f8c4'
  tertiary-fixed-dim: '#68dba9'
  on-tertiary-fixed: '#002114'
  on-tertiary-fixed-variant: '#005137'
  background: '#f8f9ff'
  on-background: '#0b1c30'
  surface-variant: '#d3e4fe'
typography:
  headline-xl:
    fontFamily: Plus Jakarta Sans
    fontSize: 30px
    fontWeight: '700'
    lineHeight: 38px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Plus Jakarta Sans
    fontSize: 24px
    fontWeight: '600'
    lineHeight: 32px
    letterSpacing: -0.015em
  headline-sm:
    fontFamily: Plus Jakarta Sans
    fontSize: 18px
    fontWeight: '600'
    lineHeight: 26px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Inter
    fontSize: 15px
    fontWeight: '400'
    lineHeight: 24px
    letterSpacing: -0.005em
  body-md:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '400'
    lineHeight: 20px
    letterSpacing: 0em
  body-sm:
    fontFamily: Inter
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
    letterSpacing: 0em
  label-lg:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '600'
    lineHeight: 18px
    letterSpacing: 0.01em
  label-md:
    fontFamily: Inter
    fontSize: 11px
    fontWeight: '600'
    lineHeight: 16px
    letterSpacing: 0.03em
  label-sm:
    fontFamily: Inter
    fontSize: 10px
    fontWeight: '700'
    lineHeight: 14px
    letterSpacing: 0.05em
  data-mono:
    fontFamily: Inter
    fontSize: 13px
    fontWeight: '500'
    lineHeight: 20px
    letterSpacing: 0.02em
rounded:
  sm: 0.125rem
  DEFAULT: 0.25rem
  md: 0.375rem
  lg: 0.5rem
  xl: 0.75rem
  full: 9999px
spacing:
  gutter: 1rem
  margin: 1.5rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 0.75rem
  space-lg: 1.25rem
  space-xl: 2rem
---

## Brand & Style

This design system is tailored for an institutional housing finance underwriting platform. It balances the strict rigor of Indian financial compliance (KYC, CKYC, Aadhaar, PAN verification) with the speed and ergonomics required by high-volume back-office risk officers and loan processors.

### Personality & Tone
- **Institutional Authority & High-Trust:** Uncompromising clarity, absolute precision, and zero visual frivolity. Data presentation must project institutional credibility.
- **Cognitive Ergonomics:** High-density enterprise layout structured to prevent decision fatigue during multi-hour verification workflows.
- **Surgical Precision:** Every border, pill, status badge, and optical baseline aligns cleanly to minimize inspection errors across complex mortgage dossiers.

### Design Style
The system adopts an **Ultra-Clean Minimalist Corporate** aesthetic layered with refined tactile micro-details:
- Crisp 1px structural dividing lines in cool slate neutrals to preserve data boundaries without visual weight.
- Controlled use of micro-elevations (crisp 1px ring borders with faint sub-pixel ambient diffusion) rather than deep spatial shadows.
- Distinct split-pane verification environments: primary source document (pan/zoom viewer) side-by-side with extracted OCR fields, optical confidence indicators, and field-level discrepancy diffing.

## Colors

The palette is engineered around high legibility, strict contrast ratios (exceeding WCAG AAA for core typography), and unambiguous status semantics.

### Core Palettes
- **Canvas & Surface:**
  - Base White: `#FFFFFF` (Primary working cards, verification split-panes, data entry fields)
  - Surface Subdued: `#F8FAFC` (Canvas backdrop, passive gutters, disabled states)
  - Surface Muted: `#F1F5F9` (Table column headers, secondary toolbars, side navigation active wells)
- **Ink & Neutral Hierarchy:**
  - Primary Text: `#0F172A` (Headings, primary data values, verified document fields)
  - Secondary Text: `#334155` (Field labels, metadata rows, secondary navigation)
  - Muted Text: `#64748B` (Placeholders, document timestamps, masking characters)
  - Line / Border: `#E2E8F0` (Card outlines, splitters, cell dividers)
  - Line / Border Subdued: `#F1F5F9` (Internal field separation)
- **Accent & Action:**
  - Indigo Primary Accent: `#4F46E5` (Active focus rings, key CTAs, selected tabs)
  - Indigo Hover: `#4338CA`
  - Indigo Soft Background: `#EEF2FF` (Interactive hover states, active filter chips)

### Verification & Compliance Status Tokens
Status tokens are strictly paired into foreground text/border and tinted surface backgrounds to ensure instant optical identification:
- **Verified / Compliant / Match:**
  - Text & Icon: `#059669`
  - Surface: `#ECFDF5`
  - Border: `#A7F3D0`
- **Under Review / Caution / Low Confidence:**
  - Text & Icon: `#D97706`
  - Surface: `#FFFBEB`
  - Border: `#FDE68A`
- **Rejected / Critical Mismatch / Fraud Flag:**
  - Text & Icon: `#E11D48`
  - Surface: `#FFF1F2`
  - Border: `#FECDD3`
- **AI Extracted / OCR In-Progress / CKYC Sync:**
  - Text & Icon: `#4F46E5`
  - Surface: `#EEF2FF`
  - Border: `#C7D2FE`

## Typography

Typography prioritizes micro-legibility and data distinction across dense tabular interfaces.

### Font Pairing Strategy
- **Headings (Plus Jakarta Sans):** Selected for structural geometry, clean apertures, and modern professional authority across application shell titles and modal headers.
- **Body & Data Grid (Inter):** Utilized for all interface controls, form labels, and data grids. Inter’s open counters and comprehensive diacritics provide clear reading at 11px–13px sizes.

### Numeric & Financial Conventions
- **Tabular Figures:** Always apply OpenType tabular numbers (`tnum`) and slashed zeros (`zero`) on all numbers, application IDs, and Indian rupee amounts.
- **Indian Financial Notation:**
  - Currency values must render using standard Indian grouping (e.g., `₹ 45,50,000` or `₹ 1.25 Cr`).
  - Strict masking patterns:
    - Aadhaar: `XXXX XXXX 1234`
    - PAN: `ABCDE1234F` (Uppercase, monospace tracking)
    - CKYC ID: `14-digit continuous identifier`

## Layout & Spacing

The layout is built for high-throughput enterprise workstations optimized at a primary viewport of 1440×900, with scalable responsiveness between 1280px and 1920px.

### Frame Architecture
- **Persistent Left Navigation:**
  - Fixed width: `260px`
  - Background: `#0F172A` (Slate-900) or clean crisp slate-50 (`#F8FAFC`) with right border `#E2E8F0`.
  - Full viewport height with collapsible nested tree for operational queues (e.g., *Pre-sanction Verification*, *Underwriting Exception Queue*, *Disbursement Lock*).
- **Application Bar (Header):**
  - Height: `64px`
  - Sticks to top of main frame (`z-index: 40`).
  - Houses the context hierarchy: Branch Selector (e.g., `Mumbai - BKC Hub`), Global Search (PAN / Application ID / Mobile No), Verification Mode Switcher, and Underwriter Profile.
- **Primary Content Viewport:**
  - Fluid canvas bounded by minimum width `1024px`.
  - Main operational area adapts via a two-column or split-pane view (50/50 or 40/60) when side-by-side document inspection is triggered.

### Spacing Philosophy
A dense 4px base increment rules the system. Operational components enforce compact paddings (`space-sm` to `space-md`) to ensure critical document dossiers remain fully visible without unnecessary vertical scrolling.

## Elevation & Depth

To avoid visual fatigue, this system avoids dark drop shadows. Depth is achieved via **tonal stratification** and **crisp micro-borders**.

### Surface Tiers
- **Tier 0 (App Canvas):** `#F8FAFC`. The foundational canvas layer behind all containers.
- **Tier 1 (Surface Cards & Panes):** `#FFFFFF` paired with an outline: `1px solid #E2E8F0`.
- **Tier 2 (Popovers, Dropdowns, Flyouts):** `#FFFFFF` with `1px solid #CBD5E1` and ambient shadow: `0 4px 12px -2px rgba(15, 23, 42, 0.08)`.
- **Tier 3 (Verification Modals & Slide-out Dossiers):** `#FFFFFF` with backdrop overlay `#0F172A` at 40% opacity, bordered by `#94A3B8`, with elevation shadow: `0 12px 24px -4px rgba(15, 23, 42, 0.12)`.

### Border Discipline
Cards and content panels do not float; they dock using clean 1px borders. When a card contains an active review state, the border subtly shifts to the semantic status color (e.g., emerald for matched fields, rose for OCR discrepancies).

## Shapes

The shape system adopts a **Soft (Level 1)** structure.

- **Base Elements (Buttons, Inputs, Table Cells):** `0.25rem` (4px). Provides a structured, sharp fintech silhouette that feels serious and precise.
- **Medium Containers (Cards, Inspection Panels, Inner Wells):** `0.5rem` (8px). Softens larger perimeter edges without wasting horizontal visual real estate.
- **Floating Modals & Dossier Overlays:** `0.75rem` (12px).
- **Status Badges & Micro Chips:** Pill geometry (`9999px`) is reserved solely for contextual status indicators (Approved, Discrepancy, Processing) to clearly delineate metadata badges from interactive rectangular form elements.

## Components

### 1. Buttons & Actions
- **Primary Action (Approve / Verify):** Solid `#0F172A` fill with `#FFFFFF` text, or verified state in `#059669`. Height: 36px. Font: 13px weight 600. Focus ring: 2px offset with `#4F46E5`.
- **Secondary Action (Request Resubmission / Flag):** Outlined with `1px solid #CBD5E1`, surface `#FFFFFF`, text `#334155`. Hover state: `#F1F5F9`.
- **Destructive Action (Reject Dossier):** Surface `#FFF1F2`, border `1px solid #FECDD3`, text `#E11D48`.
- **Icon Buttons (Zoom, Rotate, Invert Scan):** 32×32px square, border `1px solid #E2E8F0`, surface `#FFFFFF`, icon color `#475569`.

### 2. Status Badges & Verification Chips
- Displayed as micro pills (`border-radius: 9999px`) with padding `2px 8px`.
- Composed of an optical 6px dot indicator + label in `label-md` (11px, weight 600, uppercase tracking).
- Pre-configured color pairs:
  - *Verified*: `#ECFDF5` background, `#059669` dot and text.
  - *OCR Discrepancy*: `#FFF1F2` background, `#E11D48` dot and text.
  - *Manual Review Needed*: `#FFFBEB` background, `#D97706` dot and text.
  - *Fetching CKYC*: `#EEF2FF` background, `#4F46E5` dot and text.

### 3. Split-Pane Document Verification Workspace
- **Left Pane (Original Scan Viewer):** Dedicated preview frame supporting PDF/TIFF/JPEG rendering with embedded HUD controls (Pan, Zoom, 90° Rotate, Contrast Adjustment).
- **Right Pane (Extracted Data & Diff Inspector):** 
  - Each extracted field (e.g., *Borrower Full Name*, *Father's Name*, *DOB*, *Aadhaar Number*) renders in an input-like box with an automatic confidence meter (e.g., `98.4% Match`).
  - Fields with discrepancies render alongside the source OCR text in strike-through red font against the normalized CKYC registry value.

### 4. Form Fields & Data Inputs
- **Base Height:** 36px for dense single-line inputs.
- **Borders & Background:** Surface `#FFFFFF`, border `1px solid #CBD5E1`. On focus: `border-color: #4F46E5`, outline: `2px solid rgba(79, 70, 229, 0.15)`.
- **Masked Inputs:** Aadhaar and PAN fields feature mono-styled inputs with an inline unmask toggle (`Show / Hide` eye icon).

### 5. Data Tables (Underwriting Queue)
- **Header:** Height 36px, background `#F8FAFC`, uppercase 11px font weight 700, tracking 0.05em, text `#475569`.
- **Row:** Height 44px, alternating hover background `#F8FAFC`, bottom border `1px solid #F1F5F9`.
- **Cells:** Tabular numbers aligned right for loan ticket sizes (`₹ 24.50 Lakhs`), left-aligned for applicant details, centered for verification statuses.