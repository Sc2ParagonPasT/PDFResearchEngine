# Release scope reset

v0.4 is a usability-only experimental release. Keep the exact validated v0.3 retrieval tree, existing library storage, scanner and export checks. Include larger text, scrollable UI, quick-start guide, Search/Enter, real processing monitor, library/export folder shortcuts, publication filenames and optional automatic rescanned export. Package the runtime as one executable; preserve separate verification reports. Do not ship the expanded catalog or reader.

The combined prototype is preserved at commit 8c97a8a72eb25626cd28d28e9bcd78d266a8a898. Its 61 regression tests and desktop smoke test passed, but independent live retrieval failed (six candidate collections returned zero; Zenodo returned two PDFs). Validation run: https://github.com/Sc2ParagonPasT/PDFResearchEngine/actions/runs/45938227359. Future-feature files remain in the repository, excluded from preparation, tests and packaging for v0.4. No claim of 98 working repositories.

v0.5: source expansion, curated independently validated collections and catalog updates. Develop and test incrementally. v0.6: screened-document reader, separate render worker and security review. v0.7: research organization tools including numbered-list folder generator. Do not introduce additional features into v0.4 without explicit scope approval.

Clean Windows desktop testing, independent licensing review, signing and OS-enforced sandbox isolation remain outstanding. No release or claim of successful build until the applicable gates pass.

## v0.4.1 usability patch

14-point default and reset; keep existing saved sizes. Persistent upper-right text-size control with plus/minus, slider and point display. Mouse wheel scrolls nearest table/text/canvas, falling back to outer scroll area at its boundary; Ctrl-wheel changes global size and Ctrl+0 resets. Friendly status labels distinguish virus scans from rebuilding/searchable text, raw details available. Successful batches hide monitor after five seconds, with countdown, opt-out and reopening of retained report. Blocked, failed and cancelled batches remain visible; new batches cancel stale timers. Respect Tk's existing DPI scaling rather than multiplying Windows text scaling independently; simulated scale tests are not clean Windows accessibility tests. No repository expansion or reader. No changes to security.py instrumentation or retrieval algorithms in this patch.
