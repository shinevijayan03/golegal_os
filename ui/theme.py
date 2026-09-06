"""
GoLegal design system for Streamlit.

Visual thesis: the product's world is the Indian e-Stamp paper - a pale green
security-printed sheet, a serial number in a mono face, a red seal. The
brand ink is the trust navy from the PRD. Everything else stays quiet so the
deed preview (rendered as stamp paper) and the signature seal are the two
things a user remembers.

Tokens
  ink        #1E3A8A   brand navy, primary actions, headings
  ink-deep   #14265F   hover / dark ends of gradients
  paper      #F7F8FA   canvas
  stamp      #EEF5EE   e-stamp green tint (document surfaces)
  stamp-ink  #1B5E3A   e-stamp green ink
  seal       #B91C1C   seal red - drafts, alerts, the wet seal
  verified   #059669   emerald - signed, sealed, healthy
  slate      #334155   body text
  muted      #64748B   secondary text
  line       #E2E8F0   hairlines

Type
  Newsreader   display / deed body (serif, editorial-legal)
  Inter        UI body (PRD)
  IBM Plex Mono  certificate numbers, hashes, tokens
"""
from __future__ import annotations

import streamlit as st

TOKENS = {
    "ink": "#1E3A8A", "ink_deep": "#14265F", "paper": "#F7F8FA", "stamp": "#EEF5EE", "stamp_ink": "#1B5E3A",
    "seal": "#B91C1C", "verified": "#059669", "slate": "#334155", "muted": "#64748B", "line": "#E2E8F0",
    "amber": "#D97706",
}

