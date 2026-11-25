---
name: Monochrome Editorial
colors:
  surface: '#f9f9f7'
  surface-dim: '#dadad8'
  surface-bright: '#f9f9f7'
  surface-container-lowest: '#ffffff'
  surface-container-low: '#f4f4f2'
  surface-container: '#eeeeec'
  surface-container-high: '#e8e8e6'
  surface-container-highest: '#e2e2e1'
  on-surface: '#1a1c1b'
  on-surface-variant: '#444748'
  inverse-surface: '#2f3130'
  inverse-on-surface: '#f1f1ef'
  outline: '#747878'
  outline-variant: '#c4c7c7'
  surface-tint: '#5f5e5e'
  primary: '#000000'
  on-primary: '#ffffff'
  primary-container: '#1c1b1b'
  on-primary-container: '#858383'
  inverse-primary: '#c8c6c5'
  secondary: '#5f5e5e'
  on-secondary: '#ffffff'
  secondary-container: '#e4e2e1'
  on-secondary-container: '#656464'
  tertiary: '#000000'
  on-tertiary: '#ffffff'
  tertiary-container: '#1a1c1c'
  on-tertiary-container: '#848484'
  error: '#ba1a1a'
  on-error: '#ffffff'
  error-container: '#ffdad6'
  on-error-container: '#93000a'
  primary-fixed: '#e5e2e1'
  primary-fixed-dim: '#c8c6c5'
  on-primary-fixed: '#1c1b1b'
  on-primary-fixed-variant: '#474646'
  secondary-fixed: '#e4e2e1'
  secondary-fixed-dim: '#c8c6c5'
  on-secondary-fixed: '#1b1c1c'
  on-secondary-fixed-variant: '#474746'
  tertiary-fixed: '#e3e2e2'
  tertiary-fixed-dim: '#c7c6c6'
  on-tertiary-fixed: '#1a1c1c'
  on-tertiary-fixed-variant: '#464747'
  background: '#f9f9f7'
  on-background: '#1a1c1b'
  surface-variant: '#e2e2e1'
  pure-white: '#FFFFFF'
  surface-offwhite: '#F8F8F7'
  border-hairline: '#EEEEEC'
  muted-grey: '#929292'
  charcoal: '#242424'
  deep-black: '#111111'
typography:
  display:
    fontFamily: Newsreader
    fontSize: 56px
    fontWeight: '400'
    lineHeight: 64px
    letterSpacing: -0.03em
  display-mobile:
    fontFamily: Newsreader
    fontSize: 36px
    fontWeight: '400'
    lineHeight: 42px
    letterSpacing: -0.02em
  headline-lg:
    fontFamily: Newsreader
    fontSize: 40px
    fontWeight: '400'
    lineHeight: 48px
    letterSpacing: -0.02em
  headline-lg-mobile:
    fontFamily: Newsreader
    fontSize: 28px
    fontWeight: '400'
    lineHeight: 34px
    letterSpacing: -0.015em
  headline-md:
    fontFamily: Newsreader
    fontSize: 28px
    fontWeight: '400'
    lineHeight: 36px
    letterSpacing: -0.01em
  headline-sm:
    fontFamily: Work Sans
    fontSize: 20px
    fontWeight: '500'
    lineHeight: 28px
    letterSpacing: -0.01em
  body-lg:
    fontFamily: Work Sans
    fontSize: 16px
    fontWeight: '400'
    lineHeight: 26px
    letterSpacing: -0.005em
  body-md:
    fontFamily: Work Sans
    fontSize: 14px
    fontWeight: '400'
    lineHeight: 22px
    letterSpacing: 0em
  body-sm:
    fontFamily: Work Sans
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 18px
    letterSpacing: 0em
  label-md:
    fontFamily: Work Sans
    fontSize: 12px
    fontWeight: '500'
    lineHeight: 16px
    letterSpacing: 0.06em
  label-sm:
    fontFamily: Work Sans
    fontSize: 11px
    fontWeight: '500'
    lineHeight: 14px
    letterSpacing: 0.08em
  code:
    fontFamily: Courier Prime
    fontSize: 12px
    fontWeight: '400'
    lineHeight: 16px
    letterSpacing: 0em
spacing:
  gutter: 1.5rem
  gutter-mobile: 1rem
  margin: 3rem
  margin-mobile: 1.25rem
  space-xs: 0.25rem
  space-sm: 0.5rem
  space-md: 1rem
  space-lg: 1.5rem
  space-xl: 2.5rem
---

## Brand & Style

This design system embodies an uncompromising minimalist editorial aesthetic rooted in contemporary Swiss typography, architectural discipline, and high-fashion publishing. The experience feels literary, authoritative, quiet, and hyper-focused. It eliminates all decorative distractions—rejecting saturated accents, gradients, glass effects, and elevated drop shadows—in favor of structural precision, hairline dividers, meticulous negative space, and commanding typographic hierarchy.

The target audience includes design-literate professionals, curators, archivists, researchers, and editorial creators who value density control, clarity, and utilitarian elegance. The interface should evoke a calm, gallery-like poise: confident, quiet luxury that lets content breathe without competitive chrome or synthetic flair.

## Colors

The palette is strictly achromatic and neutral. No chromatic hues, blurs, or gradient blends are permitted. 

