# Clara Agent Pipeline

A zero-cost, locally reproducible automation pipeline that converts customer call transcripts into structured Retell AI voice agent configurations. Built for the Clara Answers intern assignment.

## 🏗 Architecture & Data Flow

The system processes raw transcripts through a two-phase pipeline using a robust rule-based extraction engine with an optional local LLM fallback. This ensures deterministic outputs while completely avoiding mandatory paid API dependencies.

```text
[ Raw Transcript (.txt) ]
       │
       ▼
[ Normalization Layer ] ── Removes fillers, normalizes times/days
       │
       ▼
[ Extraction Engine ] ───── Regex/Heuristic rules (fallback: Local Ollama)
       │
       ▼
[ Account Memo JSON ] ───── Structured intermediate representation
       │
       ▼
[ Patch/Merge Engine ] ──── (Pipeline B only) Field-level diffing & deep merge
       │
       ▼
[ Prompt Generator ] ────── Assembles Retell Agent Spec (v1 or v2)
```

### Pipelines

*   **Pipeline A (Demo Call):** Ingests an initial discovery call transcript, extracts core business logic (hours, services, routing rules, emergency definitions), and generates a `v1` `.json` configuration and Retell agent spec.
*   **Pipeline B (Onboarding Update):** Ingests an onboarding call transcript, extracts requested changes, applies a deep-merge patch against the `v1` configuration, and produces a `v2` configuration alongside a detailed field-level `changes.md` changelog.

---

## 🚀 How to Run Locally

### Prerequisites
*   Python 3.9+
*   Node.js (for n8n, optional but recommended)
*   *Optional:* [Ollama](https://ollama.ai/) running locally with `llama3` for LLM fallback.

### Environment Setup

```bash
git clone <repository-url>
cd clara-agent-pipeline
python -m venv venv

# Windows
venv\Scripts\Activate.ps1
# Mac/Linux
source venv/bin/activate

pip install -r requirements.txt
```

### Option 1: Pure CLI Execution (No n8n Required)

**Run Pipeline A (Single Transcript):**
```bash
python scripts/normalize_transcript.py --input dataset/demo_calls/demo_transcript_001.txt --output dataset/demo_calls/demo_transcript_001_normalized.txt
python scripts/extract_memo.py --input dataset/demo_calls/demo_transcript_001_normalized.txt --account_id account_001 --output_dir outputs/accounts/account_001/v1
python scripts/generate_agent.py --memo outputs/accounts/account_001/v1/memo.json --output_dir outputs/accounts/account_001/v1
```

**Run Pipeline B (Patch Update):**
```bash
python scripts/normalize_transcript.py --input dataset/onboarding_calls/onboarding_001.txt --output dataset/onboarding_calls/onboarding_001_normalized.txt
python scripts/apply_patch.py --v1_memo outputs/accounts/account_001/v1/memo.json --onboarding dataset/onboarding_calls/onboarding_001_normalized.txt --output_dir outputs/accounts/account_001/v2 --force
python scripts/generate_agent.py --memo outputs/accounts/account_001/v2/memo.json --output_dir outputs/accounts/account_001/v2 --version 2.0 --force
python scripts/changelog.py --v1 outputs/accounts/account_001/v1/memo.json --v2 outputs/accounts/account_001/v2/memo.json --output outputs/accounts/account_001/v2/changes.md --force
```

**Batch Processing:**
Runs Pipeline A over all transcripts in a directory, outputting a summary report to `outputs/`.
```bash
python scripts/batch_process.py --dataset_dir dataset/demo_calls --output_dir outputs/accounts
```

### Option 2: Streamlit Dashboard

A visual UI for monitoring pipeline runs, inspecting generated JSONs, and viewing color-coded diffs.
```bash
streamlit run dashboard.py
```
*Open `http://localhost:8501` in your browser.*

---

## ⚙️ n8n Workflow Instructions

The repository includes a pre-configured n8n workflow (`workflows/n8n_workflow.json`) that uses HTTP Request nodes to orchestrate the pipeline asynchronously.

![n8n Workflow Preview](n8n_workflow.png)

1.  **Start the Local API Server:**
    The n8n workflow communicates with the python scripts via a lightweight local server to bypass sandbox limitations.
    ```bash
    python scripts/pipeline_server.py --port 8765
    ```
2.  **Start n8n:**
    ```bash
    npm install -g n8n
    n8n start
    ```
3.  **Import & Execute:**
    *   Open `http://localhost:5678`.
    *   Click **Add Workflow** -> **Import from File** and select `workflows/n8n_workflow.json`.
    *   Click **Execute Workflow** on either the Pipeline A or Pipeline B manual trigger node.

---

## 📂 Dataset Injection

To process your own calls:
1.  Drop raw `.txt` transcript files into `dataset/demo_calls/` (for Pipeline A) or `dataset/onboarding_calls/` (for Pipeline B).
2.  Run the batch processor or trigger the pipeline via CLI/n8n pointing to your new file paths. The system will automatically generate safe `account_id` slugs based on extracted company names.

---

## 💾 Output Storage

All generated artifacts are deterministically written to the `outputs/` directory.

```text
outputs/
├── summary_report.json            # Batch metrics
└── accounts/
    └── <account_id>/
        ├── v1/
        │   ├── memo.json          # Intermediate structured data
        │   └── agent_spec.json    # Retell-ready system prompt config
        └── v2/
            ├── memo.json
            ├── agent_spec.json
            └── changes.md         # Field-level diff (Markdown)
```

---

## ⚠️ Known Limitations

*   **Extraction Rigidity:** The rule-based regex extraction is tuned for specific conversational patterns (e.g., standard business hour formats). Highly unstructured or colloquial phrasing may fail rule-checks and fall back to the `questions_or_unknowns` unmapped list.
*   **Idempotency Overwrites:** While the CLI supports `--force` for overwrites, running without it simply skips existing directories. Advanced state-locking is not implemented.
*   **English-Only:** Extraction rules currently assume English-language transcripts.
*   **No Audio Processing:** Expects pre-transcribed text. Diarization errors in the source text can degrade extraction accuracy.

---

## 🚀 Improvements Given Production Access

If provided with production resources (Cloud infrastructure, paid APIs, DB access), I would implement the following architectural upgrades:

1.  **State-of-the-Art LLM Extraction:** Replace regex rules with structured JSON-mode output from a frontier model (GPT-4o or Claude 3.5 Sonnet) combined with `instructor` or `pydantic` for guaranteed schema validation.
2.  **Audio Ingestion:** Integrate a live Whisper API (e.g., Deepgram) to accept raw `.mp3`/`.wav` call recordings and perform speaker diarization on the fly.
3.  **Cloud Native Orchestration & Storage:** Move from the local filesystem and n8n to AWS Step Functions or Temporal.io, persisting outputs to Amazon S3 and caching active memo states in PostgreSQL/DynamoDB.
4.  **Retell API Integration:** Automate the final mile by using the `agent_spec.json` to programmatically provision/update the agent directly via the Retell REST API instead of a manual UI import.
5.  **Human-in-the-Loop (HITL) UI:** Enhance the Streamlit dashboard to allow operations teams to manually approve, edit, or append to `questions_or_unknowns` before finalizing the `agent_spec.json`.
