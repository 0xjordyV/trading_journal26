# Discord Bot (Trading Journal)

Bot básico de Discord en Python con `discord.py` 2.x y slash commands.

## Requisitos

- Python 3.10+

## Instalación

```bash
pip install discord.py python-dotenv
```

## Configuración

1. Crea `.env` desde el ejemplo:

```powershell
Copy-Item .env.example .env
```

2. Edita `.env`:

```env
DISCORD_TOKEN=tu_token_real
DISCORD_MEMBERS_INTENT=false
```

`DISCORD_MEMBERS_INTENT`:
- `false` (recomendado para empezar): no requiere intent privilegiado.
- `true`: debes habilitar **Server Members Intent** en Discord Developer Portal.

## Ejecutar

```bash
python bot.py
```
