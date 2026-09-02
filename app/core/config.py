import os
from dotenv import load_dotenv

# Load python-dotenv
load_dotenv()

# Read GEMINI_API_KEY from the environment
GEMINI_API_KEY = os.getenv("GEMINI_API_KEY")

# If the key is not found, raise an error
if not GEMINI_API_KEY:
    raise ValueError("GEMINI_API_KEY environment variable is not set. Please set it in your environment or .env file.")

# Set ChromaDB's persistent directory path
CHROMA_DB_PATH = os.getenv("CHROMA_DB_PATH", "./chroma_db")
