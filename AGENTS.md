# Agents

Every agent working in this repo has exactly **one role**. The decomp and
translation roles are split so neither one does the other's work, even by
accident. Other covers one-off work outside those roles.

| Role | In one line | Skill |
|---|---|---|
| **decomp** | engine tooling: gets the Japanese script out, and builds the patchers that put any English back in | `pc98-decomp` |
| **translation** | the script's content: translating, and classifying and flagging what's in it | `pc98-translation` |
| **other** | one-off repository maintenance and glue tasks outside decomp and translation | none |

## Before you do anything

1. **Know your role.** Whoever started you assigns it: the prompt, the task or
   the person. If nobody did, ask. Don't choose a role because it suits the
   task in front of you.
2. **For decomp or translation, load your role's skill, and only that one.**
   * Claude Code: invoke it with the Skill tool (`pc98-decomp` or
     `pc98-translation`).
   * Other harnesses: read `.claude/skills/<skill>/SKILL.md`.
   The skill is your whole scope: what you do, what you don't do, and how.
   **Other has no role skill.** Do not load either role's skill for other work.
3. **Don't read another role's skill,** and don't read anything written only
   for another role. Decomp and translation get their scope from their own
   skill; other stays within the one-off task assigned to it.

## While you work

* Stay in your role for the whole session.
* Decomp and translation: if a request falls outside your skill, don't do it,
  not even a little of it "to help". Say which role it belongs to and leave it
  for that role. Other does not do engine tooling or script content work.
* Shared files, for decomp and translation:
  * `README.md` and `DEFINITION_OF_DONE.md`: the checklist. Each role's skill
    says which sections are its own.
  * `games/<title>/strings.json`: the handoff between the roles. Its format is
    in both skills.
  * `ROADMAP.md` and `index/`: status. Each role updates only its own columns
    and records, as its skill says.
