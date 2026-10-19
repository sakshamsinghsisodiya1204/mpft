# Contributions

Template only. Fill in the real names and what each person did. Do not leave placeholders in the submitted version.

| Member | Name | Student ID | Contribution (fill in) |
|---|---|---|---|
| 1 | _fill in name_ | _fill in_ | _fill in_ |
| 2 | _fill in name_ | _fill in_ | _fill in_ |

## Suggested module split for the teammate who joins

Each person should be able to explain their modules in the viva using `docs/WALKTHROUGH.md`.

| Teammate takes over | Files | Why it is a good unit |
|---|---|---|
| Emulator and experiments | `mpft/emulator.py`, `experiments/`, `docs/TOPOLOGY.md`, `results/` | Self-contained, easy to demonstrate, produces the graphs |
| Wireshark and remote run | `wireshark/`, `docs/REMOTE.md`, screenshots | Hands-on, needs the real two-Mac test |
| Dashboard | `web/`, `mpft/status.py` | Small and visual |

Remaining with the original author: `protocol.py`, `sender.py`, `receiver.py`, `cli.py`, `docs/PROTOCOL.md`, `docs/ARCHITECTURE.md`.

## Git evidence
`git shortlog -sn` shows commits per author; the teammate should commit under their own identity
(`git config user.name`, `git config user.email`).
