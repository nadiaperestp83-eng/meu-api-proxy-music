from fastapi import FastAPI
from ytmusicapi import YTMusic

app = FastAPI()
ytmusic = YTMusic()

@app.get("/search")
def search(q: str):
    return ytmusic.search(q)

@app.get("/get_song")
def get_song(videoId: str):
    # Isso retorna as informações e o link de reprodução
    return ytmusic.get_song(videoId)