_CSS = """<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=Newsreader:ital,opsz,wght@0,6..72,400;0,6..72,500;0,6..72,600;1,6..72,400&family=IBM+Plex+Mono:wght@400;500;600&display=swap" rel="stylesheet">
<style>
:root {
  --gl-ink:#1E3A8A; --gl-ink-deep:#14265F; --gl-paper:#F7F8FA; --gl-stamp:#EEF5EE; --gl-stamp-ink:#1B5E3A;
  --gl-seal:#B91C1C; --gl-verified:#059669; --gl-slate:#334155; --gl-muted:#64748B; --gl-line:#E2E8F0; --gl-amber:#D97706;
  --gl-serif:'Newsreader', Georgia, 'Times New Roman', serif;
  --gl-sans:'Inter', -apple-system, 'Segoe UI', Roboto, sans-serif;
  --gl-mono:'IBM Plex Mono', 'SFMono-Regular', Consolas, monospace;
  --gl-radius:10px; --gl-shadow:0 1px 2px rgba(15,23,42,.06), 0 8px 24px -12px rgba(15,23,42,.18);
}
html, body, [class*="css"], .stApp { font-family: var(--gl-sans); color: var(--gl-slate); }
.stApp { background: var(--gl-paper); }
.main .block-container { padding-top: 1.1rem; padding-bottom: 3rem; max-width: 1240px; }
h1, h2, h3 { color: var(--gl-ink); font-family: var(--gl-sans); letter-spacing: -0.01em; }
h1 { font-weight: 800; } h2 { font-weight: 700; } h3 { font-weight: 700; }
#MainMenu, footer { visibility: hidden; }
[data-testid="stDecoration"] { display: none; }
[data-testid="stHeader"] { background: transparent; }
/* ---------- Buttons */
.stButton > button, .stDownloadButton > button, .stFormSubmitButton > button {
  border-radius: 8px; font-weight: 600; font-family: var(--gl-sans); border: 1px solid var(--gl-line);
  transition: transform .08s ease, box-shadow .15s ease, background .15s ease;
}
.stButton > button:hover, .stDownloadButton > button:hover { transform: translateY(-1px); box-shadow: var(--gl-shadow); }
.stButton > button[kind="primary"], .stDownloadButton > button[kind="primary"], .stFormSubmitButton > button[kind="primary"] {
  background: var(--gl-ink); color: #fff; border-color: var(--gl-ink);
}
.stButton > button[kind="primary"]:hover { background: var(--gl-ink-deep); border-color: var(--gl-ink-deep); color:#fff; }
.stButton > button:focus-visible { outline: 3px solid rgba(30,58,138,.35); outline-offset: 2px; }
/* ---------- Inputs */
.stTextInput input, .stNumberInput input, .stTextArea textarea, .stSelectbox [data-baseweb="select"] > div, .stDateInput input {
  border-radius: 8px !important; font-family: var(--gl-sans);
}
.stTextInput label, .stNumberInput label, .stTextArea label, .stSelectbox label, .stToggle label, .stCheckbox label, .stRadio label {
  font-size: .82rem; font-weight: 600; color: var(--gl-slate);
}
/* ---------- Tabs */
.stTabs [data-baseweb="tab-list"] { gap: 4px; border-bottom: 1px solid var(--gl-line); }
.stTabs [data-baseweb="tab"] { padding: 10px 14px; font-weight: 600; color: var(--gl-muted); }
.stTabs [aria-selected="true"] { color: var(--gl-ink); }
.stTabs [data-baseweb="tab-highlight"] { background: var(--gl-ink); height: 3px; }
/* ---------- Metrics */
[data-testid="stMetric"] { background:#fff; border:1px solid var(--gl-line); border-radius: var(--gl-radius); padding: 12px 16px; }
[data-testid="stMetricLabel"] { color: var(--gl-muted); font-weight: 600; font-size:.78rem; text-transform: uppercase; letter-spacing:.04em; }
[data-testid="stMetricValue"] { color: var(--gl-ink); font-family: var(--gl-sans); font-weight: 800; }
/* ---------- Sidebar */
section[data-testid="stSidebar"] { background: #fff; border-right: 1px solid var(--gl-line); }
section[data-testid="stSidebar"] .block-container { padding-top: 1rem; }
/* ---------- Containers */
[data-testid="stVerticalBlockBorderWrapper"] { border-radius: var(--gl-radius); background: #fff; }
.streamlit-expanderHeader { font-weight: 600; }
/* =====================================================================
   GoLegal components
   ===================================================================== */
.gl-fade { animation: glfade .35s ease both; }
@keyframes glfade { from { opacity: 0; transform: translateY(4px);} to { opacity: 1; transform: none; } }
@media (prefers-reduced-motion: reduce) { .gl-fade { animation: none; } .stButton > button:hover { transform:none; } }
.gl-brand { display:flex; align-items:center; gap:.5rem; flex-wrap:nowrap; }
.gl-brand .mark { width:34px; height:34px; border-radius:9px; background: var(--gl-ink); color:#fff; display:grid; place-items:center;
  font-family: var(--gl-serif); font-weight:600; font-size:1.25rem; box-shadow: inset 0 0 0 2px rgba(255,255,255,.18); }
.gl-brand .name { font-weight:800; font-size:1.35rem; color: var(--gl-ink); letter-spacing:-.02em; }
.gl-brand .tag { font-size:.72rem; font-weight:600; color: var(--gl-stamp-ink); background: var(--gl-stamp); border:1px solid #CFE3D3; padding:.15rem .5rem; border-radius:999px; white-space:nowrap; }
.gl-eyebrow { font-size:.72rem; font-weight:700; letter-spacing:.12em; text-transform:uppercase; color: var(--gl-stamp-ink); }
.gl-display { font-family: var(--gl-serif); font-weight:500; font-size: clamp(2rem, 4.2vw, 3.4rem); line-height:1.08; color: #0F172A; letter-spacing:-.01em; margin:.35rem 0 .8rem; }
.gl-display em { font-style: italic; color: var(--gl-ink); }
.gl-lede { font-size:1.08rem; color: var(--gl-muted); max-width: 42rem; line-height:1.55; }
.gl-card { background:#fff; border:1px solid var(--gl-line); border-radius: var(--gl-radius); padding: 1rem 1.15rem; box-shadow: 0 1px 2px rgba(15,23,42,.04); }
.gl-card h4 { margin:0 0 .35rem; color:#0F172A; font-size:1rem; }
.gl-card p { margin:0; color: var(--gl-muted); font-size:.9rem; line-height:1.5; }
.gl-card.accent { border-top: 3px solid var(--gl-ink); }
.gl-stat { background:#fff; border:1px solid var(--gl-line); border-radius: var(--gl-radius); padding:.9rem 1rem; }
.gl-stat .k { font-size:.72rem; font-weight:700; letter-spacing:.06em; text-transform:uppercase; color: var(--gl-muted); }
.gl-stat .v { font-size:1.6rem; font-weight:800; color: var(--gl-ink); line-height:1.15; margin-top:.15rem; }
.gl-stat .v.mono { font-family: var(--gl-mono); font-size:1.1rem; font-weight:600; }
.gl-stat .s { font-size:.8rem; color: var(--gl-muted); margin-top:.2rem; }
.gl-stat.danger { border-color:#FCA5A5; background:#FEF2F2; } .gl-stat.danger .v { color: var(--gl-seal); }
.gl-stat.ok { border-color:#A7F3D0; } .gl-stat.ok .v { color: var(--gl-verified); }
.gl-pill { display:inline-flex; align-items:center; gap:.35rem; padding:.18rem .6rem; border-radius:999px; font-size:.74rem; font-weight:700; letter-spacing:.02em; border:1px solid transparent; white-space:nowrap; }
.gl-pill.draft { background:#F1F5F9; color:#475569; border-color:#E2E8F0; }
.gl-pill.paid { background:#EFF6FF; color:#1D4ED8; border-color:#BFDBFE; }
.gl-pill.pending { background:#FFFBEB; color:#B45309; border-color:#FDE68A; }
.gl-pill.completed, .gl-pill.signed { background:#ECFDF5; color:#047857; border-color:#A7F3D0; }
.gl-pill.expired, .gl-pill.cancelled, .gl-pill.danger { background:#FEF2F2; color:#B91C1C; border-color:#FECACA; }
.gl-pill.info { background:#EFF6FF; color:#1E3A8A; border-color:#BFDBFE; }
.gl-pill .dot { width:7px; height:7px; border-radius:50%; background: currentColor; }
.gl-trust { display:flex; flex-wrap:wrap; gap:.5rem; }
.gl-trust span { font-size:.78rem; font-weight:600; color: var(--gl-slate); background:#fff; border:1px solid var(--gl-line); padding:.35rem .7rem; border-radius:8px; }
/* Stepper (a real sequence: the 5-step journey) */
.gl-stepper { display:grid; grid-template-columns: repeat(5, 1fr); gap:.4rem; margin:.4rem 0 1rem; }
.gl-step { padding:.55rem .7rem; border-radius:8px; border:1px solid var(--gl-line); background:#fff; }
.gl-step .n { font-family: var(--gl-mono); font-size:.72rem; color: var(--gl-muted); }
.gl-step .t { font-size:.85rem; font-weight:700; color: var(--gl-slate); }
.gl-step.active { border-color: var(--gl-ink); background:#EEF2FF; } .gl-step.active .t, .gl-step.active .n { color: var(--gl-ink); }
.gl-step.done { border-color:#A7F3D0; background:#F0FDF4; } .gl-step.done .t { color:#047857; } .gl-step.done .n { color:#047857; }
@media (max-width: 720px) { .gl-stepper { grid-template-columns: repeat(2, 1fr);} .gl-step .t { font-size:.78rem; } }
/* The deed, rendered as e-Stamp paper */
.gl-deed { position:relative; background: var(--gl-stamp);
  background-image: repeating-linear-gradient(45deg, rgba(27,94,58,.045) 0 2px, transparent 2px 9px), repeating-linear-gradient(-45deg, rgba(27,94,58,.045) 0 2px, transparent 2px 9px);
  border:1px solid #CFE3D3; border-radius:6px; padding:1.4rem 1.6rem 1.6rem; font-family: var(--gl-serif); color:#1F2937; box-shadow: var(--gl-shadow); overflow:hidden; }
.gl-deed:before { content:""; position:absolute; inset:8px; border:1px solid rgba(27,94,58,.35); border-radius:3px; pointer-events:none; }
.gl-deed .cert { font-family: var(--gl-sans); background:#fff; border:1px solid #B7D3BE; border-radius:4px; padding:.7rem .9rem; margin-bottom:1rem; }
.gl-deed .cert .h { text-align:center; font-weight:800; color: var(--gl-stamp-ink); letter-spacing:.06em; font-size:.8rem; }
.gl-deed .cert .g { display:grid; grid-template-columns: 1fr 1fr; gap:.15rem .9rem; font-size:.74rem; color:#334155; margin-top:.4rem; }
.gl-deed .cert .g b { color:#0F172A; font-weight:600; }
.gl-deed .cert .mono { font-family: var(--gl-mono); font-weight:600; color: var(--gl-stamp-ink); }
.gl-deed h3.t { font-family: var(--gl-serif); text-align:center; color:#0F172A; font-weight:600; font-size:1.25rem; letter-spacing:.04em; margin:.2rem 0 .8rem; }
.gl-deed p { font-size:.95rem; line-height:1.6; margin:.35rem 0; }
.gl-deed .clause { margin:.45rem 0; font-size:.92rem; line-height:1.55; }
.gl-deed .clause b { font-weight:600; }
.gl-deed .schedule { background: rgba(255,255,255,.55); border-left:3px solid var(--gl-stamp-ink); padding:.5rem .8rem; margin:.7rem 0; font-size:.92rem; }
.gl-deed .sigs { display:grid; grid-template-columns: repeat(auto-fit, minmax(150px,1fr)); gap:.6rem; margin-top:1rem; font-family: var(--gl-sans); }
.gl-deed .sig { border-top:1px solid #6B7280; padding-top:.35rem; font-size:.78rem; color:#334155; }
.gl-deed .sig .who { font-weight:700; color:#0F172A; }
.gl-deed .sig .hash { font-family: var(--gl-mono); font-size:.68rem; color: var(--gl-verified); word-break: break-all; }
.gl-deed .sig .wait { color: var(--gl-amber); font-weight:600; }
.gl-seal { position:absolute; right:1.4rem; top:6.2rem; transform: rotate(-12deg); border:3px double var(--gl-seal); color: var(--gl-seal); font-family: var(--gl-sans);
  font-weight:800; letter-spacing:.14em; font-size:.8rem; padding:.45rem .8rem; border-radius:6px; opacity:.85; background: rgba(255,255,255,.35); pointer-events:none; }
.gl-seal.sealed { border-color: var(--gl-verified); color: var(--gl-verified); }
/* Signature progress seal */
.gl-progress-seal { display:flex; align-items:center; gap:1rem; }
.gl-ring { width:78px; height:78px; border-radius:50%; display:grid; place-items:center; position:relative; flex:none; }
.gl-ring .in { width:60px; height:60px; border-radius:50%; background:#fff; display:grid; place-items:center; font-weight:800; color: var(--gl-ink); font-size:.95rem; font-family: var(--gl-mono); }
.gl-ring.done .in { color: var(--gl-verified); }
.gl-party { display:flex; align-items:center; justify-content:space-between; gap:.6rem; padding:.55rem .75rem; border:1px solid var(--gl-line); border-radius:8px; background:#fff; margin-bottom:.4rem; }
.gl-party .nm { font-weight:700; color:#0F172A; font-size:.9rem; }
.gl-party .rl { font-size:.75rem; color: var(--gl-muted); }
.gl-party .aad { font-family: var(--gl-mono); font-size:.72rem; color: var(--gl-muted); }
.gl-risk { border-left:4px solid var(--gl-line); background:#fff; border-radius:8px; padding:.6rem .8rem; margin:.35rem 0; border-top:1px solid var(--gl-line); border-right:1px solid var(--gl-line); border-bottom:1px solid var(--gl-line); }
.gl-risk.high { border-left-color: var(--gl-seal); } .gl-risk.medium { border-left-color: var(--gl-amber); } .gl-risk.low { border-left-color:#60A5FA; } .gl-risk.info { border-left-color:#94A3B8; }
.gl-risk .t { font-weight:700; font-size:.88rem; color:#0F172A; } .gl-risk .d { font-size:.82rem; color: var(--gl-slate); margin:.15rem 0; } .gl-risk .s { font-size:.8rem; color: var(--gl-stamp-ink); }
.gl-risk .q { font-family: var(--gl-serif); font-style: italic; font-size:.82rem; color:#475569; }
.gl-empty { text-align:center; padding:2rem 1rem; border:1px dashed #CBD5E1; border-radius: var(--gl-radius); background:#fff; color: var(--gl-muted); }
.gl-empty .i { font-size:1.8rem; } .gl-empty .t { font-weight:700; color: var(--gl-slate); margin:.3rem 0 .15rem; }
.gl-mono { font-family: var(--gl-mono); font-size:.8rem; background:#F1F5F9; padding:.15rem .4rem; border-radius:4px; word-break: break-all; }
.gl-notice { border-radius:8px; padding:.7rem .9rem; font-size:.88rem; border:1px solid; margin:.4rem 0; }
.gl-notice.info { background:#EFF6FF; border-color:#BFDBFE; color:#1E3A8A; }
.gl-notice.warn { background:#FFFBEB; border-color:#FDE68A; color:#92400E; }
.gl-notice.danger { background:#FEF2F2; border-color:#FECACA; color:#991B1B; }
.gl-notice.ok { background:#ECFDF5; border-color:#A7F3D0; color:#065F46; }
.gl-how { display:grid; grid-template-columns: repeat(3,1fr); gap:.8rem; }
.gl-how .st { background:#fff; border:1px solid var(--gl-line); border-radius: var(--gl-radius); padding:1rem 1.1rem; }
.gl-how .st .n { font-family: var(--gl-serif); font-size:1.9rem; color: var(--gl-ink); line-height:1; }
.gl-how .st .t { font-weight:700; margin:.4rem 0 .2rem; color:#0F172A; }
.gl-how .st p { color: var(--gl-muted); font-size:.88rem; margin:0; line-height:1.5; }
@media (max-width: 720px) { .gl-how { grid-template-columns: 1fr; } }
.gl-chat-action { font-family: var(--gl-mono); font-size:.72rem; color: var(--gl-muted); }
.gl-kv { display:grid; grid-template-columns: max-content 1fr; gap:.2rem .8rem; font-size:.85rem; }
.gl-kv b { color: var(--gl-muted); font-weight:600; }
</style>
"""


def inject_theme() -> None:
    """Load fonts and the design system once per rerun.

    st.html renders raw HTML without passing it through the markdown parser,
    which would otherwise terminate the <style> block and print the CSS.
    """
    if hasattr(st, "html"):
        st.html(_CSS)
    else:  # pragma: no cover - older Streamlit
        st.markdown(_CSS, unsafe_allow_html=True)
