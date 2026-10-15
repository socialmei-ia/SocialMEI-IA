# GitHub automation instructions

- CI must verify important contracts without depending on a developer machine.
- Keep deployment and validation workflows separate.
- Do not assume a generic production workflow equals the team AWS deploy path.
- Never place secrets directly in workflow YAML.
- Do not weaken checks just to make changes pass.
- Keep workflow changes small and document permissions.
- Prefer PRs and passing checks for mainline changes; avoid force-push on shared branches.
