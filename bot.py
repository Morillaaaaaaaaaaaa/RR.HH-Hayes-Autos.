import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import json
import os
import datetime
import subprocess

# ================= CONFIGURACIÓN =================
CANALES_TRABAJADORES = [
    1431761299934679060,  # Luis
    1431761351025627248,  # Roberth
    1431761413541728451   # Andrew
]

ARCHIVO_HORAS = "horas_trabajadores.json"

# ================= CARGAR O CREAR DATOS =================
if os.path.exists(ARCHIVO_HORAS):
    try:
        with open(ARCHIVO_HORAS, "r") as f:
            horas_trabajadores = json.load(f)
    except json.JSONDecodeError:
        print("⚠️ JSON corrupto, se inicializa vacío.")
        horas_trabajadores = {}
else:
    horas_trabajadores = {}

# Asegurar que cada canal tenga la estructura correcta
for canal_id in CANALES_TRABAJADORES:
    cid = str(canal_id)
    if cid not in horas_trabajadores or not isinstance(horas_trabajadores[cid], dict):
        horas_trabajadores[cid] = {"ingreso": None, "total_segundos": 0, "mensaje_id": None}

# ================= FUNCIONES =================
def guardar_y_subir_json():
    try:
        with open(ARCHIVO_HORAS, "w") as f:
            json.dump(horas_trabajadores, f, indent=4)

        subprocess.run(["git", "config", "user.email", "bot@example.com"], check=True)
        subprocess.run(["git", "config", "user.name", "Bot de Horas"], check=True)
        subprocess.run(["git", "add", ARCHIVO_HORAS], check=True)
        subprocess.run(["git", "commit", "-m", "Actualizar horas desde bot"], check=True)

        remote_url = f"https://{os.getenv('GITHUB_TOKEN')}@github.com/<usuario>/<repo>.git"
        subprocess.run(["git", "push", remote_url, "HEAD:main"], check=True)
        print("✅ JSON actualizado y subido a GitHub.")
    except subprocess.CalledProcessError as e:
        print(f"⚠️ Error al subir JSON a GitHub: {e}")

def format_horas(segundos_totales):
    segundos_totales *= 60  # Simulación rápida: 1s real = 1m simulado
    horas = int(segundos_totales // 3600)
    minutos = int((segundos_totales % 3600) // 60)
    return f"{horas}h {minutos}m"

async def actualizar_mensaje(channel, mensaje_id):
    try:
        msg = await channel.fetch_message(mensaje_id)
    except discord.NotFound:
        # Crear mensaje si no existe
        embed = discord.Embed(title="🏢 Fichaje del taller", description="No hay registros todavía.", color=0x2ecc71)
        msg = await channel.send(embed=embed)
        for cid, datos in horas_trabajadores.items():
            if int(cid) == channel.id:
                datos["mensaje_id"] = msg.id
                guardar_y_subir_json()

    ranking_text = ""
    for canal_id, datos in horas_trabajadores.items():
        ch = bot.get_channel(int(canal_id))
        nombre = ch.name if ch else f"Canal {canal_id}"
        ranking_text += f"**{nombre}**: {format_horas(datos.get('total_segundos', 0))}\n"

    embed = discord.Embed(
        title="🏢 Fichaje del taller",
        description=ranking_text or "No hay registros todavía.",
        color=0x2ecc71,
        timestamp=datetime.datetime.utcnow()
    )
    await msg.edit(embed=embed)

# ================= BOT =================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

class FichajeView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(label="🟢 Ingreso", style=discord.ButtonStyle.success, custom_id="ingreso"))
        self.add_item(Button(label="🔴 Retirada", style=discord.ButtonStyle.danger, custom_id="retirada"))
        self.add_item(Button(label="📊 Horas totales", style=discord.ButtonStyle.primary, custom_id="horas"))

# ================= EVENTOS =================
@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    for guild in bot.guilds:
        for canal_id in CANALES_TRABAJADORES:
            canal = guild.get_channel(canal_id)
            if canal:
                # Borrar últimos mensajes del bot
                try:
                    async for msg in canal.history(limit=10):
                        if msg.author == bot.user:
                            await msg.delete()
                except Exception as e:
                    print(f"⚠️ No se pudieron borrar mensajes en {canal.name}: {e}")

                # Enviar panel de botones
                view = FichajeView()
                embed = discord.Embed(
                    title="💼 Panel de fichaje del taller",
                    description="Selecciona una opción:",
                    color=0x3498db
                )
                try:
                    mensaje = await canal.send(embed=embed, view=view)
                    horas_trabajadores[str(canal.id)]["mensaje_id"] = mensaje.id
                    guardar_y_subir_json()
                    print(f"📋 Panel enviado en #{canal.name}")
                except Exception as e:
                    print(f"⚠️ No se pudo enviar panel en {canal.name}: {e}")

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data.get("custom_id")
    canal_id = str(interaction.channel.id)
    ahora = datetime.datetime.now()

    if canal_id not in horas_trabajadores:
        horas_trabajadores[canal_id] = {"ingreso": None, "total_segundos": 0, "mensaje_id": None}

    datos = horas_trabajadores[canal_id]

    if custom_id == "ingreso":
        if datos["ingreso"]:
            await interaction.response.send_message("⚠️ Ya habías fichado tu entrada.", ephemeral=True)
            return
        datos["ingreso"] = ahora.isoformat()
        guardar_y_subir_json()
        await interaction.response.send_message("✅ Has fichado tu **entrada**.", ephemeral=True)

    elif custom_id == "retirada":
        if not datos["ingreso"]:
            await interaction.response.send_message("⚠️ No habías fichado entrada.", ephemeral=True)
            return
        inicio = datetime.datetime.fromisoformat(datos["ingreso"])
        segundos = (ahora - inicio).total_seconds() * 60  # simulación rápida
        datos["total_segundos"] += segundos
        datos["ingreso"] = None
        guardar_y_subir_json()
        await interaction.response.send_message(
            f"✅ Has fichado tu **salida**. Has trabajado {format_horas(segundos)}.", 
            ephemeral=True
        )
        # actualizar mensaje de horas
        mensaje_id = datos.get("mensaje_id")
        if mensaje_id:
            await actualizar_mensaje(interaction.channel, mensaje_id)

    elif custom_id == "horas":
        total = datos.get("total_segundos", 0)
        if datos["ingreso"]:
            inicio = datetime.datetime.fromisoformat(datos["ingreso"])
            total += (ahora - inicio).total_seconds() * 60
        await interaction.response.send_message(
            f"⏱️ Has trabajado un total de **{format_horas(total)}** en este canal.",
            ephemeral=True
        )

# ================= EJECUTAR BOT =================
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("⚠️ La variable de entorno DISCORD_TOKEN no está configurada.")

bot.run(TOKEN)
