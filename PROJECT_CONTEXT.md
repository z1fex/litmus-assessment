# PROJECT_CONTEXT.md: Build GTM Data Pipeline for Legal AI Startup

## 1. Project Overview
- **Objective**: The goal of this project is to build a robust, end-to-end Go-To-Market (GTM) data infrastructure for a legal AI startup. It involves creating a pipeline that automates lead ingestion, enrichment, scoring, routing, and experiment assignment.
- **Problem Solved**: It solves the manual overhead of identifying and qualifying law firm leads across multiple regions (US, Australia, Asia). It also addresses common real-world data issues such as duplicate records, inconsistent API schemas, rate limiting, and intermittent server failures.
- **End Deliverables**:
  - A fully functional Python-based pipeline (`pipeline.py`) that handles the entire lifecycle of a lead.
  - Integration with a mock API server that simulates imperfect data sources.
  - A comprehensive write-up (`WRITEUP.md`) detailing the architectural choices, trade-offs, and future improvements.

## 2. Project Structure
The project is located in `c:\Users\prosa\Desktop\LITMUS\build-gtm-data-pipeline-for-legal-ai-startup` and contains the following files and folders:

| File/Folder | Description |
| :--- | :--- |
| `pipeline.py` | The main orchestrator that manages the flow of data through all stages of the GTM workflow. |
| `enricher.py` | Handles communication with the mock API to fetch firmographics and contact details, including retry logic and schema normalization. |
| `scorer.py` | Evaluates leads against the Ideal Customer Profile (ICP) based on size, practice areas, and location. |
| `router.py` | Categorizes qualified leads into priorities (e.g., "high_priority", "nurture") for appropriate follow-up. |
| `experiment.py` | Uses hashing to assign leads to A/B testing variants (e.g., email campaign subject lines). |
| `webhook.py` | Delivers lead and campaign data to downstream systems like CRMs and email platforms. |
| `mock_server.py` | A FastAPI server that simulates the external data sources and downstream systems (do not modify). |
| `config.yaml` | Contains scoring weights, thresholds, API endpoints, and experiment settings. |
| `requirements.txt` | Lists the Python dependencies required for the project (FastAPI, PyYAML, requests, etc.). |
| `setup.sh` | A bash script for setting up the Python virtual environment and installing dependencies. |
| `WRITEUP.md` | A document detailing the implementation approach and technical decisions. |
| `README.md` | The original assessment documentation containing instructions and requirements. |
| `venv/` | (Directory) The local Python virtual environment. |
| `.litmus/` | (Directory) Litmus configuration/state directory. |

### Overall Architecture
The architecture follows a modular service-oriented pattern. The `pipeline.py` act as the hub, delegating specific responsibilities to specialized classes (`Enricher`, `ICPScorer`, `LeadRouter`, etc.). This separation of concerns allows for easier testing and maintenance.

## 3. Tasks & Requirements
### Functional Requirements
1.  **Pipeline Orchestration**: Implement a main pipeline function that processes firms from start to finish.
2.  **API Integration**: Build robust clients that handle 429 rate limiting, exponential backoff for 500s, and connection timeouts.
3.  **Data Enrichment**: Fetch and normalize firmographic data (employee count, practice areas) and contact info.
4.  **Deduplication**: Prevent duplicate processing of the same firm (e.g., by domain matching).
5.  **ICP Scoring**: Quantify firm quality based on configurable weights and thresholds.
6.  **Lead Routing**: Route leads into actionable categories.
7.  **Experiment Assignment**: Assign A/B test variants to leads.
8.  **Webhook Integration**: Deliver payloads to CRM and email systems with error handling.
9.  **Error Handling**: Implement comprehensive logging and recovery for system failures.

### Evaluation & Acceptance Criteria
- **Resilience**: How well the pipeline handles API failures (rate limits, timeouts, server errors).
- **Correctness**: Proper normalization of inconsistent schemas (e.g., `num_lawyers` vs `lawyer_count`).
- **Cleanliness**: Use of modular design and appropriate types/documentation.
- **Completeness**: Implementation of all 9 functional requirements.

### Constraints
- **Time/Scope**: This is a coding assessment; solutions should prioritize robustness and clarity over high-throughput concurrency (unless explicitly needed).
- **API Limits**: The mock server enforces a 20 requests/minute rate limit.
- **Technology**: Requires Python 3.9+ and specified libraries in `requirements.txt`.

## 4. Tech Stack
- **Language**: Python 3.14.2 (as installed on system).
- **Web Framework**: FastAPI (used by `mock_server.py`).
- **API Client**: `requests` (used in `enricher.py` and `webhook.py`).
- **Data Serialization**: YAML (via `pyyaml`) and JSON.
- **Validation**: Pydantic (used by mock server).
- **APIs/Services Mentioned**:
  - `GET /firms`: Paginated list of firms.
  - `GET /firms/{id}/firmographic`: Firmographic enrichment.
  - `GET /firms/{id}/contact`: Contact data enrichment.
  - `POST /webhooks/crm`: CRM delivery.
  - `POST /webhooks/email`: Email platform delivery.

