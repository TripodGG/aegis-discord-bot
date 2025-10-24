# Aegis — Star Trek Fleet Command Discord Bot

Aegis is a role-gated moderation/ops bot for **Star Trek Fleet Command** communities. It streamlines **Rules of Engagement (RoE)** reports and **war declarations**, keeps noisy channels tidy, and posts to a dedicated log channel for audit.

## ✨ Features

- **Slash commands** with **role-based access control** and **excluded roles**
- **/setup** — admin-only interactive panel:
  - Allowed Roles (multi-select)
  - Excluded Roles (multi-select)
  - Admiral Role (optional; pinged on war declarations)
  - War Channel (optional)
  - Log Channel (required; recommend private)
- **/roe** — file an RoE violation:
  - Modal for **long-form reason/details**
  - Pings the **selected target role**
  - Posts an embed and logs the action
- **/declare** — declare war:
  - Modal for **long-form reason/details**
  - Pings the **target role** **and** the configured **Admiral role**
  - Posts to the current channel and optionally mirrors to the **War Channel**
  - Logs the action

> Aegis stores a small JSON config per-guild under `./config/<guild-id>.json` (created automatically on first save).

---

## 🧰 Tech

- Python 3.10+
- `discord.py` 2.x slash commands & UI
- `python-dotenv` for environment variables
- JSON file config (SQLite/Postgres optional later)

---

## 🚀 Local Development

1. Clone this repo and create a virtual environment:
   ```bash
   python3 -m venv .venv
   source .venv/bin/activate
   pip install -r requirements.txt
   ```

2. Create a `.env` from the example:
   ```bash
   cp .env.example .env
   # Edit DISCORD_TOKEN=... (never commit your real token)
   ```

3. Run the bot:
   ```bash
   python bot.py
   ```

4. In your Discord server:
   - Invite the bot (scopes: `bot applications.commands`).
   - Run `/setup` (admin-only) to configure roles/channels.
   - Use `/config` to verify.

---

## ☁️ EC2 Deployment (Ubuntu 22.04/24.04)

Use the included **bootstrap script** to provision an instance and run Aegis as a systemd service that **auto-restarts** on crash and **starts on boot**.

1. Launch an EC2 instance (Ubuntu 22.04/24.04), security group with **SSH inbound** only.
2. SSH in and download the script:
   ```bash
   curl -fsSL -o bootstrap-aegis.sh https://raw.githubusercontent.com/your-username/aegis-discord-bot/main/deploy/bootstrap-aegis.sh
   sudo bash bootstrap-aegis.sh
   ```
   > Alternatively, copy `deploy/bootstrap-aegis.sh` from this repo and run it as root.

3. Put your token into `/home/aegis/app/.env`:
   ```bash
   sudo nano /home/aegis/app/.env
   ```

4. Restart and watch logs:
   ```bash
   sudo systemctl restart aegis-bot
   sudo journalctl -u aegis-bot -f
   ```

### Updating on EC2

```bash
sudo -u aegis -H bash -lc 'cd ~/app && git pull && source .venv/bin/activate && pip install -r requirements.txt || true'
sudo systemctl restart aegis-bot
```

### Optional: SSM Parameter Store

Store the token in **AWS Systems Manager Parameter Store** as `/stfc-aegis/DISCORD_TOKEN` and use the `ExecStartPre` fetcher in the systemd unit. See comments in the bootstrap script for details.

---

## 🔐 Security Tips

- Keep the token out of Git; `.env` is in `.gitignore`.
- Use a **private** log channel for staff.
- Scope bot permissions minimally when you create the invite link.
- Keep the EC2 instance patched; limit inbound to SSH only.

---

## 📜 License

MIT © 2025 CloudCoreMSP
