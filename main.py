from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pymongo import MongoClient
from bson import ObjectId
from datetime import datetime
import os
from typing import Optional

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

MONGO_URI = os.environ.get("MONGO_URI", "mongodb://ISIS2304H26202610:fyVSGbDzWt2h@157.253.236.88:8087")
client = MongoClient(MONGO_URI)
db = client["ISIS2304H26202610"]
resenas = db["resenas"]
votos = db["votos_utilidad"]

# ==================== RF1: Crear reseña ====================
@app.post("/resenas")
def crear_resena(
    id_cliente: int,
    id_reserva: int,
    id_hotel: int,
    calificacion: int,
    texto: str
):
    # Validaciones (simplificadas, falta validación con Oracle)
    if not (1 <= calificacion <= 5):
        raise HTTPException(400, "Calificación 1-5")
    if len(texto.strip()) < 10:
        raise HTTPException(400, "Texto mínimo 10 caracteres")
    
    nueva = {
        "id_reserva": id_reserva,
        "id_cliente": id_cliente,
        "id_hotel": id_hotel,
        "calificacion": calificacion,
        "texto": texto,
        "fecha_creacion": datetime.now(),
        "fecha_actualizacion": datetime.now(),
        "estado": "publicada",
        "destacada": False,
        "votos_utiles": 0
    }
    result = resenas.insert_one(nueva)
    return {"mensaje": "Reseña creada", "id_resena": str(result.inserted_id)}

# ==================== RF2: Editar reseña ====================
@app.put("/resenas/{resena_id}")
def editar_resena(resena_id: str, id_cliente: int, calificacion: Optional[int] = None, texto: Optional[str] = None):
    obj_id = ObjectId(resena_id)
    doc = resenas.find_one({"_id": obj_id})
    if not doc or doc["id_cliente"] != id_cliente:
        raise HTTPException(404, "No encontrada o no autorizado")
    
    updates = {}
    if calificacion is not None:
        if not (1 <= calificacion <= 5):
            raise HTTPException(400, "Calificación 1-5")
        updates["calificacion"] = calificacion
    if texto is not None:
        if len(texto.strip()) < 10:
            raise HTTPException(400, "Texto mínimo 10")
        updates["texto"] = texto
    if not updates:
        raise HTTPException(400, "Nada que actualizar")
    updates["fecha_actualizacion"] = datetime.now()
    resenas.update_one({"_id": obj_id}, {"$set": updates})
    return {"mensaje": "Actualizada"}

# ==================== RF3: Eliminar reseña (cliente) ====================
@app.delete("/resenas/{resena_id}")
def eliminar_resena_cliente(resena_id: str, id_cliente: int):
    obj_id = ObjectId(resena_id)
    doc = resenas.find_one({"_id": obj_id})
    if not doc or doc["id_cliente"] != id_cliente:
        raise HTTPException(404, "No encontrada")
    resenas.update_one({"_id": obj_id}, {"$set": {"estado": "eliminada", "fecha_actualizacion": datetime.now()}})
    return {"mensaje": "Eliminada"}

# ==================== RF4: Listar reseñas de hotel (público) ====================
@app.get("/hoteles/{id_hotel}/resenas")
def listar_resenas(
    id_hotel: int,
    orden: str = Query("fecha", regex="^(fecha|utilidad)$"),
    pagina: int = Query(1, ge=1),
    tamanio: int = Query(10, ge=1, le=50)
):
    skip = (pagina - 1) * tamanio
    filtro = {"id_hotel": id_hotel, "estado": "publicada"}
    sort_criteria = [("fecha_creacion", -1)] if orden == "fecha" else [("votos_utiles", -1), ("fecha_creacion", -1)]
    
    cursor = resenas.find(filtro).sort(sort_criteria).skip(skip).limit(tamanio)
    items = []
    for r in cursor:
        r["id_resena"] = str(r["_id"])
        del r["_id"]
        items.append(r)
    
    total = resenas.count_documents(filtro)
    return {"pagina": pagina, "tamanio": tamanio, "total": total, "resenas": items}

# ==================== RF5: Votar útil ====================
@app.post("/resenas/{resena_id}/votar")
def votar_util(resena_id: str, id_cliente: int):
    obj_id = ObjectId(resena_id)
    # Verificar voto previo en colección votos_utilidad
    if votos.find_one({"id_resena": obj_id, "id_cliente": id_cliente}):
        raise HTTPException(400, "Ya votaste")
    
    votos.insert_one({"id_resena": obj_id, "id_cliente": id_cliente, "fecha": datetime.now()})
    resenas.update_one({"_id": obj_id}, {"$inc": {"votos_utiles": 1}})
    return {"mensaje": "Voto registrado"}

# ==================== RF6: Historial de reseñas propias (¡agregado!) ====================
@app.get("/clientes/{id_cliente}/resenas")
def historial_cliente(
    id_cliente: int,
    orden: str = Query("fecha", regex="^(fecha|hotel)$"),
    pagina: int = Query(1, ge=1),
    tamanio: int = Query(10, ge=1, le=50)
):
    skip = (pagina - 1) * tamanio
    filtro = {"id_cliente": id_cliente}
    if orden == "fecha":
        sort_criteria = [("fecha_creacion", -1)]
    else:  # hotel
        sort_criteria = [("id_hotel", 1), ("fecha_creacion", -1)]
    
    cursor = resenas.find(filtro).sort(sort_criteria).skip(skip).limit(tamanio)
    items = []
    for r in cursor:
        r["id_resena"] = str(r["_id"])
        r["tiene_respuesta"] = "respuesta_admin" in r
        r["num_votos"] = r.get("votos_utiles", 0)
        del r["_id"]
        items.append(r)
    total = resenas.count_documents(filtro)
    return {"pagina": pagina, "tamanio": tamanio, "total": total, "resenas": items}

