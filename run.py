"""Entry point — run with: python run.py"""
import os

# Use cached model without contacting HuggingFace
os.environ.setdefault("HF_HUB_OFFLINE", "1")
os.environ.setdefault("TRANSFORMERS_OFFLINE", "1")
# Skip TensorFlow — embeddings run on PyTorch; avoids slow startup and log noise
os.environ.setdefault("USE_TF", "0")

import uvicorn

if __name__ == "__main__":
    uvicorn.run("backend.main:app", host="0.0.0.0", port=8000, reload=True)
