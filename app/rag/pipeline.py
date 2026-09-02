import os
import google.generativeai as genai
from app.core.config import GEMINI_API_KEY

# Ensure gemini API is configured
genai.configure(api_key=GEMINI_API_KEY)

class RAGPipeline:
    def __init__(self, vector_store, model_name="models/gemini-2.5-flash"):
        self.vector_store = vector_store
        self.model_name = model_name

    def generate_response(self, user_query: str, session_id: str = "default") -> str:
        # 1. Retrieve memories
        memories = self.vector_store.search_memory(user_query, top_k=3)
        context_items = [m.get("text", "") for m in memories if m.get("text")]
        context_str = "\n".join([f"- {item}" for item in context_items]) if context_items else "No relevant memories found."

        # 2. Build system prompt & prompt structure
        system_prompt = "You are Memora, an AI assistant with persistent memory. Use the following retrieved memories as context to answer the user. If memories are not relevant, ignore them. Be concise."
        
        full_prompt = (
            f"{system_prompt}\n\n"
            f"Context:\n{context_str}\n\n"
            f"Question:\n{user_query}\n"
        )

        # 3 & 4. Generate content with fallbacks for robust model support
        models_to_try = [self.model_name, "models/gemini-2.5-flash", "models/gemini-3.5-flash", "models/gemini-pro-latest"]
        response_text = ""
        last_err = None

        for m_name in models_to_try:
            try:
                model = genai.GenerativeModel(m_name)
                response = model.generate_content(full_prompt)
                if response and hasattr(response, "text"):
                    response_text = response.text
                    break
            except Exception as e:
                last_err = e
                continue

        if not response_text:
            raise RuntimeError(f"Failed to generate response using models {models_to_try}. Last error: {last_err}")

        # 5. Add agent's response to memory
        try:
            self.vector_store.add_memory(
                text=f"User asked: {user_query}, Agent replied: {response_text}",
                metadata={"session_id": session_id, "type": "conversation"}
            )
        except Exception as e:
            print(f"Warning: Failed to save interaction to memory: {e}")

        return response_text
