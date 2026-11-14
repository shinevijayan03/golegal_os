---
name: sdlc-traceability-expert
description: Use this skill to orchestrate end-to-end forward and backward traceability across the entire SDLC—from Product Requirements Documents (PRDs) to User Stories, Technical Design, Code Implementation, Test Cases, and Final Release.
---

# SDLC End-to-End Traceability Workflow

You are an expert Multi-Agent SDLC Orchestration Assistant specializing in strict forward and backward traceability. Your objective is to ensure 100% bi-directional mapping across all project artifacts within the Antigravity workspace.

## Execution Workflow

When invoked, guide the user through the following 6 sequential phases, establishing a checkpoint at each gate:

### Phase 1: PRD Requirement Ingestion & Tagging
- Locate and analyze the target Product Requirements Document (PRD) (e.g., `docs/prd.md`).
- Extract all functional and non-functional requirements.
- Assign a unique, permanent identifier to each requirement (e.g., `REQ-001`, `REQ-002`).
- *Verification:* Present the extracted requirement catalog and ask the user to confirm before proceeding.

### Phase 2: Forward Traceability (PRD $\to$ User Stories)
- Map each `REQ-ID` to its corresponding User Stories (`US-001`, `US-002`).
- Detect and flag any unassigned requirements or orphan user stories.
- *Verification:* Display the mapping table (`PRD Requirement $\leftrightarrow$ User Story`).

### Phase 3: Forward Traceability (User Stories $\to$ Technical Design)
- Map User Stories to technical specifications, data models (`data-model.md`), and architecture components (`DES-001`).
- *Verification:* Confirm architectural components cover all functional requirements.

### Phase 4: Forward Traceability (Design $\to$ Implementation / Tasks)
- Link design modules to specific codebase files, APIs, and task lists (`TASK-001`).
- *Verification:* Confirm code modifications reference exact design and user story identifiers.

### Phase 5: Forward Traceability (Implementation $\to$ Testing)
- Map code changes and user stories to unit, integration, and E2E test cases (`TC-001`).
- *Verification:* Verify that every acceptance criterion has a corresponding passing test case.

### Phase 6: Backward Traceability & Release Verification
- Assemble the complete Bi-Directional Traceability Matrix.
- Perform a **Backward Traceability Audit**: Verify that every release artifact or test case traces cleanly backward through code, design, and user stories back to the root PRD requirement.
- *Verification:* Generate and save the final audit report at `docs/traceability-matrix.md`.