# Serpnex Project Instructions

## Source of Truth

* Review all project files before making decisions.
* The Product Design Brief is the primary source of truth.
* The Design System and Implementation Handoff define the approved UI/UX.
* Never ignore existing documentation.

## Development Philosophy

* Build for production quality.
* Prioritize correctness, maintainability, scalability, and reliability over speed.
* Challenge assumptions when necessary.
* Do not implement features that are not clearly justified.
* Prefer simple solutions over unnecessary complexity.

## Architecture Rules

* Maintain a modular monolith architecture unless there is a strong reason to split services.
* Avoid premature microservices.
* Keep clear separation between:

  * Frontend
  * Backend
  * Analysis Engine
  * Data Layer
* All architectural decisions must be documented.

## Confidence Rule

* Never proceed when confidence is below 70%.
* If confidence drops below 70%:

  * Stop implementation.
  * Explain missing information.
  * Explain risks.
  * Request clarification.

## Documentation Requirements

Documentation is mandatory.

Maintain and continuously update:

* /docs/architecture.md
* /docs/decisions.md
* /docs/progress.md
* /docs/changelog.md

After every meaningful task:

* Update documentation.
* Update progress tracking.
* Update changelog.

## Decision Logging

For every important decision record:

* Date
* Context
* Decision
* Reasoning
* Alternatives considered
* Risks
* Impact

## Git Workflow

* Commit frequently.
* Do not accumulate large amounts of uncommitted work.
* Every completed milestone must be committed.
* Push completed work to GitHub regularly.
* Use clear and descriptive commit messages.

## Context Management

Monitor project context continuously.

If context approaches 70% utilization:

* Stop implementation.
* Update documentation.
* Commit all changes.
* Push to GitHub.
* Create a recovery summary.
* Record the current state of the project.

Never allow critical project knowledge to exist only inside chat history.

## Recovery Requirements

At any moment another engineer should be able to:

* Read the documentation.
* Read the decision log.
* Read the progress file.

And continue development without previous chat history.

## Quality Standards

Before implementing major features:

* Create a short implementation plan.
* Identify risks and dependencies.
* Explain tradeoffs when multiple options exist.

After implementing major features:

* Summarize changes.
* Summarize risks.
* Summarize next steps.

## Product Focus

The Bottleneck Engine is the core product value.

When tradeoffs exist:

* Prioritize verdict quality.
* Prioritize reasoning quality.
* Prioritize accuracy over feature count.

Do not add complexity that does not improve verdict quality.

## MVP Discipline

Do not expand scope without documenting the reason.

Avoid unnecessary features until the core Bottleneck Engine is validated with real-world data.

The goal is to build a successful product, not simply complete tasks.
