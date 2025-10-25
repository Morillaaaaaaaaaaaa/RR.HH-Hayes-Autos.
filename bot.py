import discord
from discord.ext import commands, tasks
from discord.ui import View, Button
import json
import os
import datetime
import subprocess
import asyncio

# ================= CONFIGURACIÓN =================
CANALES_TRABAJADORES = [
    1431761299934679060,  # Luis Morilla
    1431761351025627248,  # Roberth Venet
    1431761413541728451   # Andrew Simmons
]

CANAL_DIRECCION_ID = 1431761591514435725  # Canal donde se mostrarán las horas totales
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

# Aseguramos la estructura por cada canal de trabajador
for canal_id in CANALES_TRABAJADORES:
    if str(canal_id) not in horas_trabajadores or not isinstance(horas_trabajadores[str(canal_id)], dict):
        horas_trabajadores[str(canal_id)] = {
            "ingreso": None,
            "total_segundos": 0,
            "mensaje_id": None  # ID del panel con botones en ese canal
        }

def guardar_datos():
    """Guarda el JSON y hace commit/push al repo privado (si está configurado)."""
    try:
        with open(ARCHIVO_HORAS, "w") as f:
            json.dump(horas_trabajadores, f, indent=4)
        # Hacemos commit push opcional; si no hay credenciales o hay conflicto, lo atrapa la excepción
        subprocess.run(["git", "add", ARCHIVO_HORAS], check=False)
        subprocess.run(["git", "commit", "-m", "Actualización automática de horas"], check=False)
        subprocess.run(["git", "push"], check=False)
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
    """Formatea segundos a 'Xh Ym'. Se aplica simulación: 1s real = 1m simulado (multiplica por 60)."""
    segundos_totales *= 60  # 1s real = 1m simulado
    horas = int(segundos_totales // 3600)
    minutos = int((segundos_totales % 3600) // 60)
    return f"{horas}h {minutos}m"

async def publicar_resumen_direccion():
    """Publica un resumen total de horas en el canal de dirección (no lo limpiamos)."""
    canal = bot.get_channel(CANAL_DIRECCION_ID)
    if not canal:
        print("⚠️ No se encontró el canal de dirección.")
        return

    resumen = ""
    for canal_id, datos in horas_trabajadores.items():
        ch = bot.get_channel(int(canal_id))
        nombre = ch.name if ch else f"Canal {canal_id}"
        resumen += f"**{nombre}**: {format_horas(datos.get('total_segundos', 0))}\n"

    embed = discord.Embed(
        title="📋 Resumen total de horas trabajadas",
        description=resumen or "Aún no hay registros.",
        color=0x2ecc71,
        timestamp=datetime.datetime.utcnow()
    )
    await canal.send(embed=embed)

# ================= LIMPIEZA DE CANALES DE TRABAJADORES =================
@tasks.loop(minutes=5)  # Para pruebas: cada 5 minutos. Cambiar a hours=12 cuando esté listo.
async def limpiar_canales_trabajadores():
    """Borra los mensajes del bot en los canales de los trabajadores, excepto el panel (mensaje_id)."""
    await bot.wait_until_ready()
    for canal_id in CANALES_TRABAJADORES:
        ch = bot.get_channel(int(canal_id))
        if not ch:
            continue

        panel_id = horas_trabajadores.get(str(canal_id), {}).get("mensaje_id")
        try:
            # Recorremos el historial y borramos mensajes del bot que NO sean el panel
            async for msg in ch.history(limit=200):
                try:
                    if msg.author == bot.user and (panel_id is None or msg.id != panel_id):
                        await msg.delete()
                except discord.Forbidden:
                    # No permisos para borrar mensajes en ese canal
                    print(f"⚠️ No tengo permisos para borrar mensajes en #{ch.name}")
                    break
                except discord.NotFound:
                    continue
                except Exception as e:
                    print(f"⚠️ Error borrando mensajes en #{ch.name}: {e}")
            # Re-enviamos el panel si el panel_id no existe o fue borrado por alguien
            if panel_id:
                try:
                    await ch.fetch_message(panel_id)
                except discord.NotFound:
                    # Panel desapareció: reenviarlo y guardar nuevo id
                    view = FichajeView()
                    embed = discord.Embed(
                        title="🕐 Sistema de fichaje Hayes Autos",
                        description="Selecciona una opción para registrar tu jornada:",
                        color=0x3498db
                    )
                    mensaje = await ch.send(embed=embed, view=view)
                    horas_trabajadores[str(canal_id)]["mensaje_id"] = mensaje.id
                    guardar_datos()
            else:
                # Nunca se creó un panel: crear uno ahora y guardar id
                view = FichajeView()
                embed = discord.Embed(
                    title="🕐 Sistema de fichaje Hayes Autos",
                    description="Selecciona una opción para registrar tu jornada:",
                    color=0x3498db
                )
                mensaje = await ch.send(embed=embed, view=view)
                horas_trabajadores[str(canal_id)]["mensaje_id"] = mensaje.id
                guardar_datos()

        except Exception as e:
            print(f"⚠️ Error en limpieza canal {canal_id}: {e}")

# ================= EVENTO ON_READY =================
@bot.event
async def on_ready():
    print(f"✅ Bot conectado como {bot.user}")
    limpiar_canales_trabajadores.start()  # Inicia limpieza periódica
    for guild in bot.guilds:
        for canal_id in CANALES_TRABAJADORES:
            canal = guild.get_channel(canal_id)
            if canal:
                # Eliminar mensajes recientes del bot para dejar el canal limpio (mantendremos panel)
                try:
                    async for msg in canal.history(limit=50):
                        if msg.author == bot.user:
                            # Si es el panel registrado lo mantenemos, si no lo borramos
                            panel_id = horas_trabajadores.get(str(canal.id), {}).get("mensaje_id")
                            if panel_id is None or msg.id != panel_id:
                                await msg.delete()
                except Exception:
                    pass

                # Enviar panel si no existe y almacenar su ID
                try:
                    panel_id = horas_trabajadores.get(str(canal.id), {}).get("mensaje_id")
                    if panel_id:
                        try:
                            await canal.fetch_message(panel_id)
                        except discord.NotFound:
                            panel_id = None
                    if not panel_id:
                        view = FichajeView()
                        embed = discord.Embed(
                            title="🕐 Sistema de fichaje Hayes Autos",
                            description="Selecciona una opción para registrar tu jornada:",
                            color=0x3498db
                        )
                        mensaje = await canal.send(embed=embed, view=view)
                        horas_trabajadores[str(canal.id)]["mensaje_id"] = mensaje.id
                        guardar_datos()
                    print(f"📋 Panel asegurado en #{canal.name}")
                except Exception as e:
                    print(f"⚠️ No se pudo enviar/asegurar panel en {canal.name}: {e}")

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

    # RESPONDE RÁPIDO para evitar timeout de Discord
    if custom_id == "ingreso":
        if datos.get("ingreso"):
            await interaction.response.send_message("⚠️ Ya habías fichado tu entrada.", ephemeral=True)
            return
        datos["ingreso"] = ahora.isoformat()
        guardar_datos()
        await interaction.response.send_message("✅ Has fichado tu **entrada**.", ephemeral=True)
        return

    if custom_id == "retirada":
        if not datos.get("ingreso"):
            await interaction.response.send_message("⚠️ No habías fichado entrada.", ephemeral=True)
            return
        try:
            inicio = datetime.datetime.fromisoformat(datos["ingreso"])
            segundos = (ahora - inicio).total_seconds() * 60  # Simulación rápida
            datos["total_segundos"] += segundos
            datos["ingreso"] = None
            guardar_datos()
            await interaction.response.send_message(
                f"✅ Has fichado tu **salida**. Has trabajado {format_horas(segundos)}.",
                ephemeral=True
            )
            # Publicar resumen en canal de dirección (no lo limpiamos)
            await publicar_resumen_direccion()
        except Exception as e:
            # Si algo falla antes de responder, usar followup
            try:
                await interaction.followup.send(f"⚠️ Error al calcular horas: {e}", ephemeral=True)
            except Exception:
                print(f"⚠️ Error manejando excepción: {e}")
        return

    if custom_id == "horas":
        total = datos.get("total_segundos", 0)
        if datos.get("ingreso"):
            inicio = datetime.datetime.fromisoformat(datos["ingreso"])
            total += (ahora - inicio).total_seconds() * 60
        await interaction.response.send_message(f"⏱️ Has trabajado un total de **{format_horas(total)}** en este canal.", ephemeral=True)
        return

# ================= EJECUTAR BOT =================
TOKEN = os.getenv("DISCORD_TOKEN")
if not TOKEN:
    raise ValueError("⚠️ La variable de entorno DISCORD_TOKEN no está configurada.")

bot.run(TOKEN)
