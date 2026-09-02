import uuid
import chromadb
from typing import Optional
from app.plugins.base import Plugin, PluginType


class ChromaDBMemoryPlugin(Plugin):
    def get_name(self) -> str:
        return "chromadb_memory"

    def get_type(self) -> PluginType:
        return PluginType.MEMORY

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["add", "search"], "description": "Action to perform ('add' or 'search')"},
                "text": {"type": "string", "description": "Text content to store (for 'add')"},
                "query": {"type": "string", "description": "Query string (for 'search')"},
                "top_k": {"type": "integer", "description": "Number of results to return"},
                "metadata": {"type": "object", "description": "Optional metadata dictionary"},
                "id": {"type": "string", "description": "Optional ID for the memory"}
            },
            "required": ["action"]
        }

    def initialize(self, config: dict) -> None:
        self.config = config
        self.path = config.get("path")
        self.collection_name = config.get("collection_name")
        
        if not self.path:
            raise ValueError("Configuration path 'path' is required for ChromaDBMemoryPlugin.")
        if not self.collection_name:
            raise ValueError("Configuration collection_name 'collection_name' is required.")
            
        self.client = chromadb.PersistentClient(path=self.path)
        self.collection = self.client.get_or_create_collection(name=self.collection_name)

    def execute(self, input_data: dict) -> dict:
        try:
            action = input_data.get("action")
            if not action:
                raise ValueError("Action 'action' must be specified in input_data ('add' or 'search').")
                
            if action == "add":
                text = input_data.get("text")
                if not text:
                    raise ValueError("Text 'text' is required for action 'add'.")
                
                metadata = input_data.get("metadata", {})
                memory_id = input_data.get("id") or str(uuid.uuid4())
                
                self.collection.add(
                    documents=[text],
                    metadatas=[metadata],
                    ids=[memory_id]
                )
                return {"id": memory_id, "status": "success"}
                
            elif action == "search":
                query = input_data.get("query")
                if not query:
                    raise ValueError("Query 'query' is required for action 'search'.")
                
                top_k = int(input_data.get("top_k", 5))
                results_data = self.collection.query(
                    query_texts=[query],
                    n_results=top_k
                )
                
                formatted_results = []
                if results_data and "documents" in results_data and results_data["documents"]:
                    docs = results_data["documents"][0]
                    ids = results_data["ids"][0] if "ids" in results_data else []
                    metadatas = results_data["metadatas"][0] if "metadatas" in results_data else []
                    distances = results_data["distances"][0] if "distances" in results_data else []
                    
                    for idx, doc in enumerate(docs):
                        res_item = {
                            "document": doc,
                            "id": ids[idx] if idx < len(ids) else None,
                            "metadata": metadatas[idx] if idx < len(metadatas) else {},
                            "distance": distances[idx] if idx < len(distances) else None
                        }
                        formatted_results.append(res_item)
                        
                return {"results": formatted_results, "status": "success"}
            else:
                raise ValueError(f"Unknown action '{action}'. Supported actions are 'add' and 'search'.")
        except Exception as e:
            return {"response": str(e), "status": "error"}

    def validate_config(self, config: dict) -> bool:
        if not isinstance(config, dict):
            return False
        return bool(config.get("path"))


class InMemoryMemoryPlugin(Plugin):
    def get_name(self) -> str:
        return "inmemory_memory"

    def get_type(self) -> PluginType:
        return PluginType.MEMORY

    def get_schema(self) -> dict:
        return {
            "type": "object",
            "properties": {
                "action": {"type": "string", "enum": ["add", "search"], "description": "Action to perform ('add' or 'search')"},
                "text": {"type": "string", "description": "Text content to store (for 'add')"},
                "query": {"type": "string", "description": "Query string (for 'search')"},
                "top_k": {"type": "integer", "description": "Number of results to return"},
                "metadata": {"type": "object", "description": "Optional metadata dictionary"},
                "id": {"type": "string", "description": "Optional ID for the memory"}
            },
            "required": ["action"]
        }

    def initialize(self, config: dict) -> None:
        self.config = config
        self.memories = []

    def execute(self, input_data: dict) -> dict:
        try:
            action = input_data.get("action")
            if not action:
                raise ValueError("Action 'action' must be specified in input_data ('add' or 'search').")
                
            if action == "add":
                text = input_data.get("text")
                if not text:
                    raise ValueError("Text 'text' is required for action 'add'.")
                
                metadata = input_data.get("metadata", {})
                memory_id = input_data.get("id") or str(uuid.uuid4())
                
                memory_item = {
                    "id": memory_id,
                    "text": text,
                    "metadata": metadata
                }
                self.memories.append(memory_item)
                return {"id": memory_id, "status": "success"}
                
            elif action == "search":
                query = input_data.get("query")
                if not query:
                    raise ValueError("Query 'query' is required for action 'search'.")
                
                top_k = int(input_data.get("top_k", 5))
                
                matched_results = []
                for item in self.memories:
                    text_content = item["text"]
                    if query.lower() in text_content.lower():
                        matched_results.append({
                            "document": text_content,
                            "id": item["id"],
                            "metadata": item["metadata"],
                            "distance": 0.0
                        })
                        
                results = matched_results[:top_k]
                return {"results": results, "status": "success"}
            else:
                raise ValueError(f"Unknown action '{action}'. Supported actions are 'add' and 'search'.")
        except Exception as e:
            return {"response": str(e), "status": "error"}

    def validate_config(self, config: dict) -> bool:
        return True
