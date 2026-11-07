---
name: architecture-design
description: Design system components, module boundaries, data flows, and trade-offs before implementation.
triggers: architecture, architecture design, system design, architectural decision, component design, data flow design, আর্কিটেকচার, নকশা
---

## When to use
Use when designing a new subsystem, restructuring existing services, or deciding between architectural patterns for scalability and simplicity.

## Procedure
1. **Clarify requirements and constraints**: Document functional goals, traffic scale, latency requirements, and system limits (e.g. standard library only).
2. **List components and data flow**: Diagram the interacting layers (frontend HUD, background engines, persistent storage) and data contracts.
3. **Compare options with trade-offs**: Evaluate 2-3 architectural approaches against complexity, maintainability, and operational overhead.
4. **Select approach and record decision**: Create an Architecture Decision Record (ADR) noting Context, Decision, and Consequences.
5. **Define module boundaries**: Ensure loose coupling and clean interfaces so components can be tested and modified in isolation.
6. **Identify failure modes and risks**: Detail fallback mechanisms for component timeouts, process crashes, or corrupt data.

## Checklist
- [ ] Are architectural boundaries strictly enforced with clear interfaces?
- [ ] Does the design satisfy Nova's zero-dependency constraint?
- [ ] Are state transitions and single points of failure documented?
- [ ] Can every component be independently unit-tested?

## Output format
- **System Overview**: High-level component summary and interaction flow.
- **Architectural Decision (ADR)**: Context, Selected Option, Trade-offs.
- **Module Interface Map**: Public APIs and isolation boundaries.
- **Risk & Failure Matrix**: Failure condition, Detection, Mitigation.

## Example
```markdown
### ADR: In-Memory Skills Cache with Mtime Invalidation
- **Context**: Frequent disk reads on every chat turn slow down response times.
- **Decision**: Cache parsed markdown skills in memory; check directory mtime before re-reading.
- **Trade-off**: Small memory footprint (~100KB) in exchange for zero disk I/O on steady turns.
- **Consequence**: Sub-millisecond skill retrieval while preserving instant live edits.
```
