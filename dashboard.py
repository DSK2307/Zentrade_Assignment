"""
dashboard.py
─────────────────────────────────────────────────────────
Clara Agent Pipeline – Streamlit Dashboard

Three tabs:
  📊  Dashboard       – account overview + summary metrics
  🔍  Diff Viewer     – v1 vs v2 field-level highlighted diff
  ⚡  Batch Processor – run pipeline, view results

Run:
    streamlit run dashboard.py
─────────────────────────────────────────────────────────
"""

from __future__ import annotations

import json
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import streamlit as st

# ── Repo paths ────────────────────────────────────────────────────────────────
REPO_ROOT    = Path(__file__).resolve().parent
ACCOUNTS_DIR = REPO_ROOT / "outputs" / "accounts"
DATASET_DIR  = REPO_ROOT / "dataset" / "demo_calls"
SCRIPTS_DIR  = REPO_ROOT / "scripts"
SUMMARY_FILE = REPO_ROOT / "outputs" / "summary_report.json"

# ─────────────────────────────────────────────────────────────────────────────
#  Page config
# ─────────────────────────────────────────────────────────────────────────────

st.set_page_config(
    page_title="Clara Agent Pipeline",
    page_icon="🤖",
    layout="wide",
    initial_sidebar_state="expanded",
)

# ── Custom CSS ────────────────────────────────────────────────────────────────
st.markdown("""
<style>
/* Overall background */
[data-testid="stAppViewContainer"] { background: #0f1117; }
[data-testid="stSidebar"] { background: #161b22; border-right: 1px solid #30363d; }

/* Header */
.clara-header {
    background: linear-gradient(135deg, #1a1f2e 0%, #0d1117 100%);
    border: 1px solid #30363d;
    border-radius: 12px;
    padding: 24px 32px;
    margin-bottom: 24px;
}
.clara-header h1 { color: #58a6ff; font-size: 2rem; margin: 0; }
.clara-header p  { color: #8b949e; margin: 4px 0 0; }

/* Metric cards */
.metric-card {
    background: #161b22;
    border: 1px solid #30363d;
    border-radius: 10px;
    padding: 20px;
    text-align: center;
}
.metric-card .val { font-size: 2.4rem; font-weight: 700; color: #58a6ff; }
.metric-card .lbl { color: #8b949e; font-size: 0.85rem; margin-top: 4px; }

/* Diff boxes */
.field-added    { background:#0d2119; border-left:4px solid #3fb950; padding:10px 14px; border-radius:6px; margin:6px 0; }
.field-modified { background:#1c1700; border-left:4px solid #d29922; padding:10px 14px; border-radius:6px; margin:6px 0; }
.field-removed  { background:#1e0a0a; border-left:4px solid #f85149; padding:10px 14px; border-radius:6px; margin:6px 0; }
.field-same     { background:#161b22; border-left:4px solid #30363d; padding:10px 14px; border-radius:6px; margin:6px 0; }
.field-key  { color:#cdd9e5; font-weight:600; font-size:0.9rem; }
.field-val  { color:#8b949e; font-family:monospace; font-size:0.82rem; margin-top:3px; word-break:break-all; }
.val-old    { color:#f85149; }
.val-new    { color:#3fb950; }

/* Account badge */
.account-badge {
    display:inline-block; background:#1a3c5e; color:#58a6ff;
    border:1px solid #388bfd44; border-radius:20px;
    padding:4px 14px; font-size:0.82rem; margin:3px;
}
/* Log area */
.log-box {
    background:#0d1117; border:1px solid #30363d; border-radius:8px;
    padding:14px; font-family:monospace; font-size:0.78rem;
    color:#8b949e; max-height:300px; overflow-y:auto;
}
/* Scrollable JSON */
.json-box {
    background:#0d1117; border:1px solid #30363d; border-radius:8px;
    padding:14px; font-family:monospace; font-size:0.78rem; color:#cdd9e5;
    max-height:400px; overflow-y:auto; white-space:pre-wrap;
}
</style>
""", unsafe_allow_html=True)

# ─────────────────────────────────────────────────────────────────────────────
#  Helper functions
# ─────────────────────────────────────────────────────────────────────────────

def load_json(path: Path) -> dict | None:
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception:
        return None


