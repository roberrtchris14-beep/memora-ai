import google.generativeai as genai
from app.core.config import GEMINI_API_KEY

# Initialize Gemini API
genai.configure(api_key=GEMINI_API_KEY)

def get_embedding(text: str) -> list[float]:
    """
    Generates an embedding vector for the given text using Gemini's embedding model.
    """
    if not text or not isinstance(text, str):
        raise ValueError("Text must be a non-empty string.")
    
    # Try models/gemini-embedding-001 first, then fallback to others if needed
    models_to_try = ["models/gemini-embedding-001", "models/gemini-embedding-2", "models/gemini-embedding-2-preview"]
    last_error = None
    
    for model_name in models_to_try:
        try:
            response = genai.embed_content(
                model=model_name,
                content=text,
                task_type="retrieval_document"
            )
            
            # Handle the response dictionary or object
            if isinstance(response, dict) and "embedding" in response:
                return response["embedding"]
            elif hasattr(response, "embedding"):
                # Frequently is list[float] or an object with 'values'
                emb = response.embedding
                if hasattr(emb, "values"):
                    return list(emb.values)
                return list(emb)
            elif hasattr(response, "get"):
                return response.get("embedding", [])
        except Exception as e:
            last_error = e
            continue
            
    raise RuntimeError(f"Failed to generate embedding after trying {models_to_try}. Last error: {last_error}")
