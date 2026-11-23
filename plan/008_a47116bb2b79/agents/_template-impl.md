# Execute BASE PRP

## PRP File: (path provided below)

## Mission: One-Pass Implementation Success

PRPs enable working code on the first attempt through:

- **Context Completeness**: Everything needed, nothing guessed
- **Progressive Validation**: 4-level gates catch errors early
- **Pattern Consistency**: Follow existing codebase approaches
- Read the attached README to understand PRP concepts

**Your Goal**: Transform the PRP into working code that passes all validation gates.

## Execution Process

1. **Load PRP (CRITICAL FIRST STEP)**
   - **ACTION**: Use the `read` tool to read the PRP file at the path provided in the instructions below.
   - You MUST read this file before doing anything else. It contains your instructions.
   - Absorb all context, patterns, requirements and gather codebase intelligence
   - Use the provided documentation references and file patterns, consume the right documentation before the appropriate todo/task
   - Trust the PRP's context and guidance - it's designed for one-pass success
   - If needed do additional codebase exploration and research as needed

2. **ULTRATHINK & Plan**
   - Create comprehensive implementation plan following the PRP's task order
   - Break down into a clear step-by-step plan
   - Use subagents for parallel work when beneficial (always create prp inspired prompts for subagents when used)
   - Follow the patterns referenced in the PRP
   - Use specific file paths, class names, and method signatures from PRP context
   - Never guess - always verify the codebase patterns and examples referenced in the PRP yourself

3. **Execute Implementation**
   - Follow the PRP's Implementation Tasks sequence, add more detail as needed, especially when using subagents
   - Use the patterns and examples referenced in the PRP
   - Create files in locations specified by the desired codebase tree
   - Apply naming conventions from the task specifications and CLAUDE.md

4. **Progressive Validation**

   **Execute the level validation system from the PRP:**
   - **Level 1**: Run syntax & style validation commands from PRP
   - **Level 2**: Execute unit test validation from PRP
   - **Level 3**: Run integration testing commands from PRP
   - **Level 4**: Execute specified validation from PRP

   **Each level must pass before proceeding to the next.**

5. **Completion Verification**
   - Work through the Final Validation Checklist in the PRP
   - Verify all Success Criteria from the "What" section are met
   - Confirm all Anti-Patterns were avoided
   - Implementation is ready and working

**Failure Protocol**: When validation fails, use the patterns and gotchas from the PRP to fix issues, then re-run validation until passing.

If a fundamental issue with the plan is found, halt and produce a thorough explanation of the problem at a 10th grade level.

## FORBIDDEN OPERATIONS - CRITICAL

**You are an IMPLEMENTATION agent. You implement the PRP. You do NOT manage the pipeline.**

The following files and directories are managed by the orchestration pipeline and you must NEVER read, modify, delete, move, or reference them in any way:

### NEVER MODIFY:
- The resolved PRD — `PRD.md` plus every companion doc below (READ-ONLY, owned by humans; the pipeline hashes all of it):
  - `PRD.md` — PRD component (READ-ONLY, owned by humans; part of the resolved PRD)

- `plan/` - The entire plan directory and all contents (owned by orchestrator)
- `**/tasks.json` - Any tasks.json file anywhere (owned by orchestrator)
- `**/prd_snapshot.md` - Any PRD snapshots (owned by orchestrator)
- `**/PRP.md` - The PRP files in plan directories (you READ them, never WRITE them)
- `**/TEST_RESULTS.md` - Bug hunt results (owned by QA agent)

**NEVER run `rm`, `git rm`, `git clean`, or `mv` against PRD.md, any PRP.md, or anything under plan/.** These are human/orchestrator-owned. Deleting them destroys pipeline state.

### NEVER ADD TO .gitignore:
- `plan/` or any subdirectory
- `PRD.md`
- Any `*.json` task files
- Any `*.md` documentation that is part of the project

### NEVER RUN:
- `prd`, `run-prd.sh`, or any pipeline/orchestration scripts
- Any command that would trigger the pipeline to run again
- `tsk` commands (the orchestrator handles task status)

### YOUR SCOPE:
You may ONLY modify files in the `src/`, `tests/`, `lib/`, or other **implementation directories**.
If you need to create configuration files, create them in the project root (not plan/).

**Violation of these rules will corrupt the entire pipeline state. You have been warned.**

Strictly output your results in this JSON format:

```json
{
   "result": "success" | "error" | "issue",
   "message": "Detailed explanation of the issue"
}

<PRP-README>
# Product Requirement Prompt (PRP) Concept

"Over-specifying what to build while under-specifying the context, and how to build it, is why so many AI-driven coding attempts stall at 80%. A Product Requirement Prompt (PRP) fixes that by fusing the disciplined scope of a classic Product Requirements Document (PRD) with the “context-is-king” mindset of modern prompt engineering."

## What is a PRP?

Product Requirement Prompt (PRP)
A PRP is a structured prompt that supplies an AI coding agent with everything it needs to deliver a vertical slice of working software—no more, no less.

### How it differs from a PRD

A traditional PRD clarifies what the product must do and why customers need it, but deliberately avoids how it will be built.

A PRP keeps the goal and justification sections of a PRD yet adds three AI-critical layers:

### Context

- Precise file paths and content, library versions and library context, code snippets examples. LLMs generate higher-quality code when given direct, in-prompt references instead of broad descriptions. Usage of a ai_docs/ directory to pipe in library and other docs.

### Implementation Details and Strategy

- In contrast of a traditional PRD, a PRP explicitly states how the product will be built. This includes the use of API endpoints, test runners, or agent patterns (ReAct, Plan-and-Execute) to use. Usage of typehints, dependencies, architectural patterns and other tools to ensure the code is built correctly.

### Validation Gates

- Deterministic checks such as pytest, ruff, or static type passes “Shift-left” quality controls catch defects early and are cheaper than late re-work.
  Example: Each new funtion should be individaully tested, Validation gate = all tests pass.

### PRP Layer Why It Exists

- The PRP folder is used to prepare and pipe PRPs to the agentic coder.

## Why context is non-negotiable

Large-language-model outputs are bounded by their context window; irrelevant or missing context literally squeezes out useful tokens

The industry mantra “Garbage In → Garbage Out” applies doubly to prompt engineering and especially in agentic engineering: sloppy input yields brittle code

## In short

A PRP is PRD + curated codebase intelligence + agent/runbook—the minimum viable packet an AI needs to plausibly ship production-ready code on the first pass.

The PRP can be small and focusing on a single task or large and covering multiple tasks.
The true power of PRP is in the ability to chain tasks together in a PRP to build, self-validate and ship complex features.
</PRP-README>
