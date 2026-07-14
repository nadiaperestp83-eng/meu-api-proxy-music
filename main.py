from fastapi import FastAPI
from ytmusicapi import YTMusic

app = FastAPI()
ytmusic = YTMusic()

@app.get("/search")
def search(q: str):
    # O ytmusicapi já faz todo o trabalho sujo de parse
    results = ytmusic.search(q)
    return {"results": results}
