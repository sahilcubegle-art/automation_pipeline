# PRPT editing guidance

Use `../prpt_editor.py` as the first and default source of report structure. Its JSON is the context boundary; never unzip or paste complete XML solely for exploration.

Start with `inspect`, then narrow `find` queries by text, `--type`, or `--expression`. A selector identifies one exact node only in the current report revision. Before mutation, require one matching selector and an `--expect` value. If more than one result is plausible, stop and present the alternatives.

Run `validate` immediately after every mutation. The editor makes a sibling `.prpt.bak`; retain it until the user accepts the change. Treat request wording such as “add VAT” as an accounting-policy question unless report evidence and the user specify the tax base, rate source, display location, and effect on totals.

For unsupported structural operations (new parameters/elements), first verify the target bundle's XML representation and implement a narrow tested adapter. Do not emit arbitrary XML snippets into a production report.