def get_all_accounts() -> list[dict]:
    """Scan outputs/accounts/ and return list of account info dicts."""
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
    """Return list of diff items: {field, status, v1_val, v2_val}"""
    diff = []
    all_keys = sorted(set(v1.keys()) | set(v2.keys()))
    for key in all_keys:
        if key in SKIP_DIFF_FIELDS:
            continue
        v1v = v1.get(key)
        v2v = v2.get(key)
        if key not in v1:
            diff.append({"field": key, "status": "added",    "v1": None, "v2": v2v})
        elif key not in v2:
            diff.append({"field": key, "status": "removed",  "v1": v1v,  "v2": None})
        elif v1v != v2v:
            diff.append({"field": key, "status": "modified", "v1": v1v,  "v2": v2v})
        else:
            diff.append({"field": key, "status": "same",     "v1": v1v,  "v2": v2v})
    return diff


def run_script_live(cmd: list[str]) -> tuple[int, str]:
    """Run a script and return (returncode, combined output)."""
    try:
        result = subprocess.run(
            cmd, cwd=str(REPO_ROOT), capture_output=True, text=True, timeout=120
        )
        output = result.stdout + result.stderr
        return result.returncode, output
    except subprocess.TimeoutExpired:
        return 1, "Script timed out after 120 seconds."
    except Exception as e:
        return 1, str(e)


# ─────────────────────────────────────────────────────────────────────────────
#  Sidebar
# ─────────────────────────────────────────────────────────────────────────────

with st.sidebar:
    st.markdown("## 🤖 Clara Pipeline")
    st.markdown("---")
    tab_choice = st.radio(
        "Navigate",
        ["📊 Dashboard", "🔍 Diff Viewer", "⚡ Batch Processor"],
        label_visibility="collapsed",
    )
    st.markdown("---")
    accounts = get_all_accounts()
    st.markdown(f"**Accounts found:** `{len(accounts)}`")
    for a in accounts:
        v1_tag = "✅ v1" if a["has_v1"] else "❌ v1"
        v2_tag = "✅ v2" if a["has_v2"] else "⬜ v2"
        st.markdown(f"<span class='account-badge'>{a['id']}</span>", unsafe_allow_html=True)
        st.caption(f"{v1_tag}  {v2_tag}")

# ─────────────────────────────────────────────────────────────────────────────
#  Header
# ─────────────────────────────────────────────────────────────────────────────

st.markdown("""
<div class="clara-header">
  <h1>🤖 Clara Agent Pipeline</h1>
  <p>Zero-cost automation · Transcript → Retell AI Voice Agent Config</p>
</div>
""", unsafe_allow_html=True)

# ═════════════════════════════════════════════════════════════════════════════
#  TAB 1 – DASHBOARD
# ═════════════════════════════════════════════════════════════════════════════

