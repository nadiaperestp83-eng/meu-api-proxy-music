from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from ytmusicapi import YTMusic
from typing import Optional, Dict, Any
import uvicorn
import os

app = FastAPI(
    title="YouTube Music Proxy API",
    description="Proxy para o app Flutter consumir dados do YouTube Music.",
    version="1.0.0"
)

# Configuração do CORS para permitir requisições do app Flutter
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Em produção, restrinja ao domínio do app
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Inicializa o cliente YTMusic
# Opcional: você pode passar um arquivo de autenticação se precisar de acesso a playlists privadas
# Ex: ytmusic = YTMusic("oauth.json")
ytmusic = YTMusic()

@app.get("/")
async def root():
    return {"message": "YouTube Music Proxy API está rodando!"}

@app.get("/search")
async def search(
    q: str = Query(..., min_length=1, description="Termo de busca"),
    limit: Optional[int] = Query(20, ge=1, le=50, description="Número máximo de resultados")
):
    """
    Endpoint para buscar músicas, vídeos, álbuns, artistas e playlists.
    """
    try:
        # ytmusic.search retorna uma lista de resultados
        results = ytmusic.search(q, limit=limit)
        # Filtra para retornar apenas os campos mais relevantes (opcional)
        # Se quiser os dados brutos, retorne results diretamente
        return {"query": q, "results": results}
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na busca: {str(e)}")

@app.get("/get_song")
async def get_song(videoId: str = Query(..., description="ID do vídeo/música")):
    """
    Obtém informações detalhadas de uma música específica.
    """
    try:
        song_data = ytmusic.get_song(videoId)
        return song_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao obter música: {str(e)}")

@app.get("/get_album")
async def get_album(browseId: str = Query(..., description="ID do álbum (browseId)")):
    """
    Obtém informações detalhadas de um álbum, incluindo a lista de faixas.
    """
    try:
        album_data = ytmusic.get_album(browseId)
        return album_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao obter álbum: {str(e)}")

@app.get("/get_playlist")
async def get_playlist(playlistId: str = Query(..., description="ID da playlist")):
    """
    Obtém informações detalhadas de uma playlist, incluindo todas as faixas.
    """
    try:
        playlist_data = ytmusic.get_playlist(playlistId)
        return playlist_data
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao obter playlist: {str(e)}")

# Endpoint de health check para o Railway
@app.get("/health")
async def health_check():
    return {"status": "ok"}

if __name__ == "__main__":
    # Railway define a porta na variável de ambiente PORT
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
