# Contributing

LocalFace Studio accepts small, reviewable changes that preserve local-only processing, explicit consent, accurate capability labels and model/data provenance.

Before opening a pull request:

1. Create a focused branch and keep unrelated changes out.
2. Do not add face photos, generated results, model weights, identity vectors, runtime databases, secrets, absolute user paths or unredacted logs.
3. Document licenses for every new dependency, model, ComfyUI node, dataset and sample asset.
4. Keep non-commercial research assets isolated from any commercial-compatible claim.
5. Run `powershell -NoProfile -ExecutionPolicy Bypass -File scripts\check.ps1`.
6. For UI changes, include exact manual verification steps but no private screenshots.

Security issues must use a private GitHub security advisory, not a public issue. Contributions that weaken consent, watermarks, metadata, local binding, cleanup or model integrity checks require an explicit architecture review.
