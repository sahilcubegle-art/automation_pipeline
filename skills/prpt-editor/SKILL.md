---
name: prpt-editor
description: Inspect and make narrowly scoped, validated changes to Pentaho/JasperReports `.prpt` ZIP report bundles without placing raw report XML in context.
---

# PRPT editor

Use this skill for targeted changes to `.prpt` report bundles: locating fields, parameters, variables, labels, or expressions; changing an exact expression; and validating the result. Do not use it to infer accounting rules or redesign a report without a specified business rule.

The bundle contains several XML members (typically `layout.xml`, `datadefinition.xml`, `dataschema.xml`, and styles/settings) plus resources. Keep raw XML out of the conversation: invoke the script and reason from its compact JSON.

## Workflow

1. Run `python skills/prpt-editor/prpt_editor.py inspect REPORT.prpt`. It returns member names, object counts, and short definition names only.
2. Search progressively and cap output: `find REPORT.prpt "net income" --limit 20`, `find REPORT.prpt --type variable`, or `find REPORT.prpt --expression "tax"`.
3. If a request has a business ambiguity (for example, whether VAT is inclusive, deductible, or should affect net income), report the compact evidence and ask for the rule. Never invent it.
4. For a known expression, first locate exactly one selector with `find`; then make an optimistic-concurrency edit: `modify-expression REPORT.prpt --target layout.xml#42 --expect 'old formula' --expression 'new formula'`. The command creates `REPORT.prpt.bak`, changes only that ZIP member, and rejects a stale selector/value or ambiguous expression attribute. For a scalar input, use the verified PRD 9.x serializer: `add-parameter REPORT.prpt --name VAT_RATE --type java.lang.Double --default 0.18 --label 'VAT rate'`.
5. Run `validate REPORT.prpt`. It checks ZIP CRCs, the Pentaho MIME type, and parses every XML member. On a failed edit, restore the `.bak` only after inspecting the failure; do not overwrite it automatically.

## Constraints

- `find` selectors are report-version-specific. Never reuse a selector after another edit.
- Use `--limit` (default 50) and narrow type/expression filters. Do not dump XML except when a compact search result cannot resolve an ambiguity.
- The deterministic mutations are expression replacement and a plain scalar parameter. List/query parameters and layout additions need an explicitly verified schema/template in the target bundle; inspect first and extend the utility with a tested adapter rather than manufacturing XML.
- Preserve the tool's JSON output in the working notes instead of copying bundle content into chat.

See [agents/AGENTS.md](agents/AGENTS.md) for operating guidance and [examples/usage.md](examples/usage.md) for commands.
