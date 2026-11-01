"""Bot Discord (processus séparé) : commandes slash + questions libres dans un salon.

Lancement : `python main.py discord-bot` (service « assistant » de docker-compose).
Le jeton (DISCORD_BOT_TOKEN) et la clé IA (LLM_API_KEY) viennent du .env, jamais du code.
"""
from __future__ import annotations

import asyncio
import time

import config
from assistant import data, llm
from utils.logger import get_logger

log = get_logger("discord_bot")


def chunks(text: str, size: int = 1900) -> list[str]:
    from alerts.telegram import split_message

    return split_message(text, size) or [""]


def build_client():
    import discord
    from discord import app_commands

    intents = discord.Intents.default()
    intents.message_content = True  # lire les questions dans le salon dédié
    client = discord.Client(intents=intents)
    tree = app_commands.CommandTree(client)

    async def reply(interaction: "discord.Interaction", text: str, image: str | None = None) -> None:
        parts = chunks(text)
        embed = discord.Embed().set_thumbnail(url=image) if image else None
        await interaction.followup.send(parts[0], embed=embed) if embed else await interaction.followup.send(parts[0])
        for p in parts[1:]:
            await interaction.followup.send(p)

    @tree.command(name="prix", description="Prix, tendance et décision du bot pour un joueur suivi")
    @app_commands.describe(joueur="Nom du joueur (ex : Mbappé)")
    async def prix(interaction: discord.Interaction, joueur: str):
        await interaction.response.defer(thinking=True)
        hits = await asyncio.to_thread(data.find_players, joueur)
        if not hits:
            return await interaction.followup.send(f"Aucun joueur suivi ne correspond à « {joueur} ».")
        card = await asyncio.to_thread(data.player_card, hits[0])
        others = f"\n_Autres résultats : {', '.join(h['name'] for h in hits[1:])}_" if len(hits) > 1 else ""
        from dashboard.app import card_image

        await reply(interaction, data.player_text(card) + others, card_image(card["player_id"]))

    @prix.autocomplete("joueur")
    async def prix_auto(interaction: discord.Interaction, current: str):
        hits = await asyncio.to_thread(data.find_players, current, 25)
        return [app_commands.Choice(name=f"{h['name']} {h.get('rating') or ''}"[:100], value=h["name"]) for h in hits]

    @tree.command(name="fodder", description="Prix des fodders 85 à 91 (moins cher par note)")
    async def fodder(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        await reply(interaction, await asyncio.to_thread(data.fodder_text))

    @tree.command(name="top", description="Opportunités du moment et cartes à surveiller")
    async def top(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        await reply(interaction, await asyncio.to_thread(data.top_text))

    @tree.command(name="calendrier", description="Promos et événements à venir")
    async def calendrier(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        await reply(interaction, await asyncio.to_thread(data.calendar_text))

    @tree.command(name="resume", description="Dernier résumé des 24 heures")
    async def resume(interaction: discord.Interaction):
        await interaction.response.defer(thinking=True)
        await reply(interaction, await asyncio.to_thread(data.summary_text))

    @tree.command(name="question", description="Pose une question à l'IA (avec les données du bot)")
    @app_commands.describe(texte="Ta question")
    async def question(interaction: discord.Interaction, texte: str):
        await interaction.response.defer(thinking=True)
        await reply(interaction, await answer(str(interaction.user.id), texte))

    @client.event
    async def on_ready():
        await tree.sync()
        log.info("Bot Discord connecté : %s (%d commandes)", client.user, len(tree.get_commands()))

    @client.event
    async def on_message(message: discord.Message):
        if message.author.bot or not message.content.strip():
            return
        in_channel = config.DISCORD_BOT_CHANNEL_ID and message.channel.id == config.DISCORD_BOT_CHANNEL_ID
        mentioned = client.user in message.mentions
        if not (in_channel or mentioned):
            return
        text = message.content.replace(f"<@{client.user.id}>", "").strip()
        async with message.channel.typing():
            out = await answer(str(message.author.id), text)
        for p in chunks(out):
            await message.reply(p, mention_author=False)

    return client


async def answer(user_id: str, question: str) -> str:
    if not llm.enabled():
        return ("🤖 L'IA n'est pas encore branchée (LLM_API_KEY absent). En attendant : /prix, /fodder, /top, "
                "/calendrier, /resume.")
    try:
        llm.check_limits(user_id)
    except llm.LimitReached as e:
        return str(e)
    t0 = time.time()
    context = await asyncio.to_thread(data.llm_context, question)
    out = await asyncio.to_thread(llm.ask, question, context)
    log.info("Question IA traitée en %.1f s", time.time() - t0)
    return out


def run() -> None:
    if not config.DISCORD_BOT_TOKEN:
        log.warning("DISCORD_BOT_TOKEN absent : assistant Discord désactivé (mise en veille).")
        while True:  # le service reste « vivant » sans redémarrer en boucle
            time.sleep(3600)
    build_client().run(config.DISCORD_BOT_TOKEN, log_handler=None)
