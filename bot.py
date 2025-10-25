import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import json
import os
import datetime
import subprocess

# ================= CONFIGURACIÓN =================
CANALES_TRABAJADORES = [
    1428906272542953573,
    1428906286971617402,
    1428906299030114345
    # Agrega más canales si quieres
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
        horas_trabajadores[str(canal_id)] = {"ingreso": None, "total_segundos": 0}

def guardar_datos():
    try:
        with open(ARCHIVO_HORAS, "w") as f:
            json.dump(horas_trabajadores, f, indent=4)
        # Commit y push al repo privado
        subprocess.run(["git", "add", ARCHIVO_HORAS])
        subprocess.run(["git", "commit", "-m", "Actualización de horas"])
        subprocess.run(["git", "push"])
    except Exception as e:
        print(f"⚠️ Error guardando JSON o haciendo push: {e}")

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
    # Para testeo, aceleramos el tiempo: 1 segundo real = 1 minuto simulado
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
                    # Guardamos el ID del mensaje para futuras ediciones
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
            # Tiempo acelerado: 1 segundo real = 1 minuto simulado
            segundos = (ahora - inicio).total_seconds() * 60
            datos["total_segundos"] += segundos
            datos["ingreso"] = None
            guardar_datos()
            await interaction.response.send_message(
                f"✅ Has fichado tu **salida**. Has trabajado {format_horas(segundos)}.", 
                ephemeral=True
            )
            # Actualizar el mensaje con las horas
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
            total += (ahora - inicio).total_seconds() * 60  # acelerar tiempo
        await interaction.response.send_message(f"⏱️ Has trabajado un total de **{format_horas(total)}** en este canal.", ephemeral=True)

# ================= EJECUTAR BOT =================
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("⚠️ La variable de entorno DISCORD_TOKEN no está configurada.")

bot.run(TOKEN)
