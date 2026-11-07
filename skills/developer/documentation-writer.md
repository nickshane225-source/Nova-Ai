---
name: documentation-writer
description: Write clear, audience-focused technical documentation, READMEs, API tables, and architecture overviews.
triggers: documentation, write docs, readme, api documentation, changelog, technical writing, ডকুমেন্টেশন, বিবরণ
---

## When to use
Use when releasing new features, documenting architectural patterns, updating README files, or producing developer guides.

## Procedure
1. **Identify the primary audience**: Tailor tone, depth, and terminology to the intended reader (end-user, maintainer, or automated agent).
2. **Structure the README cleanly**: Provide a 1-sentence value proposition, rapid installation steps, running instructions, and configuration details.
3. **Document API endpoints in structured tables**: Specify HTTP verbs, URL routes, required request JSON schemas, and response formats.
4. **Draft architecture blueprints with diagrams**: Include visual flowcharts (Mermaid syntax) displaying component relationships and data paths.
5. **Provide runnable, validated examples**: Test all code snippets, CLI commands, and tag examples to ensure they run without modification.
6. **Maintain living documentation**: Update docs simultaneously with code changes; remove obsolete flags or outdated API parameters.

## Checklist
- [ ] Are all prerequisite tools, versions, and installation steps stated explicitly?
- [ ] Do all example code blocks execute successfully without errors?
- [ ] Are endpoint tables updated with current parameter names and types?
- [ ] Are diagrams rendered using valid Markdown and Mermaid syntax?

## Output format
- **Document Header**: Title, target audience, version/date.
- **Specification Sections**: Architecture, setup, configuration.
- **Reference Table**: Parameters, endpoints, or skill syntax.

## Example
```markdown
## Configuration Reference (`data/config.json`)
| Key | Type | Default | Description |
| :--- | :--- | :--- | :--- |
| `provider` | `string` | `"openai"` | LLM provider (`openai`, `claude`, `gemini`, `ollama`). |
| `language` | `string` | `"en-US"` | Primary speech recognition and TTS language. |
| `character`| `string` | `"jarvis"` | Active character personality persona. |
```
