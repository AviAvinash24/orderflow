from fastapi import FastAPI
app = FastAPI(title = "Orderflow")
@app.get("/health")
def health_check():
    return {"status":"Ok"}