from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from ytmusicapi import YTMusic
from typing import Optional
import uvicorn
import os
import traceback

app = FastAPI(
    title="YouTube Music Proxy API",
    description="Proxy para o app Flutter consumir dados do YouTube Music.",
    version="1.0.0"
)

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ytmusic = YTMusic()

@app.get("/")
async def root():
    return {"message": "YouTube Music Proxy API está rodando!"}

@app.get("/search")
async def search(
    q: str = Query(..., min_length=1, description="Termo de busca"),
    limit: Optional[int] = Query(20, ge=1, le=50, description="Número máximo de resultados")
):
    try:
        results = ytmusic.search(q, limit=limit)
        # Filtra resultados que podem causar erro de parsing
        filtered = []
        for item in results:
            try:
                # Tenta acessar um campo básico para ver se o item é válido
                _ = item.get('resultType', 'unknown')
                filtered.append(item)
            except Exception:
                # Se falhar, ignora o item
                continue
        return {"query": q, "results": filtered}
    except Exception as e:
        print(f"❌ Erro na busca: {e}")
        traceback.print_exc()
        # Retorna uma resposta vazia em vez de erro 500
        return {"query": q, "results": []}

@app.get("/get_song")
async def get_song(videoId: str = Query(...)):
    try:
        song_data = ytmusic.get_song(videoId)
        return song_data
    except Exception as e:
        print(f"❌ Erro ao obter música: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/get_album")
async def get_album(browseId: str = Query(...)):
    try:
        album_data = ytmusic.get_album(browseId)
        return album_data
    except Exception as e:
        print(f"❌ Erro ao obter álbum: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/get_playlist")
async def get_playlist(playlistId: str = Query(...)):
    try:
        playlist_data = ytmusic.get_playlist(playlistId)
        return playlist_data
    except Exception as e:
        print(f"❌ Erro ao obter playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/health")
async def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
