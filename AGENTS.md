# Backend Project Rules - LP CRM (`lpcrmbackend-main`)

Inherits global rules from `~/.gemini/config/plugins/global-rules/rules/AGENTS.md` and parent CRM specification.

---

## 1. Monday.com Project Board
- **Board ID**: `5032325363` (Name: CRM)
- **Board URL**: [Monday.com CRM Board](https://developerlifeplanners-team.monday.com/boards/5032325363)
- **Authorization Gate**: Never mark items "Done" without explicit user confirmation in chat.

---

## 2. Git & Deployments
- **Remote**: `https://github.com/lifeplannerdev/lpcrmaws-backend.git`
- **Branch Strategy**: Branch off `main` to `feat/...` or `fix/...`. Never commit directly to `main`.

---

## 3. Commands
- `python manage.py runserver`: Start Django API server.
- `python manage.py test`: Run Django unit tests.
- `python manage.py migrate`: Apply database migrations.
