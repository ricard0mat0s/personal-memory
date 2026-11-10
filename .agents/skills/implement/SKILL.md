---
name: implement
description: "Implement a piece of work based on a spec or set of tickets."
disable-model-invocation: true
---

Implement the work described by the user in the spec or tickets.

Use /tdd where possible, at pre-agreed seams.

Run typechecking regularly, single test files regularly, and the full test suite once at the end.

Once done, use /code-review to review the work.

Use /update-documentation to review and update documentation before committing.

Commit your work to the current branch in small, atomic commits. Give each
commit one coherent purpose and include the code, tests, and documentation
needed to keep that change complete and verifiable on its own. Split unrelated
changes into separate commits and use a message that describes each change.
