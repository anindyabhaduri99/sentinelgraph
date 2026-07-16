"""
rag_search.py
=============
Real semantic search against the documents already ingested into Chroma.
Reuses the same GatewayEmbedding class as ingestion - critical, since
query and document embeddings must come from the same model to be
comparable.
"""

import chromadb
from llama_index.core import VectorStoreIndex, StorageContext
from llama_index.vector_stores.chroma import ChromaVectorStore
from rag_ingest import GatewayEmbedding

chroma_client = chromadb.HttpClient(host="chroma", port=8000)
chroma_collection = chroma_client.get_or_create_collection("documents")
vector_store = ChromaVectorStore(chroma_collection=chroma_collection)

embed_model = GatewayEmbedding()

# Load the EXISTING index (already-embedded chunks) rather than
# re-ingesting - this just connects to what rag_ingest.py already built.
index = VectorStoreIndex.from_vector_store(vector_store, embed_model=embed_model)

# top_k=3 means: return the 3 most semantically similar chunks.
query_engine = index.as_retriever(similarity_top_k=3)


def search_documents(query: str, role: str) -> dict:
    """
    Real semantic search. No entitlement check needed here for now since
    these are general compliance/FAQ docs, not client-specific data - a
    real system might add resource-level entitlements per document
    category, same DAL pattern as everything else.
    """
    results = query_engine.retrieve(query)
    combined = "\n---\n".join([r.text for r in results])
    return {"query": query, "retrieved_chunks": combined}