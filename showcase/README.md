# Public showcase source

Chinese-first, buildless engineering case study for recruiters and technical reviewers. This is **not** the inference application's frontend.

- `index.html`, `styles.css`, `favicon.svg` are the entire deployable asset allowlist. No browser JavaScript is needed.
- No uploads, forms, analytics, visitor storage, local-service connections, model weights or research photographs.
- The only diagram describes application layers; no simulated portraits or before/after results.
- Focus: application scope, three engineering decisions, one model-selection comparison, and dated verification with unresolved limits.
- State AI-assisted development and upstream-model reuse; do not imply independent model training or unverified personal implementation ownership.
- Engineering and model evidence use different dates and disclose their limits.
- Code follows the repository's MIT license. Referenced models retain their own licenses.

## Check and preview

From the repository root:

```powershell
node scripts/verify_showcase.mjs
python -m http.server 4175 --bind 127.0.0.1 --directory showcase
```

Open the local address printed by the server. Stop it with Ctrl+C. This does not start inference.

## Publishing boundary

The reviewable source is retained here on GitHub. A separate Sites checkout mirrors only the three deployable files and owns its own hosting manifest and source Git history. Do not copy the product repository, runtime, models, diagnostics, screenshots or credentials into that checkout. Do not create another Site when updating the existing showcase.

Publishing is independent of the model application's release. Neither a successful static deployment nor its checks remove the gates in `docs/PUBLIC_DEPLOYMENT_READINESS.md`.
