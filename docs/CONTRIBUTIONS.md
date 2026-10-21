# Contributions

Team members. Fill in the "Contribution" column with what each person actually did; it is deliberately left blank.

| Member | Name | PRN | Contribution (fill in) |
|---|---|---|---|
| 1 | Saksham Singh Sisodiya | 1262242908 | _fill in_ |
| 2 | Parth Dande | 1262242629 | _fill in_ |
| 3 | Anupria Gupta | 1262241349 | _fill in_ |

## Suggested module split

Each person should be able to explain their modules in the viva using `docs/WALKTHROUGH.md`.

| Suggested owner | Files | Why it is a good unit |
|---|---|---|
| Core protocol (member 1) | `mpft/protocol.py`, `sender.py`, `receiver.py`, `cli.py`, `docs/PROTOCOL.md`, `docs/ARCHITECTURE.md` | The heart of the project |
| Emulator and experiments (member 2) | `mpft/emulator.py`, `experiments/`, `docs/TOPOLOGY.md`, `results/` | Self-contained, produces the graphs |
| Wireshark, dashboard and docs (member 3) | `wireshark/`, `web/`, `mpft/status.py`, `docs/screenshots/`, `docs/TEST_REPORT.md` | Visual, easy to demonstrate |

This split is only a suggestion; change it to match what actually happened.

## Git evidence
`git shortlog -sn` shows commits per author; each member should commit under their own identity
(`git config user.name`, `git config user.email`).
