import logging
import os
import sys
import time

import discord
from discord.ext import commands
from dotenv import load_dotenv

from bitunix import bitunix_request, fetch_user_trades
from db import delete_user, get_user, init_db, insert_trades, upsert_user


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

    @bot.tree.command(
        name="bitunix_test",
        description="Prueba firma y autenticacion privada contra Bitunix.",
    )
    async def bitunix_test(interaction: discord.Interaction) -> None:
        if interaction.guild is not None:
            await interaction.response.send_message("Este comando solo en DM")
            return

        discord_id = str(interaction.user.id)

        try:
            user = await get_user(discord_id)
            if user is None:
                await interaction.response.send_message(
                    "ERROR: No estás registrado. Usa /register_bitunix primero."
                )
                return

            await bitunix_request(
                discord_id=discord_id,
                method="GET",
                path="/api/v1/futures/trade/get_history_trades",
                params={
                    "symbol": "BTCUSDT",
                    "limit": 1,
                    "skip": 0,
                    "startTime": int(time.time() * 1000) - (7 * 24 * 60 * 60 * 1000),
                    "endTime": int(time.time() * 1000),
                },
            )
            await interaction.response.send_message("OK: respuesta recibida")
        except Exception as exc:
            logger.exception("Error en /bitunix_test para user_id=%s", interaction.user.id)
            await interaction.response.send_message(f"ERROR: {exc}")

    @bot.tree.command(
        name="update_journal",
        description="Sincroniza tus trades de Bitunix Futures al journal local.",
    )
    async def update_journal(
        interaction: discord.Interaction, symbol: str | None = None, limit: int = 50
    ) -> None:
        await interaction.response.defer(ephemeral=True)

        discord_id = str(interaction.user.id)
        safe_limit = max(1, min(limit, 100))

        try:
            user = await get_user(discord_id)
            if user is None:
                await interaction.followup.send(
                    "Registra tus keys con /register_bitunix en DM", ephemeral=True
                )
                return

            fetched_count, trades = await fetch_user_trades(
                discord_id=discord_id, symbol=symbol, limit=safe_limit, skip=0
            )
            inserted_count = await insert_trades(discord_id=discord_id, trades=trades)

            logger.info(
                "update_journal user_id=%s symbol=%s fetched=%s inserted=%s",
                interaction.user.id,
                symbol,
                fetched_count,
                inserted_count,
            )

            if inserted_count == 0:
                await interaction.followup.send(
                    "Sin cambios: no hay trades nuevos.", ephemeral=True
                )
            else:
                await interaction.followup.send(
                    f"Actualizado: {inserted_count} trades nuevos agregados.",
                    ephemeral=True,
                )
        except Exception as exc:
            logger.exception(
                "Error en /update_journal user_id=%s symbol=%s",
                interaction.user.id,
                symbol,
            )
            await interaction.followup.send(f"ERROR: {exc}", ephemeral=True)

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
