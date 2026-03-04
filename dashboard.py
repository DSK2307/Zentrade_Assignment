"""
dashboard.py  –  Clara Agent Pipeline  |  Enhanced SaaS UI
Run: streamlit run dashboard.py
"""
from __future__ import annotations
import json, re, subprocess, sys
from datetime import datetime
from pathlib import Path

import streamlit as st

# ── try plotly (optional) ───────────────────────────────────────────────────
try:
    import plotly.graph_objects as go
    import plotly.express as px
    HAS_PLOTLY = True
except ImportError:
    HAS_PLOTLY = False

# ── Paths ───────────────────────────────────────────────────────────────────
REPO_ROOT    = Path(__file__).resolve().parent
ACCOUNTS_DIR = REPO_ROOT / "outputs" / "accounts"
DATASET_DIR  = REPO_ROOT / "dataset" / "demo_calls"
SCRIPTS_DIR  = REPO_ROOT / "scripts"
SUMMARY_FILE = REPO_ROOT / "outputs" / "summary_report.json"
LOG_FILE     = REPO_ROOT / "logs" / "pipeline.log"

# ── Page config ─────────────────────────────────────────────────────────────
st.set_page_config(
    page_title="Clara Agent Pipeline",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Global CSS ───────────────────────────────────────────────────────────────
st.markdown("""
<style>
@import url('https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&display=swap');

html, body, [data-testid="stAppViewContainer"] {
    font-family: 'Inter', sans-serif;
    background: #080c14;
}
[data-testid="stSidebar"] {
    background: #0d1117;
    border-right: 1px solid #1e2939;
}
[data-testid="stSidebar"] * { font-family: 'Inter', sans-serif; }

/* ── Hero ── */
.hero {
    background: linear-gradient(135deg, #0f1e3d 0%, #0a1628 50%, #0d1117 100%);
    border: 1px solid #1e2d50;
    border-radius: 16px;
    padding: 32px 40px;
    margin-bottom: 28px;
    position: relative;
    overflow: hidden;
}
.hero::before {
    content: '';
    position: absolute; top: 0; right: 0;
    width: 300px; height: 300px;
    background: radial-gradient(circle, rgba(56,139,253,0.15) 0%, transparent 70%);
    border-radius: 50%;
}
.hero h1 { color: #e6edf3; font-size: 2rem; font-weight: 700; margin: 0 0 6px; }
.hero p  { color: #8b949e; font-size: 1rem; margin: 0; }
.badge {
    display: inline-flex; align-items: center; gap: 6px;
    background: rgba(56,139,253,0.12); color: #58a6ff;
    border: 1px solid rgba(56,139,253,0.3); border-radius: 20px;
    padding: 4px 12px; font-size: 0.78rem; font-weight: 500; margin: 4px 4px 0 0;
}
.badge-green { background: rgba(63,185,80,0.12); color: #3fb950; border-color: rgba(63,185,80,0.3); }
.badge-yellow { background: rgba(210,153,34,0.12); color: #d29922; border-color: rgba(210,153,34,0.3); }

/* ── Metric Cards ── */
.kpi-grid { display: grid; grid-template-columns: repeat(4,1fr); gap: 16px; margin-bottom: 28px; }
.kpi-card {
    background: linear-gradient(145deg, #111827, #0d1117);
    border: 1px solid #1e2939;
    border-radius: 14px;
    padding: 22px 24px;
    position: relative; overflow: hidden;
    transition: border-color .2s, transform .2s;
}
.kpi-card:hover { border-color: #388bfd55; transform: translateY(-2px); }
.kpi-card .icon { font-size: 1.6rem; margin-bottom: 10px; }
.kpi-card .val  { font-size: 2.2rem; font-weight: 700; color: #58a6ff; line-height:1; }
.kpi-card .lbl  { color: #8b949e; font-size: 0.82rem; margin-top: 6px; }
.kpi-card .accent {
    position: absolute; right: 0; top: 0; bottom: 0; width: 4px;
    background: linear-gradient(#388bfd, #1f6feb);
    border-radius: 0 14px 14px 0;
}
.kpi-card .accent-green  { background: linear-gradient(#3fb950, #2ea043); }
.kpi-card .accent-yellow { background: linear-gradient(#d29922, #9e6a03); }
.kpi-card .accent-red    { background: linear-gradient(#f85149, #da3633); }

/* ── Account cards ── */
.acct-card {
    background: #0d1117;
    border: 1px solid #1e2939;
    border-radius: 12px;
    padding: 18px 22px;
    margin-bottom: 12px;
    transition: border-color .2s;
    cursor: pointer;
}
.acct-card:hover { border-color: #388bfd55; }
.acct-name { color: #e6edf3; font-weight: 600; font-size: 1rem; }
.acct-id   { color: #8b949e; font-size: 0.78rem; font-family: monospace; }
.tag {
    display: inline-block; border-radius: 8px;
    padding: 2px 10px; font-size: 0.74rem; font-weight: 600; margin: 0 3px;
}
.tag-v1  { background: rgba(56,139,253,0.15); color: #58a6ff; }
.tag-v2  { background: rgba(63,185,80,0.15);  color: #3fb950; }
.tag-no  { background: rgba(139,148,158,0.1); color: #8b949e; }

/* ── Diff ── */
.diff-added    { background:#0d2119; border-left:3px solid #3fb950; padding:10px 14px; border-radius:0 8px 8px 0; margin:5px 0; }
.diff-modified { background:#1c1700; border-left:3px solid #d29922; padding:10px 14px; border-radius:0 8px 8px 0; margin:5px 0; }
.diff-removed  { background:#1e0a0a; border-left:3px solid #f85149; padding:10px 14px; border-radius:0 8px 8px 0; margin:5px 0; }
.diff-same     { background:#0d1117; border-left:3px solid #21262d; padding:10px 14px; border-radius:0 8px 8px 0; margin:5px 0; }
.diff-key { color:#cdd9e5; font-weight:600; font-size:0.88rem; }
.diff-val { color:#8b949e; font-family:monospace; font-size:0.8rem; margin-top:3px; word-break:break-all; }
.val-old  { color:#f85149; }
.val-new  { color:#3fb950; }

/* ── Log viewer ── */
.log-container {
    background: #0a0d14;
    border: 1px solid #1e2939;
    border-radius: 10px;
    padding: 14px 18px;
    font-family: 'Courier New', monospace;
    font-size: 0.78rem;
    max-height: 340px;
    overflow-y: auto;
}
.log-info    { color: #58a6ff; }
.log-warning { color: #d29922; }
.log-error   { color: #f85149; }
.log-default { color: #8b949e; }

/* ── Step indicator ── */
.steps { display: flex; gap: 0; margin: 16px 0 24px; }
.step  {
    flex: 1; text-align: center; padding: 10px 4px;
    border-top: 2px solid #1e2939;
    color: #8b949e; font-size: 0.78rem;
    transition: border-color .3s, color .3s;
}
.step.active  { border-color: #388bfd; color: #58a6ff; font-weight: 600; }
.step.done    { border-color: #3fb950; color: #3fb950; }
.step.failed  { border-color: #f85149; color: #f85149; }

/* ── Sidebar nav ── */
.nav-item {
    display: flex; align-items: center; gap: 10px;
    padding: 10px 14px; border-radius: 8px;
    color: #8b949e; font-size: 0.9rem;
    cursor: pointer; margin-bottom: 4px;
    transition: background .2s, color .2s;
}
.nav-item:hover  { background: #1e2939; color: #e6edf3; }
.nav-item.active { background: rgba(56,139,253,0.15); color: #58a6ff; font-weight: 600; }
.sidebar-section { color: #6e7681; font-size: 0.72rem; text-transform: uppercase;
                    letter-spacing: .8px; padding: 10px 14px 4px; font-weight: 600; }

/* ── Section heading ── */
.section-heading {
    color: #e6edf3; font-size: 1.1rem; font-weight: 600;
    border-bottom: 1px solid #1e2939;
    padding-bottom: 10px; margin-bottom: 18px;
}
</style>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
#  Helpers
# ════════════════════════════════════════════════════════════════════════════

def load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_all_accounts() -> list[dict]:
    accounts = []
    if not ACCOUNTS_DIR.exists():
        return accounts
    for acct_dir in sorted(ACCOUNTS_DIR.iterdir()):
        if not acct_dir.is_dir():
            continue
        info = {"id": acct_dir.name, "has_v1": False, "has_v2": False,
                "v1_memo": None, "v2_memo": None, "company": acct_dir.name}
        v1_memo = acct_dir / "v1" / "memo.json"
        v2_memo = acct_dir / "v2" / "memo.json"
        if v1_memo.exists():
            info["has_v1"] = True
            m = load_json(v1_memo)
            if m:
                info["v1_memo"] = m
                info["company"] = m.get("company_name", acct_dir.name)
        if v2_memo.exists():
            info["has_v2"] = True
            info["v2_memo"] = load_json(v2_memo)
        accounts.append(info)
    return accounts


def val_str(val) -> str:
    if val is None:
        return "—"
    if isinstance(val, (dict, list)):
        return json.dumps(val, ensure_ascii=False)
    return str(val)


SKIP_DIFF_FIELDS = {"last_updated", "schema_version", "created_at"}


def compute_diff(v1: dict, v2: dict) -> list[dict]:
    diff = []
    for key in sorted(set(v1) | set(v2)):
        if key in SKIP_DIFF_FIELDS:
            continue
        v1v, v2v = v1.get(key), v2.get(key)
        if key not in v1:
            diff.append({"field": key, "status": "added",    "v1": None, "v2": v2v})
        elif key not in v2:
            diff.append({"field": key, "status": "removed",  "v1": v1v,  "v2": None})
        elif v1v != v2v:
            diff.append({"field": key, "status": "modified", "v1": v1v,  "v2": v2v})
        else:
            diff.append({"field": key, "status": "same",     "v1": v1v,  "v2": v2v})
    return diff


def run_script(cmd: list[str]) -> tuple[int, str]:
    try:
        r = subprocess.run(cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120)
        return r.returncode, r.stdout + r.stderr
    except subprocess.TimeoutExpired:
        return 1, "Script timed out after 120 seconds."
    except Exception as e:
        return 1, str(e)


def render_log_html(lines: list[str]) -> str:
    parts = []
    for line in lines:
        if "[INFO]" in line:
            parts.append(f'<div class="log-info">{line}</div>')
        elif "[WARNING]" in line:
            parts.append(f'<div class="log-warning">{line}</div>')
        elif "[ERROR]" in line:
            parts.append(f'<div class="log-error">{line}</div>')
        else:
            parts.append(f'<div class="log-default">{line}</div>')
    return "\n".join(parts)


def parse_log_to_rows(log_text: str) -> list[dict]:
    rows = []
    pattern = re.compile(r'\[(\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2})\] \[(\w+)\] (.+)')
    for line in log_text.splitlines():
        m = pattern.match(line.strip())
        if m:
            rows.append({"Timestamp": m.group(1), "Level": m.group(2), "Message": m.group(3)})
    return rows


# ════════════════════════════════════════════════════════════════════════════
#  Data
# ════════════════════════════════════════════════════════════════════════════

accounts = get_all_accounts()
total     = len(accounts)
with_v1   = sum(1 for a in accounts if a["has_v1"])
with_v2   = sum(1 for a in accounts if a["has_v2"])
unknowns  = sum(len(a["v1_memo"].get("questions_or_unknowns", [])) for a in accounts if a.get("v1_memo"))

summary = load_json(SUMMARY_FILE) if SUMMARY_FILE.exists() else {}
last_run = ""
if summary:
    ts = summary.get("run_timestamp", "")
    try:
        last_run = datetime.fromisoformat(ts).strftime("%b %d, %Y %H:%M")
    except Exception:
        last_run = ts


# ════════════════════════════════════════════════════════════════════════════
#  SIDEBAR
# ════════════════════════════════════════════════════════════════════════════

with st.sidebar:
    st.markdown("""
    <div style="padding:20px 14px 10px;">
      <div style="font-size:1.3rem;font-weight:700;color:#e6edf3;">🤖 Clara</div>
      <div style="color:#8b949e;font-size:0.78rem;margin-top:2px;">Agent Pipeline v2.0</div>
    </div>
    """, unsafe_allow_html=True)

    page = st.radio("Navigation", ["📊 Dashboard", "🔍 Diff Viewer", "⚡ Batch Processor", "📜 Live Logs"],
                    label_visibility="collapsed")

    st.markdown('<div class="sidebar-section">System Status</div>', unsafe_allow_html=True)
    status_color = "#3fb950" if total > 0 else "#d29922"
    st.markdown(f"""
    <div style="padding:0 14px;">
      <div style="display:flex;align-items:center;gap:8px;margin-bottom:8px;">
        <div style="width:8px;height:8px;border-radius:50%;background:{status_color};"></div>
        <span style="color:#8b949e;font-size:0.82rem;">Pipeline <b style="color:#e6edf3;">{'Active' if total > 0 else 'Idle'}</b></span>
      </div>
      <div style="color:#8b949e;font-size:0.8rem;">Accounts: <b style="color:#58a6ff;">{total}</b></div>
      <div style="color:#8b949e;font-size:0.8rem;margin-top:4px;">Last run: <b style="color:#e6edf3;">{last_run or 'N/A'}</b></div>
    </div>
    """, unsafe_allow_html=True)

    st.markdown('<div class="sidebar-section" style="margin-top:12px;">Accounts</div>', unsafe_allow_html=True)
    search = st.text_input("🔍 Search", placeholder="Filter accounts...", label_visibility="collapsed")

    for a in accounts:
        if search and search.lower() not in a["company"].lower() and search.lower() not in a["id"].lower():
            continue
        v1t = f'<span class="tag tag-v1">v1</span>' if a["has_v1"] else f'<span class="tag tag-no">—</span>'
        v2t = f'<span class="tag tag-v2">v2</span>' if a["has_v2"] else f'<span class="tag tag-no">—</span>'
        st.markdown(f"""
        <div class="acct-card" style="padding:12px 16px;margin-bottom:6px;">
          <div class="acct-name" style="font-size:0.85rem;">{a['company']}</div>
          <div class="acct-id">{a['id']}</div>
          <div style="margin-top:6px;">{v1t}{v2t}</div>
        </div>
        """, unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
#  HERO
# ════════════════════════════════════════════════════════════════════════════

onboard_pct = int((with_v2 / with_v1) * 100) if with_v1 else 0
st.markdown(f"""
<div class="hero">
  <h1>🤖 Clara Agent Pipeline</h1>
  <p>Zero-cost automation · Transcript → Retell AI Voice Agent Config</p>
  <div style="margin-top:14px;">
    <span class="badge badge-green">● Pipeline Active</span>
    <span class="badge">{total} Accounts Processed</span>
    <span class="badge badge-yellow">⏱ {last_run or 'No runs yet'}</span>
    <span class="badge">{onboard_pct}% Onboarded</span>
  </div>
</div>
""", unsafe_allow_html=True)


# ════════════════════════════════════════════════════════════════════════════
#  TAB 1 – DASHBOARD
# ════════════════════════════════════════════════════════════════════════════

if page == "📊 Dashboard":

    # KPI cards
    st.markdown(f"""
    <div class="kpi-grid">
      <div class="kpi-card">
        <div class="accent"></div>
        <div class="icon">🏢</div>
        <div class="val">{total}</div>
        <div class="lbl">Total Accounts</div>
      </div>
      <div class="kpi-card">
        <div class="accent accent-green"></div>
        <div class="icon">✅</div>
        <div class="val">{with_v1}</div>
        <div class="lbl">v1 Configs Generated</div>
      </div>
      <div class="kpi-card">
        <div class="accent accent-green"></div>
        <div class="icon">🚀</div>
        <div class="val">{with_v2}</div>
        <div class="lbl">v2 Onboarded</div>
      </div>
      <div class="kpi-card">
        <div class="accent accent-yellow"></div>
        <div class="icon">❓</div>
        <div class="val">{unknowns}</div>
        <div class="lbl">Open Questions</div>
      </div>
    </div>
    """, unsafe_allow_html=True)

    # Charts row
    if HAS_PLOTLY and accounts:
        c1, c2 = st.columns([2, 1])
        with c1:
            st.markdown('<div class="section-heading">📊 Pipeline Completion</div>', unsafe_allow_html=True)
            companies = [a["company"][:22] for a in accounts]
            v1_vals = [1 if a["has_v1"] else 0 for a in accounts]
            v2_vals = [1 if a["has_v2"] else 0 for a in accounts]
            fig = go.Figure()
            fig.add_bar(name="v1 Config", x=companies, y=v1_vals,
                        marker_color="#388bfd", opacity=0.85)
            fig.add_bar(name="v2 Onboarded", x=companies, y=v2_vals,
                        marker_color="#3fb950", opacity=0.85)
            fig.update_layout(
                barmode="group", plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
                font_color="#8b949e", legend=dict(bgcolor="#0d1117"),
                margin=dict(l=20, r=20, t=20, b=60),
                xaxis=dict(gridcolor="#1e2939", tickangle=-30),
                yaxis=dict(gridcolor="#1e2939", tickvals=[0, 1]),
                height=280,
            )
            st.plotly_chart(fig, use_container_width=True)

        with c2:
            st.markdown('<div class="section-heading">🥧 v1 vs v2</div>', unsafe_allow_html=True)
            remaining = with_v1 - with_v2
            pie = go.Figure(go.Pie(
                labels=["v2 Onboarded", "v1 Only"],
                values=[with_v2, max(remaining, 0)],
                hole=0.6,
                marker_colors=["#3fb950", "#388bfd"],
            ))
            pie.update_layout(
                plot_bgcolor="#0d1117", paper_bgcolor="#0d1117",
                font_color="#8b949e", showlegend=True,
                legend=dict(bgcolor="#0d1117"),
                margin=dict(l=10, r=10, t=20, b=20), height=280,
            )
            pie.update_traces(textposition="inside", textinfo="percent")
            st.plotly_chart(pie, use_container_width=True)

    # Last batch summary
    if summary:
        st.markdown('<div class="section-heading" style="margin-top:8px;">📋 Last Batch Summary</div>', unsafe_allow_html=True)
        r1, r2, r3, r4, r5 = st.columns(5)
        for col, key, label in [
            (r1, "processed",                   "Processed"),
            (r2, "accounts_created",            "Created"),
            (r3, "errors",                      "Errors"),
            (r4, "missing_business_hours",      "Missing Hours"),
            (r5, "missing_emergency_definitions","Missing Emerg."),
        ]:
            col.metric(label, summary.get(key, 0))

    # Account cards
    st.markdown('<div class="section-heading" style="margin-top:12px;">🗂️ Account Details</div>', unsafe_allow_html=True)

    filter_col1, filter_col2 = st.columns([2, 1])
    with filter_col1:
        search_acct = st.text_input("Search accounts", placeholder="Company name or ID…", label_visibility="collapsed")
    with filter_col2:
        status_filter = st.selectbox("Filter", ["All", "v1 Only", "v2 Onboarded"], label_visibility="collapsed")

    filtered = accounts
    if search_acct:
        filtered = [a for a in filtered if search_acct.lower() in a["company"].lower() or search_acct.lower() in a["id"].lower()]
    if status_filter == "v1 Only":
        filtered = [a for a in filtered if a["has_v1"] and not a["has_v2"]]
    elif status_filter == "v2 Onboarded":
        filtered = [a for a in filtered if a["has_v2"]]

    if not filtered:
        st.info("No accounts match your filter. Run Pipeline A first.")
    else:
        for a in filtered:
            with st.expander(f"🏢  {a['company']}  |  `{a['id']}`", expanded=False):
                tv1, tv2 = st.tabs(["📋 v1 Config", "✨ v2 Onboarded"])
                with tv1:
                    if a["v1_memo"]:
                        m = a["v1_memo"]
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**🕐 Hours:** `{json.dumps(m.get('business_hours','N/A'))}`")
                            st.write(f"**🌐 Timezone:** `{m.get('timezone','—')}`")
                            st.write(f"**📍 Address:** `{m.get('office_address','—')}`")
                        with col2:
                            svcs = m.get("services_supported", [])
                            st.write("**🔧 Services:**")
                            for s in svcs:
                                st.caption(f" • {s}")
                        qs = m.get("questions_or_unknowns", [])
                        if qs:
                            st.warning(f"⚠️ {len(qs)} open question(s)")
                            for q in qs:
                                st.caption(f"  • {q}")
                        st.markdown("---")
                        st.json(m, expanded=False)
                        st.download_button("⬇️ memo.json", data=json.dumps(m, indent=2),
                                           file_name=f"{a['id']}_v1_memo.json", key=f"dl_v1_{a['id']}")
                    else:
                        st.info("No v1 memo found.")
                with tv2:
                    if a["v2_memo"]:
                        m2 = a["v2_memo"]
                        st.success(f"✅ Onboarding Complete (schema v{m2.get('schema_version','?')})")
                        st.write(f"**🕐 Updated Hours:** `{json.dumps(m2.get('business_hours','N/A'))}`")
                        st.write(f"**📅 Last Updated:** `{m2.get('last_updated','—')[:10]}`")
                        changelog = ACCOUNTS_DIR / a["id"] / "v2" / "changes.md"
                        if changelog.exists():
                            st.download_button("⬇️ changes.md", data=changelog.read_text("utf-8"),
                                               file_name=f"{a['id']}_changes.md", key=f"dl_cl_{a['id']}")
                        st.json(m2, expanded=False)
                    else:
                        st.info("No v2 yet. Run Pipeline B to patch.")


# ════════════════════════════════════════════════════════════════════════════
#  TAB 2 – DIFF VIEWER
# ════════════════════════════════════════════════════════════════════════════

elif page == "🔍 Diff Viewer":
    st.markdown('<div class="section-heading">🔍 v1 → v2 Field-Level Diff Viewer</div>', unsafe_allow_html=True)

    acct_ids = [a["id"] for a in accounts if a["has_v1"] and a["has_v2"]]
    if not acct_ids:
        st.warning("No accounts with both v1 and v2 found. Run Pipeline B first.")
    else:
        col_sel, col_mode = st.columns([2, 1])
        with col_sel:
            selected = st.selectbox("Select Account", acct_ids)
        with col_mode:
            view_mode = st.radio("View", ["Compact", "Detailed"], horizontal=True)

        acct_info = next(a for a in accounts if a["id"] == selected)
        v1, v2 = acct_info["v1_memo"], acct_info["v2_memo"]
        diff = compute_diff(v1, v2)

        added    = [d for d in diff if d["status"] == "added"]
        modified = [d for d in diff if d["status"] == "modified"]
        removed  = [d for d in diff if d["status"] == "removed"]
        same     = [d for d in diff if d["status"] == "same"]
        total_f  = len(diff)
        chg_pct  = ((len(added)+len(modified)+len(removed))/total_f)*100 if total_f else 0

        st.progress(int(chg_pct), text=f"Update intensity: {chg_pct:.1f}% of fields changed")

        d1, d2, d3, d4 = st.columns(4)
        d1.metric("✅ Added",     len(added))
        d2.metric("✏️ Modified",  len(modified))
        d3.metric("🗑️ Removed",   len(removed))
        d4.metric("⬜ Unchanged", len(same))

        show_filter = st.multiselect(
            "Show statuses", ["added", "modified", "removed", "same"],
            default=["added", "modified", "removed"]
        )

        st.markdown("""
        <div style="display:flex;gap:16px;margin:12px 0;font-size:0.82rem;">
          <span style="color:#3fb950;">● Added</span>
          <span style="color:#d29922;">● Modified</span>
          <span style="color:#f85149;">● Removed</span>
          <span style="color:#484f58;">● Unchanged</span>
        </div>""", unsafe_allow_html=True)

        for item in diff:
            if item["status"] not in show_filter:
                continue
            css = f"diff-{item['status']}"
            f   = item["field"]
            s   = item["status"].upper()

            if item["status"] == "added":
                icon = "+"
                body = f'<div class="diff-val val-new">{val_str(item["v2"])}</div>'
            elif item["status"] == "removed":
                icon = "−"
                body = f'<div class="diff-val val-old">{val_str(item["v1"])}</div>'
            elif item["status"] == "modified":
                icon = "~"
                if view_mode == "Detailed":
                    body = (f'<div class="diff-val val-old">FROM: {val_str(item["v1"])}</div>'
                            f'<div class="diff-val val-new">TO:   {val_str(item["v2"])}</div>')
                else:
                    body = f'<div class="diff-val"><span class="val-old">{val_str(item["v1"])}</span> → <span class="val-new">{val_str(item["v2"])}</span></div>'
            else:
                icon = " "
                body = f'<div class="diff-val" style="color:#484f58;">{val_str(item["v1"])}</div>'

            st.markdown(f"""
            <div class="{css}">
              <div class="diff-key">{icon} {f} <span style="font-size:0.72rem;opacity:.6;">[{s}]</span></div>
              {body}
            </div>""", unsafe_allow_html=True)

        changelog_path = ACCOUNTS_DIR / selected / "v2" / "changes.md"
        if changelog_path.exists():
            st.markdown("---")
            with st.expander("📄 View changes.md"):
                st.markdown(changelog_path.read_text(encoding="utf-8"))


# ════════════════════════════════════════════════════════════════════════════
#  TAB 3 – BATCH PROCESSOR
# ════════════════════════════════════════════════════════════════════════════

elif page == "⚡ Batch Processor":
    st.markdown('<div class="section-heading">⚡ Batch Processor</div>', unsafe_allow_html=True)

    col_left, col_right = st.columns(2)

    # Pipeline A
    with col_left:
        st.markdown("### 🔵 Pipeline A — Discovery → v1")
        transcripts = sorted(DATASET_DIR.glob("*.txt")) if DATASET_DIR.exists() else []
        transcripts = [t for t in transcripts if "_normalized" not in t.stem]
        st.info(f"**{len(transcripts)}** transcript(s) found in `dataset/demo_calls/`")
        force_a = st.checkbox("Force overwrite existing outputs", key="force_a")

        if st.button("▶️ Run Pipeline A", use_container_width=True, type="primary"):
            if not transcripts:
                st.error("No transcripts found.")
            else:
                pb = st.progress(0, "Starting batch…")
                cmd = [sys.executable, str(SCRIPTS_DIR / "batch_process.py"),
                       "--dataset_dir", str(DATASET_DIR), "--output_dir", str(ACCOUNTS_DIR)]
                if force_a:
                    cmd.append("--force")
                rc, out = run_script(cmd)
                pb.progress(100, "Done!")
                if rc == 0:
                    st.success("✅ Batch Pipeline A complete!")
                    st.balloons()
                else:
                    st.error("❌ Batch failed.")

                # Tabular log
                rows = parse_log_to_rows(out)
                if rows:
                    st.dataframe(rows, use_container_width=True, height=260)
                else:
                    st.markdown(f'<div class="log-container">{render_log_html(out.splitlines())}</div>',
                                unsafe_allow_html=True)

                if SUMMARY_FILE.exists():
                    rep = load_json(SUMMARY_FILE)
                    if rep:
                        r1, r2, r3 = st.columns(3)
                        r1.metric("Processed", rep.get("processed", 0))
                        r2.metric("Created",   rep.get("accounts_created", 0))
                        r3.metric("Errors",    rep.get("errors", 0))

    # Pipeline B
    with col_right:
        st.markdown("### 🟣 Pipeline B — Onboarding → v2")
        acct_options = [a["id"] for a in accounts if a["has_v1"]]
        onboard_dir  = REPO_ROOT / "dataset" / "onboarding_calls"
        onboard_files = sorted(onboard_dir.glob("*.txt")) if onboard_dir.exists() else []
        onboard_files = [f for f in onboard_files if "_normalized" not in f.stem]

        if not acct_options:
            st.warning("No v1 accounts found. Run Pipeline A first.")
        else:
            sel_acct    = st.selectbox("Account to update", acct_options)
            sel_onboard = st.selectbox("Onboarding transcript",
                                       [f.name for f in onboard_files] if onboard_files else ["(none found)"])
            force_b = st.checkbox("Force overwrite v2", key="force_b")

            STEPS = ["Normalize", "Apply Patch", "Generate Agent", "Changelog"]

            step_ph = st.empty()
            def render_steps(states: list[str]):
                html = '<div class="steps">'
                for label, state in zip(STEPS, states):
                    html += f'<div class="step {state}">{label}</div>'
                html += "</div>"
                step_ph.markdown(html, unsafe_allow_html=True)

            render_steps(["", "", "", ""])

            if st.button("▶️ Run Pipeline B", use_container_width=True, type="primary"):
                if not onboard_files or sel_onboard == "(none found)":
                    st.error("No onboarding transcript found.")
                else:
                    onboard_path = onboard_dir / sel_onboard
                    v1_memo      = ACCOUNTS_DIR / sel_acct / "v1" / "memo.json"
                    v2_out       = ACCOUNTS_DIR / sel_acct / "v2"
                    norm_out     = str(onboard_path).replace(".txt", "_normalized.txt")
                    ff           = ["--force"] if force_b else []

                    pipeline_steps = [
                        ("Normalize", [sys.executable, str(SCRIPTS_DIR / "normalize_transcript.py"),
                                       "--input", str(onboard_path), "--output", norm_out]),
                        ("Apply Patch", [sys.executable, str(SCRIPTS_DIR / "apply_patch.py"),
                                         "--v1_memo", str(v1_memo),
                                         "--onboarding", norm_out,
                                         "--output_dir", str(v2_out)] + ff),
                        ("Generate Agent", [sys.executable, str(SCRIPTS_DIR / "generate_agent.py"),
                                            "--memo", str(v2_out / "memo.json"),
                                            "--output_dir", str(v2_out),
                                            "--version", "2.0"] + ff),
                        ("Changelog", [sys.executable, str(SCRIPTS_DIR / "changelog.py"),
                                       "--v1", str(v1_memo),
                                       "--v2", str(v2_out / "memo.json"),
                                       "--output", str(v2_out / "changes.md")] + ff),
                    ]

                    pb2 = st.progress(0)
                    all_logs  = []
                    states    = ["", "", "", ""]
                    failed    = False

                    for i, (label, cmd) in enumerate(pipeline_steps):
                        states[i] = "active"
                        render_steps(states)
                        pb2.progress(int((i / len(pipeline_steps)) * 100), text=f"Running {label}…")
                        rc, out = run_script(cmd)
                        all_logs.append({"Step": label, "Log Output": out.strip()})
                        if rc != 0:
                            states[i] = "failed"
                            render_steps(states)
                            st.error(f"❌ {label} failed.")
                            failed = True
                            break
                        states[i] = "done"
                        render_steps(states)

                    pb2.progress(100, "Done!")
                    if not failed:
                        st.success(f"✅ Pipeline B complete for `{sel_acct}`!")
                        st.balloons()
                        st.toast(f"🎉 Onboarded {sel_acct}!", icon="🚀")

                    st.dataframe(all_logs, use_container_width=True)

                    st.markdown("**📁 Output files:**")
                    for fname in ["memo.json", "agent_spec.json", "changes.md"]:
                        fp = v2_out / fname
                        st.caption(f"{'✅' if fp.exists() else '❌'} `{fp.relative_to(REPO_ROOT)}`")

    # Summary report
    st.markdown("---")
    st.markdown('<div class="section-heading">📋 Summary Report</div>', unsafe_allow_html=True)
    if SUMMARY_FILE.exists():
        rep = load_json(SUMMARY_FILE)
        if rep:
            st.json(rep)
            st.download_button("⬇️ Download summary_report.json",
                               data=json.dumps(rep, indent=2),
                               file_name="summary_report.json",
                               mime="application/json")
    else:
        st.info("No summary report yet. Run Pipeline A batch first.")


# ════════════════════════════════════════════════════════════════════════════
#  TAB 4 – LIVE LOGS
# ════════════════════════════════════════════════════════════════════════════

elif page == "📜 Live Logs":
    st.markdown('<div class="section-heading">📜 Pipeline Log Viewer</div>', unsafe_allow_html=True)

    if not LOG_FILE.exists():
        st.info("No log file found at `logs/pipeline.log`.")
    else:
        raw = LOG_FILE.read_text(encoding="utf-8", errors="replace")
        log_rows = parse_log_to_rows(raw)

        # Filters
        lc1, lc2, lc3 = st.columns([2, 1, 1])
        with lc1:
            log_search = st.text_input("Search logs", placeholder="Filter messages…", label_visibility="collapsed")
        with lc2:
            level_filter = st.multiselect("Level", ["INFO", "WARNING", "ERROR"], default=["INFO", "WARNING", "ERROR"])
        with lc3:
            max_rows = st.number_input("Max rows", min_value=10, max_value=500, value=100, step=10, label_visibility="collapsed")

        filtered_rows = [r for r in log_rows if r["Level"] in level_filter]
        if log_search:
            filtered_rows = [r for r in filtered_rows if log_search.lower() in r["Message"].lower()]
        filtered_rows = filtered_rows[-max_rows:]

        # Stats
        s1, s2, s3 = st.columns(3)
        s1.metric("Total Lines", len(log_rows))
        s2.metric("Warnings", sum(1 for r in log_rows if r["Level"] == "WARNING"))
        s3.metric("Errors",   sum(1 for r in log_rows if r["Level"] == "ERROR"))

        st.markdown("---")

        # Table view
        st.dataframe(filtered_rows, use_container_width=True, height=420)

        # Raw log coloured view
        with st.expander("🖥️ Raw coloured log output"):
            html_lines = render_log_html([f"[{r['Timestamp']}] [{r['Level']}] {r['Message']}" for r in filtered_rows])
            st.markdown(f'<div class="log-container">{html_lines}</div>', unsafe_allow_html=True)

        st.download_button("⬇️ Download Full Log", data=raw, file_name="pipeline.log", mime="text/plain")
