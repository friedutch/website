# Minecraft

## Human Summary
- This module owns the public Minecraft landing page for `friedutch.plus`.
- It reads the Minecraft page environment variables plus local server files and renders the public connection page at `/minecraft/`.
- It can also expose an admin-only controls block for the separate Minecraft LaunchAgent.
- The page now renders inside the same shared Discord-like site shell as the rest of the website.

## AI Copilot

### Ownership
- [`projects/minecraft/minecraft.py`](/Users/administrator/Sites/friedutchplus/projects/minecraft/minecraft.py)
- [`templates/minecraft.html`](/Users/administrator/Sites/friedutchplus/templates/minecraft.html)
- [`static/css/pages/minecraft.css`](/Users/administrator/Sites/friedutchplus/static/css/pages/minecraft.css)
- [`projects/minecraft/ops/start_server.sh`](/Users/administrator/Sites/friedutchplus/projects/minecraft/ops/start_server.sh)
- [`projects/minecraft/ops/friedutchplus.minecraft.server.plist.example`](/Users/administrator/Sites/friedutchplus/projects/minecraft/ops/friedutchplus.minecraft.server.plist.example)
- [`projects/minecraft/ops/server.properties.example`](/Users/administrator/Sites/friedutchplus/projects/minecraft/ops/server.properties.example)

### Purpose
- Publish connection details and live host metadata for a separately hosted Minecraft server.
- Keep Minecraft-specific route logic out of the main app factory.
- Serve the Minecraft info page from `/minecraft/` on the main website.

### Runtime model
- The Flask site only serves the landing page.
- The actual Minecraft daemon should run as its own process or service outside this repo.
- The page reads server status from the LaunchAgent label and selected world/server details from local `server.properties`.
- Start and stop controls on the page live in the admin-only controls block and require an authenticated Smart Lock admin session.
- When admin access is missing, the rest of the site uses the canonical `/login` Smart Lock entrypoint.
- A DNS record such as `mc.friedutch.plus` should point at the host running the Minecraft server.
- The provided ops files assume a live server root at `/Users/administrator/Servers/minecraft`.
- Keep that live server root outside the Git repo and never commit a copied server instance, world folder, Paper jar, or plugin jar.

### Current page structure
- `Server ID`
  - public top card
  - shows server name `FP SMP`, join address, status, and player count
- `Golden Rules`
  - public rules card
- `Admin Controls`
  - only visible to Smart Lock admins
  - contains start/stop and placeholder operational actions
- The page background image is [`static/img/pages/minecraft/background.jpg`](/Users/administrator/Sites/friedutchplus/static/img/pages/minecraft/background.jpg).
- The live Minecraft server-list name comes from the server `motd`, currently set to `FP SMP`.

### Ops files
- `ops/install_paper.sh` downloads a stable Paper server jar from PaperMC's official downloads service and seeds the live server directory.
- `ops/provision_host.sh` installs the live server directory, installs the LaunchAgent, and restarts the Flask site so the page reflects the current config.
- `ops/start_server.sh` starts the Paper server with a configurable Java binary and heap size.
- `ops/friedutchplus.minecraft.server.plist.example` is the LaunchAgent template for keeping the server alive on macOS.
- `ops/server.properties.example` is a baseline server configuration for the live server directory.
- The example `motd` is `FP SMP` to match the website’s `Server ID` card.
- The baseline server example keeps `online-mode=true`, `white-list=true`, `hide-online-players=true`, `enable-query=false`, and `enable-rcon=false`.

### Environment variables
- `MINECRAFT_JOIN_HOST`
- `MINECRAFT_JOIN_PORT`
- `MINECRAFT_SERVER_ROOT`
- `MINECRAFT_WORLD_NAME`
- `MINECRAFT_LAUNCH_AGENT_LABEL`
- `MINECRAFT_LAUNCH_AGENT_PLIST`
- `MINECRAFT_SERVER_EDITION`
- `MINECRAFT_SERVER_MODLOADER`
- `MINECRAFT_SERVER_VERSION`
- `MINECRAFT_SERVER_ACCESS`
