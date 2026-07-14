"""
YouTube Music Proxy API
------------------------
Este servidor atua EXCLUSIVAMENTE como um roteador de metadados.
Ele NUNCA baixa, processa ou faz proxy de bytes de áudio: o único
trabalho dele é (1) consultar o YouTube Music via `ytmusicapi` e
devolver JSON já normalizado para o app Flutter, e (2) no endpoint
`/get_song_url`, extrair o link direto de streaming (googlevideo.com)
e devolver SOMENTE essa URL — o app baixa o áudio direto do Google.
"""

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from ytmusicapi import YTMusic
from typing import Optional
import uvicorn
import os
import time
import traceback

app = FastAPI(
    title="YouTube Music Proxy API",
    description="Proxy de metadados para o app Flutter. Nunca processa áudio.",
    version="2.0.0",
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

ytmusic = YTMusic()

EMPTY_STREAM_RESULT = {
    "playable": False,
    "statusMSG": "unknown_error",
    "lowQualityAudio": None,
    "highQualityAudio": None,
}

# ============================================================
#  CACHE EM MEMÓRIA (TTL curto) PARA URLS DE STREAMING
# ============================================================
# As URLs do googlevideo.com costumam expirar em poucas horas.
# Usamos um TTL conservador de 5h para não servir link expirado,
# e para reduzir chamadas repetidas ao YouTube (economiza tempo
# de resposta e reduz o risco de rate limit).
_STREAM_CACHE: dict[str, dict] = {}
_STREAM_TTL_SECONDS = 5 * 60 * 60  # 5 horas


def _cache_get(video_id: str) -> Optional[dict]:
    entry = _STREAM_CACHE.get(video_id)
    if entry is None:
        return None
    if entry["expires_at"] <= time.time():
        _STREAM_CACHE.pop(video_id, None)
        return None
    return entry["data"]


def _cache_set(video_id: str, data: dict) -> None:
    _STREAM_CACHE[video_id] = {
        "data": data,
        "expires_at": time.time() + _STREAM_TTL_SECONDS,
    }


# ============================================================
#  HELPERS DE NORMALIZAÇÃO
# ============================================================
def _safe_thumbnails(thumbnails) -> list:
    """Garante que sempre haja pelo menos 1 thumbnail (o app quebra em
    thumbnails[0] se a lista vier vazia)."""
    if thumbnails:
        return thumbnails
    return [{"url": "", "width": 0, "height": 0}]


def _audio_json_from_format(fmt: dict) -> dict:
    """Converte um item de `streamingData.adaptiveFormats` (formato cru
    do youtubei/v1/player) para o shape que o Dart `Audio.fromJson`
    espera (ver lib/services/stream_service.dart e hm_streaming_data.dart)."""
    mime = fmt.get("mimeType", "")
    return {
        "itag": fmt.get("itag", 0),
        "audioCodec": "mp4a" if "mp4a" in mime else "opus",
        "bitrate": fmt.get("bitrate", 0),
        "loudnessDb": fmt.get("loudnessDb", 0.0) or 0.0,
        "url": fmt.get("url", ""),
        "approxDurationMs": int(fmt.get("approxDurationMs") or 0),
        "size": int(fmt.get("contentLength") or 0),
    }


def _pick_best_format(adaptive_formats: list, itag_priority: list[int]) -> Optional[dict]:
    """Só aceita formatos que já vêm com `url` direta (sem `signatureCipher`).
    Decifrar o `signatureCipher` exige rodar o JS do player do YouTube, o
    que este servidor propositalmente NÃO faz (mantém o proxy leve). Quando
    só existe `signatureCipher`, devolvemos None e o app cai no fallback
    local (youtube_explode_dart, que sabe decifrar)."""
    audio_only = [
        f for f in adaptive_formats
        if str(f.get("mimeType", "")).startswith("audio/") and f.get("url")
    ]
    for itag in itag_priority:
        for f in audio_only:
            if f.get("itag") == itag:
                return f
    return audio_only[0] if audio_only else None


# ============================================================
#  ROTAS
# ============================================================
@app.get("/")
async def root():
    return {"message": "YouTube Music Proxy API está rodando!"}


@app.get("/health")
async def health_check():
    return {"status": "ok"}


@app.get("/search")
async def search(
    q: str = Query(..., min_length=1, description="Termo de busca"),
    limit: Optional[int] = Query(20, ge=1, le=50),
    filter: Optional[str] = Query(
        None,
        description="songs|videos|albums|artists|playlists|community_playlists|featured_playlists",
    ),
    ignore_spelling: bool = Query(False),
):
    try:
        results = ytmusic.search(
            q, filter=filter, limit=limit, ignore_spelling=ignore_spelling
        )
        for item in results:
            if "thumbnails" in item:
                item["thumbnails"] = _safe_thumbnails(item["thumbnails"])
        return {"query": q, "results": results}
    except Exception as e:
        print(f"❌ Erro na busca: {e}")
        traceback.print_exc()
        return {"query": q, "results": []}


@app.get("/get_search_suggestions")
async def get_search_suggestions(q: str = Query(..., min_length=1)):
    try:
        return {"suggestions": ytmusic.get_search_suggestions(q)}
    except Exception as e:
        print(f"❌ Erro nas sugestões: {e}")
        return {"suggestions": []}


@app.get("/get_home")
async def get_home(limit: int = Query(4, ge=1, le=20)):
    try:
        sections = ytmusic.get_home(limit=limit)
        for section in sections:
            for item in section.get("contents", []):
                if "thumbnails" in item:
                    item["thumbnails"] = _safe_thumbnails(item["thumbnails"])
        return {"sections": sections}
    except Exception as e:
        print(f"❌ Erro no get_home: {e}")
        traceback.print_exc()
        return {"sections": []}


@app.get("/get_watch_playlist")
async def get_watch_playlist(
    videoId: Optional[str] = Query(None),
    playlistId: Optional[str] = Query(None),
    limit: int = Query(25, ge=1, le=100),
    radio: bool = Query(False),
    shuffle: bool = Query(False),
):
    try:
        data = ytmusic.get_watch_playlist(
            videoId=videoId or None,
            playlistId=playlistId or None,
            limit=limit,
            radio=radio,
            shuffle=shuffle,
        )
        for track in data.get("tracks", []):
            if "thumbnail" in track and "thumbnails" not in track:
                track["thumbnails"] = track["thumbnail"]
            track["thumbnails"] = _safe_thumbnails(track.get("thumbnails"))
        return data
    except Exception as e:
        print(f"❌ Erro no get_watch_playlist: {e}")
        traceback.print_exc()
        return {"tracks": [], "playlistId": playlistId, "lyrics": None, "related": None}


@app.get("/get_song")
async def get_song(videoId: str = Query(...)):
    try:
        return ytmusic.get_song(videoId)
    except Exception as e:
        print(f"❌ Erro ao obter música: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_album")
async def get_album(browseId: str = Query(...)):
    try:
        data = ytmusic.get_album(browseId)
        data["thumbnails"] = _safe_thumbnails(data.get("thumbnails"))
        return data
    except Exception as e:
        print(f"❌ Erro ao obter álbum: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_playlist")
async def get_playlist(playlistId: str = Query(...), limit: int = Query(100, ge=1, le=500)):
    try:
        data = ytmusic.get_playlist(playlistId, limit=limit)
        data["thumbnails"] = _safe_thumbnails(data.get("thumbnails"))
        return data
    except Exception as e:
        print(f"❌ Erro ao obter playlist: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_artist")
async def get_artist(browseId: str = Query(...)):
    try:
        data = ytmusic.get_artist(browseId)
        data["thumbnails"] = _safe_thumbnails(data.get("thumbnails"))
        return data
    except Exception as e:
        print(f"❌ Erro ao obter artista: {e}")
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/get_lyrics")
async def get_lyrics(browseId: str = Query(...)):
    try:
        return ytmusic.get_lyrics(browseId)
    except Exception as e:
        print(f"❌ Erro ao obter letras: {e}")
        return {"lyrics": None, "source": None}


# ------------------------------------------------------------------
# ÚNICO endpoint relacionado a streaming. Devolve SOMENTE a URL
# direta do googlevideo.com (+ metadados leves de itag/bitrate).
# O áudio em si NUNCA passa por este servidor.
# ------------------------------------------------------------------
@app.get("/get_song_url")
async def get_song_url(videoId: str = Query(...)):
    cached = _cache_get(videoId)
    if cached is not None:
        return cached

    try:
        song_data = ytmusic.get_song(videoId)
        playability = song_data.get("playabilityStatus", {})
        status = playability.get("status", "UNKNOWN")

        if status != "OK":
            # Não cacheamos falhas: o app deve tentar de novo ou usar o
            # fallback local (youtube_explode_dart) imediatamente.
            return {
                "playable": False,
                "statusMSG": playability.get("reason", status),
                "lowQualityAudio": None,
                "highQualityAudio": None,
            }

        adaptive_formats = song_data.get("streamingData", {}).get("adaptiveFormats", [])
        high = _pick_best_format(adaptive_formats, itag_priority=[251, 140])
        low = _pick_best_format(adaptive_formats, itag_priority=[249, 139]) or high

        if high is None:
            # Só existem formatos com signatureCipher (assinatura cifrada).
            # Decifrar exigiria rodar o JS do player -> fora do escopo
            # deste proxy leve. O app deve cair no fallback local.
            return {
                "playable": False,
                "statusMSG": "cipher_required_use_fallback",
                "lowQualityAudio": None,
                "highQualityAudio": None,
            }

        result = {
            "playable": True,
            "statusMSG": "OK",
            "lowQualityAudio": _audio_json_from_format(low),
            "highQualityAudio": _audio_json_from_format(high),
        }
        _cache_set(videoId, result)
        return result

    except Exception as e:
        print(f"❌ Erro no get_song_url: {e}")
        traceback.print_exc()
        return {
            "playable": False,
            "statusMSG": "server_error",
            "lowQualityAudio": None,
            "highQualityAudio": None,
        }


if __name__ == "__main__":
    port = int(os.getenv("PORT", 8000))
    uvicorn.run(app, host="0.0.0.0", port=port)