- **Pure White (`#FFFFFF`)**: Primary background for high-focus content panels, input fields, and pristine reading zones.
- **Surface Off-white (`#F8F8F7`)**: Base canvas tint and secondary container fill providing subtle tonal separation without heavy borders.
- **Border Hairline / Light Grey (`#EEEEEC`)**: Structural separator used for crisp 1px borders, table rows, and grid line dividers.
- **Medium Grey (`#929292`)**: Tertiary metadata, understated label captions, timestamps, inactive icons, and muted status indicators.
- **Charcoal (`#242424`)**: High-contrast secondary typography, hover states, subheadings, and secondary interactive borders.
- **Black (`#111111`)**: Absolute anchor used for primary headlines, active text, sharp foreground accents, and solid micro-buttons.

## Typography

The type system pairs the editorial elegance of **Newsreader** for literary display and headlines with the precise, functional neutrality of **Work Sans** for UI prose, tables, and functional controls.

- **Headlines & Display**: Rendered in Newsreader Regular with negative tracking to evoke fine print culture and editorial mastheads. Maintain tight line-heights without clipping descenders.
- **Body & Interface**: Set in Work Sans with neutral tracking and balanced leading to maintain high legibility across dense listings and long-form reading.
- **Labels & Micro-data**: Always rendered in uppercase with deliberate tracking (`0.06em` to `0.08em`) to delineate operational metrics, column keys, and state markers from narrative text.
- **Monospaced Data**: Use Courier Prime for indexes, reference keys, financial markers, and tabular counters to ground the editorial voice with utilitarian honesty.

## Layout & Spacing

The layout is built upon an architectural grid with uncompromising horizontal and vertical alignment:

- **Desktop (1024px+)**: A 12-column grid bounded by 3rem (`48px`) margins and 1.5rem (`24px`) gutters. Editorial spreads, full-bleed hairline dividing lines, and asymmetrical column layouts (e.g., 4-col metadata index adjacent to an 8-col reading area).
- **Tablet (768px - 1023px)**: An 8-column layout with 2rem (`32px`) margins and 1.25rem (`20px`) gutters.
- **Mobile (< 768px)**: A 4-column layout with 1.25rem (`20px`) margins and 1rem (`16px`) gutters. Columns collapse linearly, and hairline horizontal rules visually partition discrete modules.

Vertical spacing strictly respects baseline increments of `4px` and `8px`. Section padding uses deliberate, generous rhythm (`space-xl` and higher) to preserve white space and avoid visual crowding.

## Elevation & Depth

This design system avoids all drop shadows, synthetic blurs, and skeuomorphic bevels. Hierarchy is established entirely through planar flat techniques:

1. **Hairline Outlines**: Boundaries are denoted by strict 1px solid borders in `#EEEEEC`. Grouped modules share internal borders without overlapping double lines (`border-collapse` philosophy).
2. **Subtle Tonal Stratification**: Background shifts between `#FFFFFF` (interactive elements, canvas panes) and `#F8F8F7` (surrounding frame, secondary zones) designate layered depth without elevation.
3. **Contrast Stacking**: Deep Charcoal (`#242424`) and Black (`#111111`) are reserved for active or prioritized focal points, pulling them naturally to the foreground through luminance contrast alone.

## Shapes

The geometry is unapologetically sharp (`0px` radius everywhere). Buttons, inputs, tags, modal drawers, and tabular cards terminate in precise 90-degree right angles. 

The sole exception to the rectangular rule is functional circular indicators: status dot badges and micro-radio controls, which are drawn as pure circles to contrast with the razor-sharp grid architecture.

## Components

### Buttons
- **Primary**: Solid Black (`#111111`) background, Pure White (`#FFFFFF`) text, sharp corners, zero border. Hover shifts background to Charcoal (`#242424`). Micro-directional arrows (`→`, `↗`) follow text labels with a 4px gap.
- **Secondary / Ghost**: Pure White or transparent background with a 1px solid `#EEEEEC` border and `#111111` text. On hover, border shifts to `#111111` with no motion translation.
- **Icon / Micro Actions**: Borderless, displaying single hairline glyphs or small directional arrows. Active states reveal a solid 1px `#111111` bottom underline.

### Chips & Badges
- **Status Indicators**: Minimal, unbordered capsules with an inline 6px solid dot (`#111111` for active/ready, `#929292` for inactive/draft). Typography uses `label-sm` uppercase.
- **Filter Tags**: 1px `#EEEEEC` frame, `#F8F8F7` fill, and `#242424` text. Selected state inverts to `#111111` fill and `#FFFFFF` text.

### Form Inputs & Checkboxes
- **Text Inputs**: Crisp bottom border only (1px solid `#EEEEEC`) or full 1px box with `#FFFFFF` fill. Focus changes border to `#111111` without glow or shadow. Placeholder text is `#929292`.
- **Checkboxes**: 14x14px sharp square box with 1px `#EEEEEC` border. Checked state fills box with `#111111` and displays a crisp white 1px vector check.
- **Radio Buttons**: 14x14px circle with 1px `#EEEEEC` ring; selected state shows an internal 6px concentric solid circle in `#111111`.

### Cards & Panels
- **Modular Cards**: Flat surfaces (`#FFFFFF` or `#F8F8F7`) enclosed by a 1px `#EEEEEC` border. No drop shadows. Hover triggers no vertical lift; instead, the border transitions cleanly from `#EEEEEC` to `#242424`.
- **Dividers**: Always 1px solid `#EEEEEC`, spanning full grid width or docking directly to section margins.

### Tables & Data Lists
- **Tabular Data**: Unpadded exterior container. Horizontal row separators in 1px `#EEEEEC`. Table header uses `label-sm` in `#929292` with uppercase tracking. Numerical and date columns render in Courier Prime right-aligned. Hovering a row applies a `#F8F8F7` tint with a subtle `→` revealed on the right edge.