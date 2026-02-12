import logging
import os
import sys
import time
from datetime import datetime

import discord
from discord.ext import commands
from dotenv import load_dotenv

from bitunix import bitunix_request, fetch_user_trades
from db import (
    add_note,
    delete_user,
    get_user,
    init_db,
    insert_trades,
    list_trades,
    upsert_user,
)


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
                "Error interno (revisa consola)", ephemeral=True
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
                "Error interno (revisa consola)", ephemeral=True
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
        except Exception:
            logger.exception(
                "Error en /update_journal user_id=%s symbol=%s",
                interaction.user.id,
                symbol,
            )
            await interaction.followup.send(
                "Error interno (revisa consola)", ephemeral=True
            )

    @bot.tree.command(
        name="add_note",
        description="Agrega o actualiza una nota subjetiva para un trade.",
    )
    async def add_note_command(
        interaction: discord.Interaction, trade_id: str, nota: str
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        discord_id = str(interaction.user.id)

        try:
            updated = await add_note(discord_id=discord_id, trade_id=trade_id, note=nota)
            if not updated:
                await interaction.followup.send(
                    "No encontré ese trade_id en tu journal. Primero corre /update_journal",
                    ephemeral=True,
                )
                return

            await interaction.followup.send(
                f"Nota agregada al trade {trade_id}", ephemeral=True
            )
        except Exception:
            logger.exception(
                "Error en /add_note user_id=%s trade_id=%s",
                interaction.user.id,
                trade_id,
            )
            await interaction.followup.send(
                "Error interno (revisa consola)", ephemeral=True
            )

    @bot.tree.command(
        name="view_journal",
        description="Muestra tu journal reciente con paginacion.",
    )
    async def view_journal(
        interaction: discord.Interaction,
        days: int = 7,
        page: int = 1,
        symbol: str | None = None,
    ) -> None:
        await interaction.response.defer(ephemeral=True)
        discord_id = str(interaction.user.id)

        safe_days = max(1, days)
        safe_page = max(1, page)
        page_size = 10
        offset = (safe_page - 1) * page_size
        now_ms = int(time.time() * 1000)
        since_ms = now_ms - (safe_days * 86400000)

        try:
            trades, total = await list_trades(
                discord_id=discord_id,
                since_ms=since_ms,
                limit=page_size,
                offset=offset,
                symbol=symbol,
            )

            if total == 0:
                await interaction.followup.send(
                    "No hay trades en ese rango. Usa /update_journal", ephemeral=True
                )
                return

            lines: list[str] = []
            for trade in trades:
                ts = int(trade.get("timestamp_ms") or 0)
                date_str = datetime.fromtimestamp(ts / 1000).strftime("%Y-%m-%d %H:%M")
                line = (
                    f"{date_str} | {trade.get('symbol') or '-'} {trade.get('side') or '-'}"
                    f" | pnl={trade.get('realized_pnl') or 0} fee={trade.get('fee') or 0}"
                    f" | id={trade.get('trade_id')}"
                    f" | nota={trade.get('note') or '-'}"
                )
                lines.append(line)

            title = f"Tu Journal - últimos {safe_days} días"
            if symbol:
                title = f"{title} ({symbol})"

            embed = discord.Embed(
                title=title,
                description="\n".join(lines),
                color=discord.Color.blue(),
            )
            embed.set_footer(
                text=f"Página {safe_page} | Mostrando {len(trades)} de {total}"
            )

            await interaction.followup.send(embed=embed, ephemeral=True)
        except Exception:
            logger.exception(
                "Error en /view_journal user_id=%s days=%s page=%s symbol=%s",
                interaction.user.id,
                days,
                page,
                symbol,
            )
            await interaction.followup.send(
                "Error interno (revisa consola)", ephemeral=True
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