if tab_choice == "📊 Dashboard":
    st.subheader("📊 Pipeline Overview")

    # ── Metric cards ──────────────────────────────────────────────────────────
    total     = len(accounts)
    with_v2   = sum(1 for a in accounts if a["has_v2"])
    with_v1   = sum(1 for a in accounts if a["has_v1"])
    unknowns  = sum(
        len(a["v1_memo"].get("questions_or_unknowns", []))
        for a in accounts if a.get("v1_memo")
    )

    c1, c2, c3, c4 = st.columns(4)
    for col, val, label in [
        (c1, total,   "Total Accounts"),
        (c2, with_v1, "v1 Complete"),
        (c3, with_v2, "v2 Onboarded"),
        (c4, unknowns,"Open Questions"),
    ]:
        col.markdown(f"""
        <div class="metric-card">
          <div class="val">{val}</div>
          <div class="lbl">{label}</div>
        </div>""", unsafe_allow_html=True)

    st.markdown("---")

    # ── Summary report ────────────────────────────────────────────────────────
    if SUMMARY_FILE.exists():
        st.subheader("📋 Last Batch Summary")
        report = load_json(SUMMARY_FILE)
        if report:
            ts = report.get("run_timestamp", "")
            try:
                ts = datetime.fromisoformat(ts).strftime("%Y-%m-%d %H:%M UTC")
            except Exception:
                pass
            st.caption(f"Run at: {ts}")
            r1, r2, r3, r4, r5 = st.columns(5)
            for col, key, label in [
                (r1, "processed",                    "Processed"),
                (r2, "accounts_created",             "Created"),
                (r3, "errors",                       "Errors"),
                (r4, "missing_business_hours",       "Missing Hours"),
                (r5, "missing_emergency_definitions","Missing Emerg."),
            ]:
                col.metric(label, report.get(key, 0))
        st.markdown("---")

    # ── Account cards ─────────────────────────────────────────────────────────
    st.subheader("🗂️ Account Details")
    if not accounts:
        st.info("No accounts found in `outputs/accounts/`. Run a pipeline first.")
    else:
        for a in accounts:
            with st.expander(f"🏢 {a['company']}  |  `{a['id']}`", expanded=False):
                tab_v1, tab_v2 = st.tabs(["📋 v1 Configuration", "✨ v2 Onboarded"])
                
                with tab_v1:
                    if a["v1_memo"]:
                        m = a["v1_memo"]
                        col1, col2 = st.columns(2)
                        with col1:
                            st.write(f"**🕐 Hours:** `{json.dumps(m.get('business_hours', 'N/A'))}`")
                            st.write(f"**🌐 Timezone:** `{m.get('timezone', '—')}`")
                            st.write(f"**📍 Address:** `{m.get('office_address', '—')}`")
                        with col2:
                            svcs = m.get("services_supported", [])
                            st.write("**🔧 Services:**")
                            for s in svcs:
                                st.caption(f" • {s}")
                                
                        qs = m.get("questions_or_unknowns", [])
                        if qs:
                            st.warning(f"⚠️ **Open questions ({len(qs)}):**")
                            for q in qs:
                                st.caption(f"  • {q}")
                                
                        st.markdown("---")
                        st.caption("Raw JSON Data")
                        st.json(m, expanded=False)
                    else:
                        st.info("No v1 memo found.")
                        
                with tab_v2:
                    if a["v2_memo"]:
                        m2 = a["v2_memo"]
                        st.success(f"✅ Onboarding Complete (Schema v{m2.get('schema_version', '?')})")
                        st.write(f"**🕐 Updated Hours:** `{json.dumps(m2.get('business_hours', 'N/A'))}`")
                        st.write(f"**📅 Last Updated:** `{m2.get('last_updated', '—')[:10]}`")
                        
                        changelog = ACCOUNTS_DIR / a["id"] / "v2" / "changes.md"
                        if changelog.exists():
                            st.download_button("⬇️ Download changes.md", data=changelog.read_text('utf-8'), file_name=f"{a['id']}_changes.md", key=f"dl_{a['id']}")
                            
                        st.markdown("---")
                        st.caption("Raw JSON Data")
                        st.json(m2, expanded=False)
                    else:
                        st.info("No v2 memo yet. Run Pipeline B to patch.")

# ═════════════════════════════════════════════════════════════════════════════
#  TAB 2 – DIFF VIEWER
# ═════════════════════════════════════════════════════════════════════════════

