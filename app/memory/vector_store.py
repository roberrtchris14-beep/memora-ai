import uuid
import chromadb
from app.core.config import CHROMA_DB_PATH
from app.memory.embedding import get_embedding

class VectorStore:
    def __init__(self):
        # Initialize the persistent client using the configured path
        self.client = chromadb.PersistentClient(path=CHROMA_DB_PATH)
        # Create or get the 'memora_collection'
        self.collection = self.client.get_or_create_collection(name="memora_collection")

    def add_memory(self, text: str, metadata: dict = None) -> str:
        """
        Generates an embedding for the given text and stores it in ChromaDB along with metadata.
        Returns the unique ID of the stored memory.
        """
        if metadata is None:
            metadata = {}
            
        # Ensure metadata contains only valid types (str, int, float, bool)
        # ChromaDB requires metadata dict values to be simple primitive types
        cleaned_metadata = {}
        for k, v in metadata.items():
            if isinstance(v, (str, int, float, bool)):
                cleaned_metadata[k] = v
            else:
                cleaned_metadata[k] = str(v)

        # Generate the embedding vector
        embedding = get_embedding(text)
        
        # Generate a unique identifier
        memory_id = str(uuid.uuid4())
        
        # Store in ChromaDB collection
        self.collection.add(
            ids=[memory_id],
            embeddings=[embedding],
            metadatas=[cleaned_metadata],
            documents=[text]
        )
        return memory_id

    def search_memory(self, query: str, top_k: int = 3) -> list:
        """
        Generates the query embedding, performs a similarity search in ChromaDB,
        and returns the top_k results.
        """
        # Generate embedding for the search query
        query_embedding = get_embedding(query)
        
        # Query ChromaDB
        results = self.collection.query(
            query_embeddings=[query_embedding],
            n_results=top_k
        )
        
        # Format search results
        formatted_results = []
        if results and "ids" in results and results["ids"]:
            ids = results["ids"][0]
            documents = results.get("documents", [[]])[0] if results.get("documents") else []
            metadatas = results.get("metadatas", [[]])[0] if results.get("metadatas") else []
            distances = results.get("distances", [[]])[0] if results.get("distances") else []
            
            for i in range(len(ids)):
                formatted_results.append({
                    "id": ids[i],
                    "text": documents[i] if i < len(documents) else "",
                    "metadata": metadatas[i] if (metadatas and i < len(metadatas)) else {},
                    "distance": distances[i] if (distances and i < len(distances)) else 0.0
                })
                
        return formatted_results
