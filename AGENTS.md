# Agents

Every agent working in this repo has exactly **one role**. The roles are split
so neither one does the other's work, even by accident.

| Role | In one line | Skill |
|---|---|---|
| **decomp** | engine tooling: gets the Japanese script out, and builds the patchers that put any English back in | `pc98-decomp` |
| **translation** | the script's content: translating, and classifying and flagging what's in it | `pc98-translation` |

## Before you do anything

1. **Know your role.** Whoever started you assigns it: the prompt, the task or
   the person. If nobody did, ask. Don't choose a role because it suits the
   task in front of you.
2. **Load your role's skill, and only that one.**
   * Claude Code: invoke it with the Skill tool (`pc98-decomp` or
     `pc98-translation`).
   * Other harnesses: read `.claude/skills/<skill>/SKILL.md`.
   The skill is your whole scope: what you do, what you don't do, and how.
3. **Don't read the other role's skill,** and don't read anything written
   only for the other role. Your scope comes from your own skill alone, so
   nothing from the other role leaks into your work.

## While you work

* Stay in your role for the whole session.
* If a request falls outside your skill, don't do it, not even a little of it
  "to help". Say which role it belongs to and leave it for that role.
* Shared files, for both roles:
  * `README.md` and `DEFINITION_OF_DONE.md`: the checklist. Each role's skill
    says which sections are its own.
  * `games/<title>/strings.json`: the handoff between the roles. Its format is
    in both skills.
  * `ROADMAP.md` and `index/`: status. Each role updates only its own columns
    and records, as its skill says.
