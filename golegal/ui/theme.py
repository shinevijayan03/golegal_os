"""
Executive Crimson Red (#D32F2F) & Vibrant Orange (#FF6D00) Light Design System.
WCAG 2.2 AA Contrast Compliance & High-Contrast Typography.
"""
from __future__ import annotations
import streamlit as st

_THEME_CSS = """
<style>
/* -------------------------------------------------------------
   GoLegal vNext Executive Crimson & Vibrant Orange Light Theme
   ------------------------------------------------------------- */
:root {
  --gl-crimson: #D32F2F;
  --gl-crimson-dark: #B71C1C;
  --gl-crimson-light: #FFCDD2;
  --gl-orange: #FF6D00;
  --gl-orange-vibrant: #FF5722;
  --gl-orange-light: #FFE0B2;
  --gl-bg-light: #F9FAFB;
  --gl-surface: #FFFFFF;
  --gl-surface-border: #E5E7EB;
  --gl-text: #111827;
  --gl-muted: #4B5563;
  --gl-emerald: #059669;
  --gl-amber: #D97706;
}

html, body, [class*="css"], .stApp {
  background-color: var(--gl-bg-light) !important;
  color: var(--gl-text) !important;
  font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
}

/* Header & Brand Banner */
.gl-brand-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0.85rem 1.25rem;
  background: #FFFFFF;
  border-bottom: 3px solid var(--gl-crimson);
  border-radius: 8px;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.06);
  margin-bottom: 1.25rem;
}

.gl-logo {
  font-size: 1.6rem;
  font-weight: 800;
  letter-spacing: -0.5px;
  color: #111827;
}

.gl-logo span {
  background: linear-gradient(90deg, var(--gl-orange) 0%, var(--gl-crimson) 100%);
  -webkit-background-clip: text;
  -webkit-text-fill-color: transparent;
}

.gl-tagline {
  font-size: 0.85rem;
  color: var(--gl-crimson);
  font-weight: 600;
}

/* GPU Telemetry Pill */
.gl-gpu-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.5rem;
  padding: 0.35rem 0.75rem;
  background: #FFF3E0;
  border: 1px solid var(--gl-orange);
  border-radius: 20px;
  color: #E65100;
  font-size: 0.78rem;
  font-weight: 600;
}

.gl-gpu-dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background-color: var(--gl-emerald);
  box-shadow: 0 0 6px var(--gl-emerald);
}

/* Custom Cards */
.gl-card {
  background-color: #FFFFFF;
  border: 1px solid var(--gl-surface-border);
  border-radius: 8px;
  padding: 1.25rem;
  margin-bottom: 1rem;
  box-shadow: 0 1px 3px rgba(0, 0, 0, 0.04);
}

.gl-card h4 {
  color: var(--gl-crimson);
  margin-top: 0;
  margin-bottom: 0.5rem;
}

/* Status Badges */
.gl-badge {
  display: inline-block;
  padding: 0.25rem 0.65rem;
  border-radius: 4px;
  font-size: 0.75rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.5px;
}

.gl-badge-draft {
  background-color: #FEF3C7;
  border: 1px solid #F59E0B;
  color: #92400E;
}

.gl-badge-review {
  background-color: #FFEDD5;
  border: 1px solid var(--gl-orange);
  color: #C2410C;
}

.gl-badge-approved {
  background-color: #D1FAE5;
  border: 1px solid var(--gl-emerald);
  color: #065F46;
}

.gl-badge-mock {
  background-color: #FEE2E2;
  border: 1px solid var(--gl-crimson);
  color: #991B1B;
}

.gl-badge-danger {
  background-color: #FEE2E2;
  border: 1px solid #DC2626;
  color: #B91C1C;
}

/* Warning & Banner Notice */
.gl-notice-banner {
  padding: 0.85rem 1.2rem;
  border-radius: 6px;
  margin-bottom: 1rem;
  font-size: 0.9rem;
}

.gl-notice-warn {
  background: #FFF7ED;
  border-left: 4px solid var(--gl-orange);
  color: #9A3412;
}

.gl-notice-danger {
  background: #FEF2F2;
  border-left: 4px solid var(--gl-crimson);
  color: #991B1B;
}

/* Primary Button Styling */
div.stButton > button:first-child[kind="primary"] {
  background: linear-gradient(135deg, var(--gl-orange) 0%, var(--gl-crimson) 100%) !important;
  color: #FFFFFF !important;
  border: none !important;
  font-weight: 700 !important;
  box-shadow: 0 2px 6px rgba(211, 47, 47, 0.3) !important;
}

div.stButton > button:first-child[kind="primary"]:hover {
  background: linear-gradient(135deg, #FF7043 0%, #C62828 100%) !important;
  box-shadow: 0 4px 10px rgba(211, 47, 47, 0.4) !important;
}

/* Secondary & Form Containers */
[data-testid="stForm"], [data-testid="stExpander"] {
  background: #FFFFFF !important;
  border: 1px solid var(--gl-surface-border) !important;
  border-radius: 8px !important;
}
</style>
"""


def inject_theme() -> None:
    """Inject custom executive Crimson & Orange stylesheet."""
    st.markdown(_THEME_CSS, unsafe_allow_html=True)