## 5. Data & Schema
### Input Data Structures (from `mock_server.py`)
- **Firm (Basic)**: `{"id": str, "name": str, "domain": str}`.
- **Firmographic (Extended)**: `{"firm_id": str, "name": str, "domain": str, "country": str, "region": str, "practice_areas": list[str], "num_lawyers" | "lawyer_count": int}`.
- **Contact**: `{"firm_id": str, "name": str, "title": str, "phone": str, "email": str | None, "linkedin_url": str | None}`.

### Expected Pipeline Output/Payloads
- **CRM Lead Payload**: Includes IDs, names, domains, ICP scores, route categories, and contact info.
- **Email Campaign Payload**: Includes the assigned experiment variant and target email address.

## 6. Current State
- **Status**: **Completed**.
- **Scaffolded**: The initial boilerplates for all files were present but empty/stubbed.
- **Built**:
  - `enricher.py`: Fully implemented with retries and 429 handling.
  - `scorer.py`: Implemented with weighted scoring logic.
  - `router.py`: Categorizes leads based on score thresholds.
  - `experiment.py`: Uses deterministic MD5 hashing for assignment.
  - `webhook.py`: Implemented with server-side error recovery and specific endpoints.
  - `pipeline.py`: Fully orchestrated to process all 55 firms across paginated results.
- **Missing/Errors**: No known errors at current implementation. The pipeline has been verified by running against the live mock server.

## 7. Key Instructions
### Original README Content (Word for Word)
```markdown
# Build GTM Data Pipeline for Legal AI Startup

## Overview

You're a full-stack engineer at a legal AI startup building the GTM data infrastructure to acquire midsize law firm clients across the US, Australia, and Asia. This pipeline will power lead acquisition from ingestion through experiment assignment, ensuring a seamless integration of various data sources and systems to optimize customer acquisition strategies.

## Problem Statement

Build an end-to-end GTM data pipeline that integrates API data sources, enriches lead information, scores prospects against ideal customer profiles, routes qualified leads, and assigns experiment variants. This assessment will evaluate not only your engineering capabilities but also your understanding of systems integration, data flow management, and the ability to handle real-world API challenges.

## Getting Started

### Prerequisites

- Python 3.9+

### Setup Instructions

Run the setup script from the project root to get started:

```bash
./setup.sh
```

Any API tokens or additional information can be found on the **Assessment Instruction Page** where you downloaded this assessment.

### Running

Start the mock server in one terminal:

```bash
python mock_server.py
```

Run your pipeline in another terminal.

## Project Structure

```
pipeline.py       — main pipeline orchestrator
enricher.py       — firmographic and contact data enrichment
scorer.py         — ICP scoring
router.py         — lead routing
44: experiment.py     — A/B experiment assignment
45: webhook.py        — webhook delivery to downstream systems
mock_server.py    — fully working mock API server (do not modify)
config.yaml       — pipeline configuration (weights and thresholds are yours to set)
```

## Requirements

### Functional Requirements

1. **Pipeline Orchestration**: Implement a main pipeline function that processes firms through the complete GTM workflow, handling configuration from YAML files.

2. **API Integration**: Build robust API clients that handle rate limiting (429 errors), implement exponential backoff retry logic, and gracefully handle network timeouts and connection errors.

3. **Data Enrichment**: Fetch firmographic data (employee count, practice areas) and contact information for each firm, handling cases where enrichment APIs return partial or missing data.

4. **Deduplication**: Identify and handle duplicate firms based on domain, name similarity, and other identifying characteristics to prevent duplicate processing.

5. **ICP Scoring**: Score firms against ideal customer profile criteria (firm size, practice areas, geographic regions) with configurable weights and thresholds.

6. **Lead Routing**: Route leads into categories based on their score and firm data.

7. **Experiment Assignment**: Assign leads to email campaign variants (A/B tests) with proper randomization.

8. **Webhook Integration**: Fire webhooks to downstream systems (CRM, email platforms) with proper error handling and retry logic for failed deliveries.

9. **Error Handling**: Implement error handling for API failures, data validation errors, and system exceptions with appropriate logging and recovery strategies.

### Mock Server

The mock server (`mock_server.py`) is fully working and simulates real-world API imperfections:

- **GET /firms** — paginated list of 55 law firms (includes near-duplicates). ~10% of requests return 500 errors. Rate limit enforced at 20 requests/minute (returns 429 with `Retry-After` header when exceeded).
- **GET /firms/{id}/firmographic** — firmographic data. ~20% of responses have missing fields. Schema is occasionally inconsistent (e.g. `num_lawyers` vs `lawyer_count`).
- **GET /firms/{id}/contact** — contact info. ~30% of contacts have null email or null LinkedIn URL.
- **POST /webhooks/crm** — accepts lead payloads. ~5% chance of failure.
- **POST /webhooks/email** — accepts campaign payloads. ~5% chance of failure.

API docs are available at `http://localhost:8000/docs` when the server is running.

Do not modify the mock server. Your pipeline needs to handle its behavior as-is.

### Deliverables

1. **Working pipeline** — implements all functional requirements above
2. **WRITEUP.md** — a short write-up explaining your approach, trade-offs, and what you'd do differently with more time. Reference specific parts of your code so reviewers can follow your reasoning.

## Submission Guidelines

Upload a zip file of your completed assessment to the assessment platform.

---
**Questions?** Contact us at founders@litmus.build
```
