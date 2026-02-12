import logging
import os
import sys

import discord
from discord.ext import commands
from dotenv import load_dotenv

from db import delete_user, init_db, upsert_user


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


def build_bot(enable_members_intent: bool) -> commands.Bot:
    intents = discord.Intents.none()
    intents.guilds = True
    intents.members = enable_members_intent

    bot = commands.Bot(command_prefix="!", intents=intents)

    @bot.event
    async def on_ready() -> None:
        print(f"Bot conectado como {bot.user}")

        try:
            await init_db()
            logger.info("Base de datos inicializada")
        except Exception:
            logger.exception("Error al inicializar la base de datos")

        try:
            synced = await bot.tree.sync()
            logger.info("Slash commands sincronizados: %s", len(synced))
        except Exception:
            logger.exception("Error al sincronizar slash commands")

    @bot.tree.command(
        name="hello",
        description="Saluda para confirmar que el bot está activo.",
    )
    async def hello(interaction: discord.Interaction) -> None:
        await interaction.response.send_message(
            "¡Hola! Listo para llevar tu trading journal en Bitunix (perps)."
        )

    @bot.tree.command(
        name="register_bitunix",
        description="Registra o actualiza tus API keys de Bitunix.",
    )
    async def register_bitunix(
        interaction: discord.Interaction, api_key: str, api_secret: str
    ) -> None:
        if interaction.guild is not None:
            await interaction.response.send_message("Este comando solo en DM")
            return

        try:
            await upsert_user(
                discord_id=str(interaction.user.id),
                api_key=api_key,
                api_secret=api_secret,
            )
            await interaction.response.send_message(
                "¡Keys registradas! (Recomendación: crea keys READ-ONLY). Usa /update_journal"
            )
        except Exception:
            logger.exception("Error guardando keys para user_id=%s", interaction.user.id)
            await interaction.response.send_message(
                "Ocurrió un error guardando tus keys. Intenta de nuevo."
            )

    @bot.tree.command(
        name="revoke_bitunix",
        description="Elimina tus API keys almacenadas en el bot.",
    )
    async def revoke_bitunix(interaction: discord.Interaction) -> None:
        if interaction.guild is not None:
            await interaction.response.send_message("Este comando solo en DM")
            return

        try:
            await delete_user(discord_id=str(interaction.user.id))
            await interaction.response.send_message(
                "Keys eliminadas. Para volver a usar el bot, registra de nuevo."
            )
        except Exception:
            logger.exception("Error eliminando keys para user_id=%s", interaction.user.id)
            await interaction.response.send_message(
                "Ocurrió un error eliminando tus keys. Intenta de nuevo."
            )

    return bot


def main() -> None:
    load_dotenv()
    token = os.getenv("DISCORD_TOKEN")
    enable_members_intent = (
        os.getenv("DISCORD_MEMBERS_INTENT", "false").strip().lower() == "true"
    )

    if not token:
        print("Error: falta DISCORD_TOKEN en el archivo .env")
        sys.exit(1)

    if enable_members_intent:
        logger.info(
            "DISCORD_MEMBERS_INTENT=true. Habilita 'Server Members Intent' en Discord Developer Portal."
        )
    else:
        logger.info(
            "DISCORD_MEMBERS_INTENT=false. El bot arrancara sin intent privilegiado de members."
        )

    bot = build_bot(enable_members_intent=enable_members_intent)
    bot.run(token)


if __name__ == "__main__":
    main()
