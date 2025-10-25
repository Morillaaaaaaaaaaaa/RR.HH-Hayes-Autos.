import discord
from discord.ext import commands
from discord.ui import View, Button
import json
import os
import datetime

# ================= CONFIGURACIÓN =================
CANALES_TRABAJADORES = [
    1428906272542953573,
    1428906286971617402,
    1428906299030114345,
    1428906312061943898,
    1428906327220031691,
    1428906337391345794,
    1428906361944674314,
    1428906373143461899,
    1428906380454006970,
    1428906391816503336,
    1428906401983369236,
    1428906429376630935,
    1428906445390352536,
    1428906455473459343,
    1428906470875074622,
    1428906485794082877
]

CANAL_RANKING_ID = 1428919005032353792
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
        horas_trabajadores[str(canal_id)] = {"ingreso": None, "total_minutos": 0}

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
        self.add_item(Button(label="📊 Horas totales", style=discord.ButtonStyle.primary, custom_id="horas"))

# ================= FUNCIONES AUXILIARES =================
def calcular_horas(minutos):
    return round(minutos / 60, 2)

async def actualizar_ranking():
    canal = bot.get_channel(CANAL_RANKING_ID)
    if not canal:
        return

    ranking_text = ""
    for canal_id, datos in horas_trabajadores.items():
        total_horas = calcular_horas(datos.get("total_minutos", 0))
        ch = bot.get_channel(int(canal_id))
        nombre = ch.name if ch else f"Canal {canal_id}"
        ranking_text += f"**{nombre}**: {total_horas} horas\n"

    embed = discord.Embed(
        title="🏆 Ranking de horas trabajadas",
        description=ranking_text or "No hay registros todavía.",
        color=0x2ecc71,
        timestamp=datetime.datetime.utcnow()
    )
    await canal.send(embed=embed)

# ================= EVENTO ON_READY =================
@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    for guild in bot.guilds:
        for canal_id in CANALES_TRABAJADORES:
            canal = guild.get_channel(canal_id)
            if canal:
                try:
                    async for msg in canal.history(limit=10):
                        if msg.author == bot.user:
                            await msg.delete()
                except Exception as e:
                    print(f"⚠️ No se pudieron borrar mensajes en {canal.name}: {e}")

                view = FichajeView()
                embed = discord.Embed(
                    title="💼 Ministerio de Trabajo",
                    description="Sistema de fichaje del taller\nSelecciona una opción:",
                    color=0x3498db
                )
                try:
                    await canal.send(embed=embed, view=view)
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
        horas_trabajadores[canal_id] = {"ingreso": None, "total_minutos": 0}

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
            minutos = (ahora - inicio).total_seconds() / 60
            datos["total_minutos"] += minutos
            datos["ingreso"] = None
            guardar_datos()
            await interaction.response.send_message(
                f"✅ Has fichado tu **salida**. Has trabajado {calcular_horas(minutos)} horas.", 
                ephemeral=True
            )
            await actualizar_ranking()
        except Exception as e:
            await interaction.response.send_message(f"⚠️ Error al calcular horas: {e}", ephemeral=True)

    # ===== HORAS TOTALES =====
    elif custom_id == "horas":
        total_horas = calcular_horas(datos.get("total_minutos", 0))
        await interaction.response.send_message(f"⏱️ Has trabajado un total de **{total_horas} horas** en este canal.", ephemeral=True)

# ================= EJECUTAR BOT =================
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("⚠️ La variable de entorno DISCORD_TOKEN no está configurada.")

bot.run(TOKEN)
