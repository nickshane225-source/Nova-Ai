---
name: database-design
description: Model database schemas, relationships, indexes, query patterns, and reversible migrations.
triggers: database design, schema design, sql schema, sqlite design, database migration, ডাটাবেস ডিজাইন, স্কিমা
---

## When to use
Use when creating or altering database tables, selecting primary/foreign keys, optimizing indexes, or planning persistent data storage.

## Procedure
1. **Model entities and relationships**: Identify core domain entities, cardinalities (1:1, 1:N, N:M), and state invariants.
2. **Choose appropriate storage engine**: Default to SQLite (`sqlite3` stdlib) for single-node local desktop storage; contrast with document stores (MongoDB) when storing polymorphic unindexed payloads.
3. **Define keys, constraints, and indexes**: Assign auto-incrementing integer or UUID primary keys; index frequently filtered and sorted columns.
4. **Draft reversible migrations**: Write schema migration scripts with explicit `UP` (create/alter) and `DOWN` (rollback) SQL statements.
5. **Enforce parameterized queries**: Never format variables directly into SQL queries; always use parameterized placeholders (`?`).
6. **Plan backups and rollback recovery**: Maintain file-based snapshot procedures before running destructive schema alterations.

## Checklist
- [ ] Are all SQL queries strictly parameterized using `?` placeholders?
- [ ] Are foreign key constraints and cascade rules explicitly declared?
- [ ] Are compound indexes created for common multi-column lookups?
- [ ] Is there an automated migration rollback path?

## Output format
- **Entity-Relationship Summary**: Tables, primary keys, foreign keys.
- **DDL Migration Script**: Reversible SQL statements with `CREATE TABLE IF NOT EXISTS`.
- **Query Optimization Notes**: Indexes and access patterns.

## Example
```sql
-- Migration: Add notes table with full-text indexing support
CREATE TABLE IF NOT EXISTS notes (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    title TEXT NOT NULL,
    content TEXT NOT NULL,
    category TEXT DEFAULT 'general',
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
);
CREATE INDEX IF NOT EXISTS idx_notes_category ON notes(category);
```
