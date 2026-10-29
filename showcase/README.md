# Public showcase source

Chinese-first, buildless presentation of LocalFace Studio. This is **not** the inference application's frontend.

- `index.html`, `styles.css`, `app.js`, `favicon.svg` are the entire deployable asset allowlist.
- No uploads, forms, analytics, visitor storage, local-service connections, model weights or research photographs.
- Diagrams are explicitly marked as illustrations, not actual swap results.
- Engineering and model evidence use different dates and disclose their limits.
- Code follows the repository's MIT license. Referenced models retain their own licenses.

## Check and preview

From the repository root:

```powershell
node scripts/verify_showcase.mjs
node --check showcase/app.js
python -m http.server 4175 --bind 127.0.0.1 --directory showcase
```

Open the local address printed by the server. Stop it with Ctrl+C. This does not start inference.

## Publishing boundary

The reviewable source is retained here on GitHub. A separate Sites checkout mirrors only the four deployable files and owns its own hosting manifest and source Git history. Do not copy the product repository, runtime, models, diagnostics, screenshots or credentials into that checkout. Do not create another Site when updating the existing showcase.

Publishing is independent of the model application's release. Neither a successful static deployment nor its checks remove the gates in `docs/PUBLIC_DEPLOYMENT_READINESS.md`.
