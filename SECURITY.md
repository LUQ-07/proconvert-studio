# Security policy

ProConvert Studio opens documents that may come from untrusted sources, so security reports are welcome.

## Reporting a vulnerability
Please **do not open a public issue** for a security problem. Use GitHub's private reporting instead:
**Security tab -> "Report a vulnerability"** on this repository. Include the program version, the steps to reproduce and, if
possible, a minimal file that triggers the problem (remove any private content first).

You will get an answer as soon as the maintainer can look at it; this is a volunteer project, so there is no guaranteed
response time and no bug bounty.

## What the application does to protect you
Described in [docs/SECURITY_MODEL.md](docs/SECURITY_MODEL.md): documents are processed locally, nothing is uploaded, the app makes
no network requests, input files are never modified, output files are never overwritten silently, and every conversion has
explicit size, page and time limits.

## Supported versions
Only the latest release receives fixes.
