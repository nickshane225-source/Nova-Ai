---
name: voice-ux-design
description: Design speakable, concise voice interactions, verbal confirmations, and interruption-handling conversational UX.
triggers: voice ux, voice design, speakable reply, voice interaction, conversational ux, ভয়েস ডিজাইন, কথা বলা
---

## When to use
Use when formatting text-to-speech outputs, optimizing conversational latency, designing voice confirmation dialogs, or handling voice interruptions.

## Procedure
1. **Ensure spoken brevity and naturalness**: Keep initial spoken responses within 1-3 concise sentences; avoid reading markdown tables, URLs, or code blocks aloud.
2. **Require verbal confirmation for destructive actions**: Verbally confirm irreversible actions before running them (e.g. *"Deleting 5 files in workspace. Proceed?"*).
3. **Summarize first, offer details second**: Speak high-level outcomes first, then prompt the user if they desire deeper technical breakdowns.
4. **Handle interruptions and barge-in gracefully**: Cancel ongoing speech synthesis immediately when user speech is detected; reset state cleanly.
5. **Handle unclear speech with single short clarifications**: If speech recognition is ambiguous, ask one focused question rather than presenting a complex menu.
6. **Mirror user language, tone, and politeness**: Match the user's spoken language (Bengali, English, Hindi, Urdu) and maintain a consistent assistant persona.

## Checklist
- [ ] Are spoken voice responses free of raw markdown formatting and code syntax?
- [ ] Is verbal confirmation requested prior to executing destructive commands?
- [ ] Does voice synthesis terminate immediately upon audio interruption?
- [ ] Does output mirror the active language setting dynamically?

## Output format
- **Spoken String**: Natural, cadence-friendly sentences for TTS.
- **Visual Display Complement**: Rich text, code blocks, or tables displayed on screen.
- **Conversation State Flow**: Prompt, Expected Response, Fallback Prompt.

## Example
```markdown
*User:* "Run disk cleanup on my PC."
*Spoken Voice Output:* "I found 1.2 gigabytes of temporary files. Would you like me to delete them?"
*Visual Screen HUD:* [Action HUD: 1,420 files in C:\Temp | Buttons: Confirm / Cancel]
```
