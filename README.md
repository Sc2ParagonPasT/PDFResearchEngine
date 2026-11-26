# PDF Research Engine

Free, locally operated, dark-mode PDF discovery and research application. Development prototype v0.2. The planned Windows x64 deliverable is `PDFResearchEngine.exe`, with bundled ClamAV, YARA, PDF reconstruction and OCR.

## Build status

No verified Windows executable exists yet. The source archive `PDF_Research_Engine_v0.2_source.zip` contains the application, tests, original build recipe, documentation and third-party notices. The repository build workflow will compile this archive on a GitHub-hosted Windows runner once the archive is uploaded. The build must pass automated tests and actual scanner diagnostics before an experimental artifact is produced.

## Safety and scope

Development prototype only. The native PDF worker has process separation but no OS-enforced sandbox. Antivirus checks do not guarantee safety. Do not use this prototype with hostile files or sensitive personal data. Test only in a disposable Windows VM until sandboxing, clean-machine validation, and licensing/redistribution review are complete. No paid APIs are required. Source archive includes component licensing notes.
