We are now starting PHASE 2 of SIH26118.

Read PROJECT_CONTEXT.md and android/MIGRATION_MAP.md first.

IMPORTANT:
Do NOT redesign the architecture.
Do NOT revert to C++.
Do NOT delete the Python reference.
Do NOT modify the chemistry or invent calibration data.

The target architecture is:

Android
→ Kotlin
→ OpenCV Android SDK where required
→ local image-processing pipeline

The Python implementation under:

reference/python/

is the GOLDEN REFERENCE.

Our goal is to port its functionality to Kotlin incrementally while preserving behavior.

==================================================
PHASE 2 GOAL
==================================================

Begin migrating the Python reference engine into Kotlin.

DO NOT attempt to convert the entire engine in one shot.

Work module-by-module and verify each module against the Python reference before moving forward.

==================================================
STEP 0 — RE-SCAN CURRENT REPOSITORY
==================================================

Before modifying anything:

1. Scan the CURRENT repository.
2. Read PROJECT_CONTEXT.md.
3. Read android/MIGRATION_MAP.md.
4. Inspect the current Android project.
5. Inspect the relevant Python reference modules.
6. Inspect the CURRENT OpenCV dependency/version actually configured in Gradle.

Do not rely on previous folder structures or assumptions.

==================================================
STEP 1 — IDENTIFY THE FIRST MODULE
==================================================

Determine the safest first module to migrate.

Prefer starting with a small, deterministic component such as:

reference/python/engine/badge_spec.py

or another module you determine is a better first target.

Explain:

- what the Python module does
- what inputs it accepts
- what outputs it produces
- what dependencies it has
- what Kotlin class/package should represent it
- how we can test equivalence

DO NOT write the full migration yet until this analysis is complete.

==================================================
STEP 2 — PRESERVE THE PYTHON REFERENCE
==================================================

The files under:

reference/python/

must remain unchanged unless I explicitly approve a change.

Do not "clean up" or rewrite Python code just to make Kotlin easier.

==================================================
STEP 3 — KOTLIN IMPLEMENTATION
==================================================

Once the module is understood and the migration approach is clear:

Implement ONLY that module in Kotlin.

Follow the existing Android package architecture.

Keep:

- geometry/configuration separate from CV
- CV separate from colour math
- colour math separate from calibration
- calibration separate from exposure estimation

Do not hard-code experimental H2S calibration as if it were real.

==================================================
STEP 4 — VERIFICATION
==================================================

Create appropriate tests or comparison tooling where practical.

The objective is:

Python reference input
→ Python output

and

same input
→ Kotlin output

should agree within explicitly justified numerical tolerances.

If exact equivalence is impossible because of OpenCV/API differences, explain why and define the tolerance.

Do NOT simply say "looks correct."

==================================================
STEP 5 — CONTEXT LOG
==================================================

After the module is successfully implemented and verified, update:

PROJECT_CONTEXT.md

with a SHORT entry containing:

- module migrated
- Kotlin location
- verification result
- important decisions
- limitations
- next module

Do not fill the file with code.

==================================================
CRITICAL RULES
==================================================

Do NOT:

- migrate the entire engine at once
- create a giant monolithic BadgeEngine.kt
- rename old concepts without checking their underlying assumptions
- invent wristband dimensions
- invent H2S calibration coefficients
- treat Na2S liquid testing as H2S calibration
- modify the golden Python reference unnecessarily
- delete legacy files
- build the final UI yet
- add unnecessary backend functionality
- make irreversible changes without showing me first

Use the existing architecture.

At the end of this step, STOP and show me:

1. What module you recommend migrating first
2. Why
3. Its Python behavior
4. Proposed Kotlin class/package
5. Dependencies
6. Testing strategy
7. Exact files you intend to create/modify

Wait for approval before implementing the first module.