# ==================== RF7: Responder (admin) ====================
@app.put("/admin/resenas/{resena_id}/respuesta")
def responder_admin(resena_id: str, id_admin: int, texto: str):
    obj_id = ObjectId(resena_id)
    if len(texto.strip()) < 5:
        raise HTTPException(400, "Respuesta muy corta")
    res = resenas.update_one(
        {"_id": obj_id},
        {"$set": {"respuesta_admin": {"texto": texto, "fecha": datetime.now(), "id_admin": id_admin}}}
    )
    if res.matched_count == 0:
        raise HTTPException(404, "Reseña no encontrada")
    return {"mensaje": "Respuesta guardada"}

# ==================== RF8: Eliminar reseña (admin) ====================
@app.delete("/admin/resenas/{resena_id}")
def eliminar_admin(resena_id: str, id_admin: int):
    obj_id = ObjectId(resena_id)
    res = resenas.update_one({"_id": obj_id}, {"$set": {"estado": "eliminada"}})
    if res.matched_count == 0:
        raise HTTPException(404, "No encontrada")
    return {"mensaje": "Eliminada por admin"}

# ==================== RF9: Destacar reseña ====================
@app.post("/admin/resenas/{resena_id}/destacar")
def destacar(resena_id: str, id_admin: int):
    obj_id = ObjectId(resena_id)
    doc = resenas.find_one({"_id": obj_id})
    if not doc:
        raise HTTPException(404, "No existe")
    hotel_id = doc["id_hotel"]
    # Quitar destacada de otras del mismo hotel
    resenas.update_many({"id_hotel": hotel_id, "destacada": True}, {"$set": {"destacada": False}})
    resenas.update_one({"_id": obj_id}, {"$set": {"destacada": True}})
    return {"mensaje": f"Reseña destacada para hotel {hotel_id}"}

# ==================== RFC1: Top 10 hoteles ====================
@app.get("/rfc1/top-hoteles")
def top_hoteles(fecha_inicio: str, fecha_fin: str):
    start = datetime.fromisoformat(fecha_inicio)
    end = datetime.fromisoformat(fecha_fin)
    pipeline = [
        {"$match": {"estado": "publicada", "fecha_creacion": {"$gte": start, "$lte": end}}},
        {"$group": {"_id": "$id_hotel", "promedio": {"$avg": "$calificacion"}, "total": {"$sum": 1}}},
        {"$addFields": {"promedio": {"$round": ["$promedio", 2]}}},
        {"$sort": {"promedio": -1, "total": -1}},
        {"$limit": 10}
    ]
    return list(resenas.aggregate(pipeline))

# ==================== RFC2: Evolución mensual ====================
@app.get("/rfc2/evolucion/{id_hotel}")
def evolucion(id_hotel: int, anio: int):
    start = datetime(anio, 1, 1)
    end = datetime(anio, 12, 31, 23, 59, 59)
    pipeline = [
        {"$match": {"id_hotel": id_hotel, "estado": "publicada", "fecha_creacion": {"$gte": start, "$lte": end}}},
        {"$group": {"_id": {"$month": "$fecha_creacion"}, "promedio": {"$avg": "$calificacion"}, "total": {"$sum": 1}}},
        {"$addFields": {"promedio": {"$round": ["$promedio", 2]}}},
        {"$sort": {"_id": 1}}
    ]
    return list(resenas.aggregate(pipeline))

# ==================== RFC3: Comparativo ciudad (sin colección hoteles, usa mapeo fijo) ====================
# Mapeo de ciudad a lista de id_hotel (debes ajustar según tus datos reales)
CIUDAD_HOTELES = {
    "Bogotá": [1, 2, 3],
    "Medellín": [4, 5, 6],
    "Cali": [7, 8, 9]
}

@app.get("/rfc3/comparativo/{ciudad}")
def comparativo(ciudad: str):
    hoteles = CIUDAD_HOTELES.get(ciudad)
    if not hoteles:
        raise HTTPException(404, "Ciudad no encontrada")
    pipeline = [
        {"$match": {"id_hotel": {"$in": hoteles}, "estado": "publicada"}},
        {"$group": {
            "_id": "$id_hotel",
            "promedio": {"$avg": "$calificacion"},
            "total": {"$sum": 1},
            "con_respuesta": {"$sum": {"$cond": [{"$ifNull": ["$respuesta_admin", False]}, 1, 0]}},
            "destacadas": {"$sum": {"$cond": ["$destacada", 1, 0]}}
        }},
        {"$addFields": {
            "promedio": {"$round": ["$promedio", 2]},
            "%respuesta": {"$round": [{"$multiply": [{"$divide": ["$con_respuesta", "$total"]}, 100]}, 1]},
            "%destacadas": {"$round": [{"$multiply": [{"$divide": ["$destacadas", "$total"]}, 100]}, 1]}
        }},
        {"$project": {"_id": 0, "id_hotel": "$_id", "calificacion_promedio": "$promedio", 
                      "total_resenas": "$total", "porcentaje_con_respuesta": "$%respuesta",
                      "porcentaje_destacadas": "$%destacadas"}}
    ]
    return list(resenas.aggregate(pipeline))

# ==================== Health ====================
@app.get("/")
def root():
    return {"api": "Dann-Alpes", "status": "ok"}