import os
import asyncio
from google import genai
from google.genai import types
from scripts.main import db
from datetime import datetime
import json

class MemoryManager:
    def __init__(self):
        self.client = genai.Client(api_key=os.getenv("googlekey"))
        self.model_name = "text-embedding-004"
        self.embedding_dim = 768

    async def get_embedding(self, text: str):
        """Generates embedding for the given text using Gemini."""
        result = await self.client.aio.models.embed_content(
            model=self.model_name,
            contents=text
        )
        return result.embeddings[0].values

    async def add_memory(self, user_id: int, role: str, content: str):
        """Adds a message to sequential history and generates a long-term memory."""
        # 1. Save to sequential history
        await db.message.create(data={
            'userId': user_id,
            'role': role,
            'content': content
        })

        # 2. Save to long-term memory (semantic)
        # We only embed the content itself for search
        embedding = await self.get_embedding(content)
        
        # We use raw SQL to insert the vector since Prisma's Unsupported type requires it
        # vector(...) format is [v1, v2, ...]
        vector_str = "[" + ",".join(map(str, embedding)) + "]"
        
        await db.execute_raw(
            'INSERT INTO "Memory" ("userId", "content", "embedding", "createdAt") VALUES ($1, $2, $3::vector, $4)',
            user_id, content, vector_str, datetime.now()
        )

        # 3. Cleanup: Limit sequential history to last 50 messages per user to keep it fast
        # (This is a simple cleanup, could be more sophisticated)
        # But for now, let's just let it grow a bit or implement it later if needed.
        pass

    async def get_context(self, user_id: int, current_query: str, history_limit: int = 10, memory_limit: int = 5):
        """Retrieves short-term history and semantically relevant long-term memories."""
        
        # 1. Get short-term history (last N messages)
        history = await db.message.find_many(
            where={'userId': user_id},
            order={'createdAt': 'desc'},
            take=history_limit
        )
        history.reverse() # Order chronologically

        # 2. Get long-term memories (semantic search)
        query_embedding = await self.get_embedding(current_query)
        vector_str = "[" + ",".join(map(str, query_embedding)) + "]"
        
        # Search using cosine similarity (<=> is cosine distance in pgvector)
        # We want the smallest distance (highest similarity)
        memories = await db.query_raw(
            'SELECT "content", "createdAt" FROM "Memory" WHERE "userId" = $1 ORDER BY "embedding" <=> $2::vector LIMIT $3',
            user_id, vector_str, memory_limit
        )

        # 3. Format context
        formatted_history = []
        for msg in history:
            role_name = "User" if msg.role == "user" else "RVDiA"
            formatted_history.append(f"{role_name}: {msg.content}")

        formatted_memories = []
        for mem in memories:
            formatted_memories.append(f"- {mem['content']}")

        return {
            'history': "\n".join(formatted_history),
            'memories': "\n".join(formatted_memories) if formatted_memories else "None yet."
        }

# Global instance
memory_manager = MemoryManager()
