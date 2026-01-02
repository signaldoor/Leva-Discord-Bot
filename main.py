import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import asyncio
import requests

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
OLLAMA_URL = os.getenv("OLLAMA_URL")
OLLAMA_API_KEY = os.getenv("OLLAMA_API_KEY")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not set")
if not OLLAMA_URL:
    raise RuntimeError("OLLAMA_URL not set")

handler = logging.FileHandler(
    filename="discord.log",
    mode="w",
    encoding="utf8"
)

intents = discord.Intents.default()
intents.message_content = True
intents.members = True

bot = commands.Bot(command_prefix="!", intents=intents)

secret_role = "Le Epic Gamer"

system_prompt = """
You are Leva, also known as UMP45 from Girls' Frontline.
You speak with dry humor, restrained sarcasm, and quiet emotional depth.
Stay in character at all times.
"""

# AI CODE
def ollama_chat(prompt: str, system_prompt: str) -> str:
    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        headers={
            "Authorization": f"Bearer {OLLAMA_API_KEY}",
        },
        json={
            "model": "qwen2.5:1.5b",
            "messages": [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": prompt},
            ],
            "stream": False,
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]

@bot.event
async def on_ready():
    print(f"{bot.user} is online!")

@bot.event
async def on_member_join(member):
    await member.send(f"Welcome to the server {member.name}")

# AI CODE
@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    if "retard" in message.content.lower():
        await message.delete()
        await message.channel.send(
            f"{message.author.mention} - don't say that word silly!"
        )
        return

    if message.content.startswith("!ai "):
        prompt = message.content[4:]
        await message.channel.typing()

        try:
            reply = await asyncio.to_thread(
                ollama_chat,
                prompt,
                system_prompt
            )
        except Exception as e:
            print(e)
            await message.channel.send("AI error.")
            return

        for chunk in (
            reply[i:i + 2000]
            for i in range(0, len(reply), 2000)
        ):
            await message.channel.send(chunk)

    await bot.process_commands(message)

@bot.command()
async def hello(ctx):
    await ctx.send(f"Hello {ctx.author.mention}!")

@bot.command()
async def assign(ctx):
    role = discord.utils.get(ctx.guild.roles, name=secret_role)
    if role:
        await ctx.author.add_roles(role)
        await ctx.send(
            f"{ctx.author.mention} is now assigned to {secret_role}"
        )
    else:
        await ctx.send("Role doesn't exist")

@bot.command()
async def remove(ctx):
    role = discord.utils.get(ctx.guild.roles, name=secret_role)
    if role:
        await ctx.author.remove_roles(role)
        await ctx.send(
            f"{ctx.author.mention} has had the {secret_role} removed"
        )
    else:
        await ctx.send("Role doesn't exist")

@bot.command()
async def dm(ctx, *, msg):
    await ctx.author.send(f"You said {msg}")

@bot.command()
async def reply(ctx):
    await ctx.reply("This is a reply to your message!")

@bot.command()
async def poll(ctx, *, question):
    embed = discord.Embed(
        title="New Poll",
        description=question
    )
    poll_message = await ctx.send(embed=embed)
    await poll_message.add_reaction("😊")
    await poll_message.add_reaction("😒")

@bot.command()
@commands.has_role(secret_role)
async def secret(ctx):
    await ctx.send("Welcome to the Le Epic Gamer club!")

@secret.error
async def secret_error(ctx, error):
    if isinstance(error, commands.MissingRole):
        await ctx.send("You do not have permission to do that!")

bot.run(TOKEN, log_handler=handler, log_level=logging.DEBUG)
