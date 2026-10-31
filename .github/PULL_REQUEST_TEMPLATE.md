## Summary

<!-- What changed, and why? Link the issue if one exists. -->

## Type of change

- [ ] Bug fix
- [ ] Evaluation or dataset change
- [ ] New capability
- [ ] Documentation
- [ ] Refactor or maintenance

## Verification

<!-- Paste the commands you ran and their result. -->

```bash
pytest
cd axion && pnpm lint && pnpm exec tsc --noEmit && pnpm build
```

## Checklist

- [ ] Tests cover the new or changed behaviour.
- [ ] Evaluation numbers (if any) include a before/after comparison.
- [ ] Documentation is updated where behaviour or configuration changed.
- [ ] No credentials, `.env` files, downloaded PDFs, or generated dumps are included.
- [ ] The change is limited to one concern.
