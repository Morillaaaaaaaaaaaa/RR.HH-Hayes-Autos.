import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import json
import os
import datetime

# ================= CONFIGURACIÓN =================
CANALES_TRABAJADORES = [
    1431761299934679060,  # Luis Morilla
    1431761351025627248,  # Roberth Venet
    1431761413541728451   # Andrew Simmons
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

for canal_id in CANALES_TRABAJADORES:
    if str(canal_id) not in horas_trabajadores:
        horas_trabajadores[str(canal_id)] = {"ingreso": None, "total_segundos": 0, "mensaje_id": None}

def guardar_datos():
    try:
        with open(ARCHIVO_HORAS, "w") as f:
            json.dump(horas_trabajadores, f, indent=4)
    except Exception as e:
        print(f"⚠️ Error guardando JSON: {e}")

# ================= BOT =================
intents = discord.Intents.default()
intents.message_content = True
bot = commands.Bot(command_prefix="!", intents=intents)

# ================= VISTA DE BOTONES =================
class FichajeView(View):
    def __init__(self):
        super().__init__(timeout=None)
        self.add_item(Button(label="🟢 Ingreso", style=discord.ButtonStyle.success, custom_id="ingreso"))
        self.add_item(Button(label="🔴 Retirada", style=discord.ButtonStyle.danger, custom_id="retirada"))
        self.add_item(Button(label="📊 Horas totales", style=discord.ButtonStyle.primary, custom_id="horas"))

# ================= FUNCIONES AUXILIARES =================
def format_horas(segundos_totales):
    segundos_totales *= 60  # 1s real = 1m simulado
    horas = int(segundos_totales // 3600)
    minutos = int((segundos_totales % 3600) // 60)
    return f"{horas}h {minutos}m"

async def actualizar_mensaje(channel, mensaje_id):
    try:
        msg = await channel.fetch_message(mensaje_id)
    except:
        return
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

# ================= EVENTO ON_READY =================
@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    for guild in bot.guilds:
        for canal_id in CANALES_TRABAJADORES:
            canal = guild.get_channel(canal_id)
            if canal:
                # Borrar últimos mensajes del bot excepto el panel
                mensaje_bot_id = horas_trabajadores[str(canal.id)].get("mensaje_id")
                async for msg in canal.history(limit=20):
                    if msg.author == bot.user and msg.id != mensaje_bot_id:
                        await msg.delete()

                # Enviar panel de botones si no existe
                if not horas_trabajadores[str(canal.id)].get("mensaje_id"):
                    view = FichajeView()
                    embed = discord.Embed(
                        title="💼 Panel de fichaje del taller",
                        description="Selecciona una opción:",
                        color=0x3498db
                    )
                    try:
                        mensaje = await canal.send(embed=embed, view=view)
                        horas_trabajadores[str(canal.id)]["mensaje_id"] = mensaje.id
                        guardar_datos()
                        print(f"📋 Panel enviado en #{canal.name}")
                    except Exception as e:
                        print(f"⚠️ No se pudo enviar panel en {canal.name}: {e}")

# ================= EVENTO ON_INTERACTION =================
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

    # ===== INGRESO =====
    if custom_id == "ingreso":
        if datos["ingreso"]:
            await interaction.response.send_message("⚠️ Ya habías fichado tu entrada.", ephemeral=True)
            return
        datos["ingreso"] = ahora.isoformat()
        guardar_datos()
        await interaction.response.send_message("✅ Has fichado tu **entrada**.", ephemeral=True)

    # ===== RETIRADA =====
    elif custom_id == "retirada":
        if not datos["ingreso"]:
            await interaction.response.send_message("⚠️ No habías fichado entrada.", ephemeral=True)
            return
        try:
            inicio = datetime.datetime.fromisoformat(datos["ingreso"])
            segundos = (ahora - inicio).total_seconds() * 60
            datos["total_segundos"] += segundos
            datos["ingreso"] = None
            guardar_datos()
            await interaction.response.send_message(
                f"✅ Has fichado tu **salida**. Has trabajado {format_horas(segundos)}.",
                ephemeral=True
            )
            mensaje_id = datos.get("mensaje_id")
            if mensaje_id:
                await actualizar_mensaje(interaction.channel, mensaje_id)
        except Exception as e:
            await interaction.response.send_message(f"⚠️ Error al calcular horas: {e}", ephemeral=True)

    # ===== HORAS TOTALES =====
    elif custom_id == "horas":
        total = datos.get("total_segundos", 0)
        if datos["ingreso"]:
            inicio = datetime.datetime.fromisoformat(datos["ingreso"])
            total += (ahora - inicio).total_seconds() * 60
        await interaction.response.send_message(f"⏱️ Has trabajado un total de **{format_horas(total)}** en este canal.", ephemeral=True)

# ================= COMANDO LIMPIAR =================
@bot.command(name="limpiar")
@commands.has_permissions(administrator=True)
async def limpiar(ctx):
    canal = ctx.channel
    borrados = 0
    mensaje_bot_id = horas_trabajadores.get(str(canal.id), {}).get("mensaje_id")
    async for msg in canal.history(limit=100):
        if msg.author == bot.user and msg.id != mensaje_bot_id:
            await msg.delete()
            borrados += 1
    await ctx.send(f"🧹 He borrado {borrados} mensajes de fichaje.", delete_after=5)

# ================= EJECUTAR BOT =================
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("⚠️ La variable de entorno DISCORD_TOKEN no está configurada.")

bot.run(TOKEN)
