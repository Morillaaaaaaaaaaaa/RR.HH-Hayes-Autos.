import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import json
import os
import datetime

# ================= CONFIGURACIÓN =================
CANALES_TRABAJADORES = [
    1431761299934679060,  # Luis
    1431761351025627248,  # Roberth
    1431761413541728451   # Andrew
]

CANAL_HORAS_ID = 1431761591514435725  # Canal de horas trabajadas

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

# Validar que cada canal tenga la estructura correcta
for canal_id in CANALES_TRABAJADORES:
    clave = str(canal_id)
    if clave not in horas_trabajadores or not isinstance(horas_trabajadores[clave], dict):
        horas_trabajadores[clave] = {"ingreso": None, "total_segundos": 0}

def guardar_datos():
    try:
        with open(ARCHIVO_HORAS, "w") as f:
            json.dump(horas_trabajadores, f, indent=4)
    except Exception as e:
        print(f"⚠️ Error guardando JSON: {e}")

guardar_datos()

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
        self.add_item(Button(label="⏱️ Horas totales", style=discord.ButtonStyle.primary, custom_id="horas"))

# ================= FUNCIONES AUXILIARES =================
def segundos_a_horas_minutos(segundos):
    horas = int(segundos // 3600)
    minutos = int((segundos % 3600) // 60)
    return f"{horas}h {minutos}m"

# ================= RANKING DE HORAS =================
mensaje_horas_id = None  # ID del mensaje en el canal de horas

async def actualizar_mensaje_horas():
    global mensaje_horas_id
    canal = bot.get_channel(CANAL_HORAS_ID)
    if not canal:
        return

    ranking_text = ""
    for canal_id, datos in horas_trabajadores.items():
        # Validar estructura de cada dato
        if not isinstance(datos, dict):
            horas_trabajadores[canal_id] = {"ingreso": None, "total_segundos": 0}
            datos = horas_trabajadores[canal_id]

        total_tiempo = segundos_a_horas_minutos(datos.get("total_segundos", 0))
        ch = bot.get_channel(int(canal_id))
        nombre = ch.name if ch else f"Canal {canal_id}"
        ranking_text += f"**{nombre}**: {total_tiempo}\n"

    embed = discord.Embed(
        title="🏆 Horas trabajadas (Directiva)",
        description=ranking_text or "No hay registros todavía.",
        color=0x2ecc71,
        timestamp=datetime.datetime.utcnow()
    )

    if mensaje_horas_id:
        try:
            msg = await canal.fetch_message(mensaje_horas_id)
            await msg.edit(embed=embed)
        except discord.NotFound:
            msg = await canal.send(embed=embed)
            mensaje_horas_id = msg.id
    else:
        msg = await canal.send(embed=embed)
        mensaje_horas_id = msg.id

# ================= LIMPIEZA DE CANALES DE FICHAJE =================
@tasks.loop(minutes=5)
async def limpiar_canales_fichajes():
    for canal_id in CANALES_TRABAJADORES:
        canal = bot.get_channel(canal_id)
        if canal:
            try:
                async for msg in canal.history(limit=20):
                    if msg.author == bot.user:
                        await msg.delete()
            except Exception as e:
                print(f"⚠️ No se pudieron borrar mensajes en {canal.name}: {e}")

# ================= EVENTOS =================
@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    limpiar_canales_fichajes.start()
    for guild in bot.guilds:
        for canal_id in CANALES_TRABAJADORES:
            canal = guild.get_channel(canal_id)
            if canal:
                view = FichajeView()
                embed = discord.Embed(
                    title="💼 Sistema de fichaje",
                    description="Selecciona una opción para registrar tu tiempo:",
                    color=0x3498db
                )
                try:
                    await canal.send(embed=embed, view=view)
                    print(f"📋 Panel enviado en #{canal.name}")
                except Exception as e:
                    print(f"⚠️ No se pudo enviar panel en {canal.name}: {e}")
    await actualizar_mensaje_horas()

@bot.event
async def on_interaction(interaction: discord.Interaction):
    if interaction.type != discord.InteractionType.component:
        return

    custom_id = interaction.data.get("custom_id")
    canal_id = str(interaction.channel.id)
    ahora = datetime.datetime.now()

    if canal_id not in horas_trabajadores or not isinstance(horas_trabajadores[canal_id], dict):
        horas_trabajadores[canal_id] = {"ingreso": None, "total_segundos": 0}

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
            # Simulación rápida: cada segundo real = 1 minuto de trabajo
            segundos_trabajados = (ahora - inicio).total_seconds() * 60
            datos["total_segundos"] += segundos_trabajados
            datos["ingreso"] = None
            guardar_datos()
            await interaction.response.send_message(
                f"✅ Has fichado tu **salida**. Has trabajado {segundos_a_horas_minutos(segundos_trabajados)}.", 
                ephemeral=True
            )
            await actualizar_mensaje_horas()
        except Exception as e:
            await interaction.response.send_message(f"⚠️ Error al calcular horas: {e}", ephemeral=True)

    # ===== HORAS TOTALES =====
    elif custom_id == "horas":
        total_segundos = datos.get("total_segundos", 0)
        await interaction.response.send_message(
            f"⏱️ Has trabajado un total de **{segundos_a_horas_minutos(total_segundos)}** en este canal.",
            ephemeral=True
        )

# ================= EJECUTAR BOT =================
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("⚠️ La variable de entorno DISCORD_TOKEN no está configurada.")

bot.run(TOKEN)
