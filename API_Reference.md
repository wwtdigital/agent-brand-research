# API (Application Programming Interface) Reference

## Endpoints

| Method | Path | What it does |
|--------|------|--------------|
| `POST` | `/api/smart/launch` | Creates a SMART (Substitutable Medical Applications, Reusable Technologies)-on-FHIR (Fast Healthcare Interoperability Resources) session (`userId`, `patientMrn`, `encounterId`, `tenantId`) — entry point for Cerner-launched contexts |
| `GET` | `/api/smart/session/{sessionId}` | Retrieves an existing session by ID |
| `POST` | `/api/gemini/query` | Unified orchestrator — resolves which capability to use (Policy vs Insights) by keyword-matching the message, applies guardrails, dispatches, and returns answer + citations |
| `POST` | `/api/policy/ask` | Direct endpoint for Policy & Procedure Q&A (Question and Answer) — bypasses capability resolution |
| `POST` | `/api/insights/ask` | Direct endpoint for analytics/BigQuery (Google's cloud data warehouse) insights — currently stubbed |
| `GET` | `/health` | Health probe |
| `GET` | `/` | Lists available routes |

---

## Capabilities

### Policy & Procedure Q&A (Question and Answer)
The working feature. Takes a question, sends it to Google Cloud Discovery Engine (Vertex AI (Artificial Intelligence) Search), and returns a grounded answer with document citations. Backed by an indexed policy/procedure data store.

### Clinical Insights (stub)
Designed to query a curated BigQuery dataset via a Vertex AI Data Agent (natural-language analytics). Not yet implemented — returns placeholder responses.

### SMART (Substitutable Medical Applications, Reusable Technologies)-on-FHIR (Fast Healthcare Interoperability Resources) Session Management
Accepts a launch context from Cerner/PowerChart (user, patient, encounter, tenant) and mints a session ID that downstream calls carry for identity and audit.

---

## Security Pipeline (in the orchestrator)

Every `/api/gemini/query` call runs through:

1. Session validation
2. Capability authorization (stub, currently permissive)
3. Model Armor prompt inspection
4. Service call
5. Model Armor response inspection
6. Cloud DLP (Data Loss Prevention) PHI (Protected Health Information)/PII (Personally Identifiable Information) scan (stubbed)

> Both guardrails fail-open for the POC (Proof of Concept).

---

## What's Real vs. Stubbed

| Component | Status |
|-----------|--------|
| Discovery Engine calls | ✅ Real |
| Session creation | ✅ Real |
| Model Armor wiring (fails open if template not configured) | ✅ Real |
| Audit logging | ✅ Real |
| DLP (Data Loss Prevention) inspector | 🔲 Stubbed |
| Capability authorizer | 🔲 Stubbed |
| Insights/BigQuery agent | 🔲 Stubbed |
| Cerner FHIR (Fast Healthcare Interoperability Resources) token exchange (assumed to have happened upstream) | 🔲 Stubbed |

---

## Architecture Overview

This API (Application Programming Interface) is designed to sit between a Cerner SMART (Substitutable Medical Applications, Reusable Technologies) launch and Google Cloud AI (Artificial Intelligence) services, acting as a secure orchestration layer.