elif tab_choice == "🔍 Diff Viewer":
    st.subheader("🔍 v1 → v2 Diff Viewer")
    st.caption("Compare Account Memo fields between versions with color-coded highlights.")

    acct_ids = [a["id"] for a in accounts if a["has_v1"] and a["has_v2"]]
    if not acct_ids:
        st.warning("No accounts with both v1 and v2 found. Run Pipeline B first.")
    else:
        selected = st.selectbox("Select Account", acct_ids)
        acct_info = next(a for a in accounts if a["id"] == selected)

        v1 = acct_info["v1_memo"]
        v2 = acct_info["v2_memo"]
        diff = compute_diff(v1, v2)

        # Stats
        added    = [d for d in diff if d["status"] == "added"]
        modified = [d for d in diff if d["status"] == "modified"]
        removed  = [d for d in diff if d["status"] == "removed"]
        same     = [d for d in diff if d["status"] == "same"]

        total_fields = len(diff)
        change_pct = ((len(added) + len(modified) + len(removed)) / total_fields) * 100 if total_fields else 0
        
        st.progress(int(change_pct), text=f"Update Intensity: {change_pct:.1f}% of fields changed during Onboarding")

        s1, s2, s3, s4 = st.columns(4)
        s1.metric("✅ Added",    len(added))
        s2.metric("✏️ Modified", len(modified))
        s3.metric("🗑️ Removed",  len(removed))
        s4.metric("⬜ Unchanged",len(same))

        st.markdown("---")

        # Filter
        show_filter = st.multiselect(
            "Show field types",
            ["added", "modified", "removed", "same"],
            default=["added", "modified", "removed"],
        )

        # Legend
        st.markdown("""
        <div style="display:flex; gap:16px; margin-bottom:16px; font-size:0.82rem;">
          <span style="color:#3fb950">■ Added</span>
          <span style="color:#d29922">■ Modified</span>
          <span style="color:#f85149">■ Removed</span>
          <span style="color:#484f58">■ Unchanged</span>
        </div>""", unsafe_allow_html=True)

        # Diff rows
        for item in diff:
            if item["status"] not in show_filter:
                continue

            css_class = f"field-{item['status']}"
            field     = item["field"]
            status    = item["status"].upper()

            if item["status"] == "added":
                html = f"""
                <div class="{css_class}">
                  <div class="field-key">+ {field} <span style="color:#3fb950;font-size:0.75rem">[{status}]</span></div>
                  <div class="field-val val-new">{val_str(item['v2'])}</div>
                </div>"""
            elif item["status"] == "removed":
                html = f"""
                <div class="{css_class}">
                  <div class="field-key">- {field} <span style="color:#f85149;font-size:0.75rem">[{status}]</span></div>
                  <div class="field-val val-old">{val_str(item['v1'])}</div>
                </div>"""
            elif item["status"] == "modified":
                html = f"""
                <div class="{css_class}">
                  <div class="field-key">~ {field} <span style="color:#d29922;font-size:0.75rem">[{status}]</span></div>
                  <div class="field-val val-old">▶ FROM: {val_str(item['v1'])}</div>
                  <div class="field-val val-new">▶ TO:   {val_str(item['v2'])}</div>
                </div>"""
            else:
                html = f"""
                <div class="{css_class}">
                  <div class="field-key" style="color:#484f58">  {field}</div>
                  <div class="field-val" style="color:#484f58">{val_str(item['v1'])}</div>
                </div>"""

            st.markdown(html, unsafe_allow_html=True)

        # Changelog file reader
        st.markdown("---")
        changelog_path = ACCOUNTS_DIR / selected / "v2" / "changes.md"
        if changelog_path.exists():
            with st.expander("📄 View changes.md (raw)"):
                st.markdown(changelog_path.read_text(encoding="utf-8"))

# ═════════════════════════════════════════════════════════════════════════════
#  TAB 3 – BATCH PROCESSOR
# ═════════════════════════════════════════════════════════════════════════════

