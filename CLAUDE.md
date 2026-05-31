# CLAUDE.md

Claude Code project instructions. Read `AGENTS.md` for full project documentation, architecture rules, commands, and code style guidance.

---

## Claude Code-Specific Notes

- Default to Server Components in Next.js. Only use `'use client'` when interactivity is required.
- All admin backend calls must go through Server Actions in `apps/admin-web/actions/` — never from a client component.
