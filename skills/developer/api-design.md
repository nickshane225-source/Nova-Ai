---
name: api-design
description: Design clean, consistent RESTful API endpoints, request/response schemas, validation, and error contracts.
triggers: api design, rest api, endpoint design, api schema, route design, এপিআই ডিজাইন, এন্ডপয়েন্ট
---

## When to use
Use when creating new HTTP endpoints, standardizing JSON schemas, or exposing internal subsystem data to frontend clients.

## Procedure
1. **Define resources and verbs**: Use standard HTTP methods (GET for queries, POST for mutations/actions, DELETE for removals) mapped to plural resources.
2. **Draft request and response schemas**: Design predictable JSON payloads with strict typing, required fields, and default values.
3. **Specify input validation rules**: Reject malformed parameters early with clear 400 Bad Request messages before triggering business logic.
4. **Establish consistent error contracts**: Return standard error shapes (`{"error": "message", "code": "CODE"}`) with semantic HTTP status codes.
5. **Handle idempotency and pagination**: Ensure retry safety on critical operations and use offset/limit pagination on unbounded collections.
6. **Enforce local-only network protection**: Guard local APIs with `_local_only()` checks inspecting Host and Origin headers to prevent DNS rebinding.

## Checklist
- [ ] Does every endpoint return standard JSON with accurate status codes?
- [ ] Are parameter types and ranges strictly validated before execution?
- [ ] Is local-only origin validation enforced on every sensitive route?
- [ ] Is the endpoint documented in the blueprint table?

## Output format
Markdown table specifying Method, Endpoint, Request Payload, Response Schema, and Description.

## Example
| Method | Endpoint | Request Payload | Response Schema | Description |
| :--- | :--- | :--- | :--- | :--- |
| `GET` | `/api/skills` | `?mode=developer\|cyber` | `{"mode": str, "skills": list}` | Returns parsed skills metadata for the mode. |
| `POST` | `/api/chat` | `{"message": str, "mode": str}` | `{"reply": str, "actions": list}` | Executes message turn with skill injection. |