elif tab_choice == "⚡ Batch Processor":
    st.subheader("⚡ Batch Processor")

    col_left, col_right = st.columns([1, 1])

    # ── Pipeline A ────────────────────────────────────────────────────────────
    with col_left:
        st.markdown("### 🔵 Pipeline A – Demo Call → v1")
        st.caption("Normalize → Extract → Generate agent spec")

        transcripts = sorted(DATASET_DIR.glob("*.txt")) if DATASET_DIR.exists() else []
        transcripts = [t for t in transcripts if "_normalized" not in t.stem]
        st.info(f"Found **{len(transcripts)}** demo transcript(s) in `dataset/demo_calls/`")

        force_a = st.checkbox("Force overwrite existing outputs", key="force_a")

        if st.button("▶️  Run Pipeline A (All Transcripts)", use_container_width=True, type="primary"):
            if not transcripts:
                st.error("No transcripts found.")
            else:
                log_lines = []
                progress = st.progress(0, text="Starting batch...")
                status_box = st.empty()

                for i, t in enumerate(transcripts):
                    pct = int((i / len(transcripts)) * 100)
                    progress.progress(pct, text=f"Processing {t.name}…")
                    status_box.info(f"⏳ {t.name}")

                    cmd = [sys.executable, str(SCRIPTS_DIR / "batch_process.py"),
                           "--dataset_dir", str(DATASET_DIR),
                           "--output_dir",  str(ACCOUNTS_DIR)]
                    if force_a:
                        cmd.append("--force")
                    rc, out = run_script_live(cmd)
                    log_lines.append(out)
                    break  # batch_process.py processes all at once

                progress.progress(100, text="Done!")
                status_box.success("✅ Batch complete!")
                st.balloons()
                st.toast("🎉 Pipeline A Batch Finished!", icon="✅")

                log_text = "\n".join(log_lines)
                st.markdown('<div class="log-box">' + log_text.replace("\n", "<br>") + '</div>',
                            unsafe_allow_html=True)

                if SUMMARY_FILE.exists():
                    report = load_json(SUMMARY_FILE)
                    if report:
                        st.markdown("**📊 Batch Results:**")
                        rc1, rc2, rc3 = st.columns(3)
                        rc1.metric("Processed",  report.get("processed", 0))
                        rc2.metric("Created",    report.get("accounts_created", 0))
                        rc3.metric("Errors",     report.get("errors", 0))

    # ── Pipeline B ────────────────────────────────────────────────────────────
    with col_right:
        st.markdown("### 🟣 Pipeline B – Onboarding → v2")
        st.caption("Normalize → Patch → Generate → Changelog")

        acct_options = [a["id"] for a in accounts if a["has_v1"]]
        onboard_files = sorted((REPO_ROOT / "dataset" / "onboarding_calls").glob("*.txt")) \
                        if (REPO_ROOT / "dataset" / "onboarding_calls").exists() else []
        onboard_files = [f for f in onboard_files if "_normalized" not in f.stem]

        if not acct_options:
            st.warning("No v1 accounts found. Run Pipeline A first.")
        else:
            sel_acct    = st.selectbox("Account to update", acct_options)
            sel_onboard = st.selectbox(
                "Onboarding transcript",
                [f.name for f in onboard_files] if onboard_files else ["(none found)"]
            )
            force_b = st.checkbox("Force overwrite v2", key="force_b")

            if st.button("▶️  Run Pipeline B", use_container_width=True, type="primary"):
                if not onboard_files or sel_onboard == "(none found)":
                    st.error("No onboarding transcript found in `dataset/onboarding_calls/`")
                else:
                    onboard_path = REPO_ROOT / "dataset" / "onboarding_calls" / sel_onboard
                    v1_memo      = ACCOUNTS_DIR / sel_acct / "v1" / "memo.json"
                    v2_out       = ACCOUNTS_DIR / sel_acct / "v2"
                    norm_out     = str(onboard_path).replace(".txt", "_normalized.txt")

                    steps = [
                        ("Normalize", [sys.executable, str(SCRIPTS_DIR / "normalize_transcript.py"),
                                       "--input", str(onboard_path), "--output", norm_out]),
                        ("Apply Patch", [sys.executable, str(SCRIPTS_DIR / "apply_patch.py"),
                                         "--v1_memo", str(v1_memo),
                                         "--onboarding", norm_out,
                                         "--output_dir", str(v2_out)] + (["--force"] if force_b else [])),
                        ("Generate Agent v2", [sys.executable, str(SCRIPTS_DIR / "generate_agent.py"),
                                               "--memo", str(v2_out / "memo.json"),
                                               "--output_dir", str(v2_out),
                                               "--version", "2.0"] + (["--force"] if force_b else [])),
                        ("Changelog", [sys.executable, str(SCRIPTS_DIR / "changelog.py"),
                                       "--v1", str(v1_memo),
                                       "--v2", str(v2_out / "memo.json"),
                                       "--output", str(v2_out / "changes.md")] + (["--force"] if force_b else [])),
                    ]

                    all_logs = []
                    progress_b = st.progress(0)
                    for i, (label, cmd) in enumerate(steps):
                        progress_b.progress(int((i / len(steps)) * 100), text=f"Running {label}…")
                        rc, out = run_script_live(cmd)
                        all_logs.append(f"[{label}]\n{out}")
                        if rc != 0:
                            st.error(f"❌ {label} failed")
                            break

                    progress_b.progress(100, text="Done!")
                    st.success(f"✅ Pipeline B complete for `{sel_acct}`")
                    st.balloons()
                    st.toast(f"🎉 Successfully Onboarded {sel_acct}!", icon="🚀")

                    log_html = "<br>".join(
                        line for block in all_logs for line in block.split("\n")
                    )
                    st.markdown(f'<div class="log-box">{log_html}</div>', unsafe_allow_html=True)

                    # Show output files
                    st.markdown("**📁 Output files:**")
                    for fname in ["memo.json", "agent_spec.json", "changes.md"]:
                        fp = v2_out / fname
                        exists = "✅" if fp.exists() else "❌"
                        st.caption(f"{exists} `{fp.relative_to(REPO_ROOT)}`")

    # ── Summary report viewer ─────────────────────────────────────────────────
    st.markdown("---")
    st.subheader("📋 Summary Report")
    if SUMMARY_FILE.exists():
        report = load_json(SUMMARY_FILE)
        if report:
            st.json(report)
            if st.download_button(
                "⬇️  Download summary_report.json",
                data=json.dumps(report, indent=2),
                file_name="summary_report.json",
                mime="application/json",
            ):
                pass
    else:
        st.info("No summary report yet. Run Pipeline A batch first.")
