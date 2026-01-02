import discord
from discord.ext import commands
import logging
from dotenv import load_dotenv
import os
import asyncio
import requests
import threading
import json
from pathlib import Path
from http.server import HTTPServer, BaseHTTPRequestHandler
from collections import defaultdict, deque

# environment
load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN")
OLLAMA_URL = os.getenv("OLLAMA_URL")

if not TOKEN:
    raise RuntimeError("DISCORD_TOKEN not set")
if not OLLAMA_URL:
    raise RuntimeError("OLLAMA_URL not set")

# memory
SHORT_TERM_LIMIT = 10
user_memory = defaultdict(lambda: deque(maxlen=SHORT_TERM_LIMIT))

MEMORY_FILE = Path("long_term_memory.json")

def load_long_term_memory():
    if MEMORY_FILE.exists():
        with open(MEMORY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

def save_long_term_memory(memory):
    with open(MEMORY_FILE, "w", encoding="utf-8") as f:
        json.dump(memory, f, indent=2, ensure_ascii=False)

long_term_memory = load_long_term_memory()

# logging
handler = logging.FileHandler(
    filename="discord.log",
    mode="w",
    encoding="utf8"
)

# bot setup
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

# http server
def start_http_server():
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            self.send_response(200)
            self.send_header("Content-type", "text/plain")
            self.end_headers()
            self.wfile.write(b"Bot is running")

        def log_message(self, format, *args):
            return

    port = int(os.getenv("PORT", 8080))
    HTTPServer(("0.0.0.0", port), Handler).serve_forever()

# ollama client
def ollama_chat(prompt, system_prompt, short_memory, long_memory):
    messages = [{"role": "system", "content": system_prompt}]

    if long_memory:
        messages.append({
            "role": "system",
            "content": "Long-term memory about the user:\n" + "\n".join(long_memory)
        })

    messages.extend(short_memory)
    messages.append({"role": "user", "content": prompt})

    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": "qwen2.5:1.5b",
            "messages": messages,
            "stream": False,
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]

def summarize_memory(conversation):
    summary_prompt = (
        "Summarize the following conversation into concise long-term facts "
        "about the user. Keep it factual.\n\n"
    )
    for msg in conversation:
        summary_prompt += f"{msg['role']}: {msg['content']}\n"

    response = requests.post(
        f"{OLLAMA_URL}/api/chat",
        json={
            "model": "qwen2.5:1.5b",
            "messages": [
                {"role": "system", "content": "You summarize conversations."},
                {"role": "user", "content": summary_prompt},
            ],
            "stream": False,
        },
        timeout=120,
    )
    response.raise_for_status()
    return response.json()["message"]["content"]

# events
@bot.event
async def on_ready():
    print(f"{bot.user} is online!")

@bot.event
async def on_member_join(member):
    await member.send(f"Welcome to the server {member.name}")

@bot.event
async def on_message(message):
    if message.author == bot.user:
        return

    # moderation
    if "retard" in message.content.lower():
        await message.delete()
        await message.channel.send(
            f"{message.author.mention} - don't say that word silly!"
        )
        return

    # AI command
    if message.content.startswith("!ai "):
        user_id = str(message.author.id)
        prompt = message.content[4:]

        await message.channel.typing()

        try:
            reply = await asyncio.to_thread(
                ollama_chat,
                prompt,
                system_prompt,
                list(user_memory[user_id]),
                long_term_memory.get(user_id, [])
            )
        except Exception as e:
            print(e)
            await message.channel.send("AI error.")
            return

        # store short-term memory
        user_memory[user_id].append(
            {"role": "user", "content": prompt}
        )
        user_memory[user_id].append(
            {"role": "assistant", "content": reply}
        )

        # summarize into long-term memory when short-term fills
        if len(user_memory[user_id]) >= SHORT_TERM_LIMIT:
            try:
                summary = await asyncio.to_thread(
                    summarize_memory,
                    list(user_memory[user_id])
                )
                long_term_memory.setdefault(user_id, []).append(summary)
                save_long_term_memory(long_term_memory)
                user_memory[user_id].clear()
            except Exception as e:
                print("Summary failed:", e)

        for chunk in (
            reply[i:i + 2000]
            for i in range(0, len(reply), 2000)
        ):
            await message.channel.send(chunk)

    await bot.process_commands(message)

# commands
@bot.command()
async def clear_memory(ctx):
    user_memory.pop(str(ctx.author.id), None)
    await ctx.send("Your short-term memory has been cleared.")

@bot.command()
async def clear_long_memory(ctx):
    long_term_memory.pop(str(ctx.author.id), None)
    save_long_term_memory(long_term_memory)
    await ctx.send("Your long-term memory has been cleared.")

@bot.command()
async def memory(ctx):
    mem = long_term_memory.get(str(ctx.author.id))
    if not mem:
        await ctx.send("No long-term memory stored.")
    else:
        await ctx.send("\n".join(mem[-5:]))

@bot.command()
async def hello(ctx):
    await ctx.send(f"Hello {ctx.author.mention}!")

@bot.command()
async def assign(ctx):
    role = discord.utils.get(ctx.guild.roles, name=secret_role)
    if role:
        await ctx.author.add_roles(role)
        await ctx.send(f"{ctx.author.mention} is now assigned to {secret_role}")
    else:
        await ctx.send("Role doesn't exist")

@bot.command()
async def remove(ctx):
    role = discord.utils.get(ctx.guild.roles, name=secret_role)
    if role:
        await ctx.author.remove_roles(role)
        await ctx.send(f"{ctx.author.mention} has had the {secret_role} removed")
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
    embed = discord.Embed(title="New Poll", description=question)
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

# start server
threading.Thread(
    target=start_http_server,
    daemon=True
).start()

bot.run(TOKEN, log_handler=handler, log_level=logging.DEBUG)
