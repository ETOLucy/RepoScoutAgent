# GitHub Repository Surfaces

Use these constraints when planning repository identity work.

## Supported remote settings

GitHub CLI supports the core MVP:

- `gh repo edit OWNER/REPO --description ... --homepage ... --add-topic ...`
- `gh repo rename NEW-NAME --repo OWNER/OLD-NAME --yes`
- `gh repo view OWNER/REPO --json nameWithOwner,description,homepageUrl,repositoryTopics,url`

Repository renames redirect many old GitHub URLs, but local remotes should still be updated to the
new canonical URL. Treat package registries, Pages domains, deployment integrations, badges, and
hard-coded URLs as separate consumers that require an audit.

## Social preview

Create `social-preview.png` at 1280 x 640 px and keep it under 1 MB. Keep the repository identity and
essential wording away from the outer edge so the image survives crops and small previews. Inspect
the final PNG rather than trusting an SVG source render.

GitHub exposes social-preview management in the repository Settings interface. The documented public
GitHub CLI and REST surfaces do not provide a stable upload command. Prefer browser automation for
the upload; otherwise tell the user to open:

`Settings > General > Social preview > Edit`

Do not use a guessed or undocumented endpoint.

## Logo and README

GitHub repositories do not have a dedicated repository-logo setting. Use:

- a square transparent mark that remains legible at 32 px;
- a horizontal lockup near the README title;
- light and dark variants when one SVG cannot adapt;
- meaningful alternative text;
- the social preview for link unfurls;
- a concise description and focused topics for repository discovery.

Avoid decorative badge walls, false "official" badges, screenshots that hide the real product, and
claims that cannot be verified from the repository.

## Topic rules

Use lowercase terms made from letters, digits, and hyphens. Prefer a small set that covers the
project's domain, primary technology, and use case. Add topics conservatively; do not remove existing
topics unless the user explicitly approves replacement.
