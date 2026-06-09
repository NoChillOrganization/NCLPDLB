# Security Policy

## Supported Versions

This is a single-deployment Discord bot (no versioned releases). The `master` branch
is the only supported version.

| Branch  | Supported |
| ------- | --------- |
| master  | ✅ Yes    |

## Reporting a Vulnerability

Please **do not** open a public GitHub issue for security vulnerabilities.

Report privately via one of:

- **GitHub private security advisory**: [Report a vulnerability](https://github.com/NoChillModeOnline/NCLPDLB/security/advisories/new)
- **Email**: travis.r.weisberg@gmail.com

Include:
- Description of the vulnerability and affected component
- Steps to reproduce
- Potential impact

You can expect an acknowledgement within 48 hours. If accepted, a fix will be
deployed to `master` and the advisory will be published. If declined, you'll
receive an explanation.

## Sensitive components

- `credentials.json` — Google service-account key (gitignored, never committed)
- `.env` — bot token + spreadsheet credentials (gitignored, never committed)
- `pokemon_draft.db` — local SQLite DB with draft/ELO data (gitignored)
