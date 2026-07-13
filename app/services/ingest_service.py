import asyncio
import csv
import ipaddress
import json
import urllib.parse
import uuid
from datetime import datetime
from io import BytesIO
from pathlib import Path

import httpx
from bs4 import BeautifulSoup
from docx import Document
from fastapi import UploadFile
from pypdf import PdfReader

from app.core.observability import logger
from app.services.corpus_index import CorpusIndex, KeywordIndex

DATA_DIR = Path(__file__).resolve().parent.parent.parent / "data"
UPLOADS_DIR = DATA_DIR / "uploads"
MANIFEST_PATH = UPLOADS_DIR / "manifest.jsonl"
SEED_CORPUS_PATH = DATA_DIR / "seed" / "corpus.jsonl"

CHUNK_SIZE = 1500       # target characters per chunk (1000–5000 range)
CHUNK_OVERLAP = 200    # characters of overlap between consecutive chunks

MAX_URL_CHUNKS = 1500          # cap for HuggingFace dataset ingest via URL
MAX_URL_CHUNKS_PER_SOURCE = 200  # spread budget across source types
MAX_URL_SIZE = 50 * 1024 * 1024  # 50MB cap for regular URL downloads


def _chunk_text(text: str, doc_id: str, source: str, title: str) -> list[dict]:
    """Splits text into overlapping chunks, matching the seed corpus format.
    
    Chunk size is in the 1000-5000 character range for optimal RAG retrieval.
    """
    chunks = []
    words = text.split()
    current_chunk = []
    current_len = 0
    
    for word in words:
        current_chunk.append(word)
        current_len += len(word) + 1
        
        if current_len >= CHUNK_SIZE:
            chunks.append({
                "chunk_id": f"{doc_id}_{len(chunks):04d}",
                "text": " ".join(current_chunk),
                "source": source,
                "doc_id": doc_id,
                "title": title
            })
            # Keep overlapping words at the tail
            overlap_chars = 0
            overlap_words = []
            for w in reversed(current_chunk):
                overlap_chars += len(w) + 1
                overlap_words.insert(0, w)
                if overlap_chars >= CHUNK_OVERLAP:
                    break
            current_chunk = overlap_words
            current_len = sum(len(w) + 1 for w in current_chunk)
            
    # Append any remaining words as a final chunk
    if current_chunk:
        chunks.append({
            "chunk_id": f"{doc_id}_{len(chunks):04d}",
            "text": " ".join(current_chunk),
            "source": source,
            "doc_id": doc_id,
            "title": title
        })
        
    return chunks


class IngestService:
    def __init__(self, corpus_index=None, keyword_index=None, llm_client=None, graph_driver=None):
        self.corpus_index = corpus_index
        self.keyword_index = keyword_index
        self.llm_client = llm_client
        self.graph_driver = graph_driver
        UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
        if not MANIFEST_PATH.exists():
            MANIFEST_PATH.touch()

    async def _rebuild_index_from_corpus(self) -> None:
        """Rebuild CorpusIndex + KeywordIndex from corpus.jsonl and hot-swap
        into global state and all live service references."""
        try:
            if not SEED_CORPUS_PATH.exists():
                return
            chunks = [
                json.loads(line)
                for line in SEED_CORPUS_PATH.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
            if not chunks:
                return

            logger.info("Rebuilding corpus index from %d chunks...", len(chunks))
            new_corpus = await asyncio.to_thread(CorpusIndex.build, chunks)
            await asyncio.to_thread(new_corpus.save)

            new_keyword = await asyncio.to_thread(KeywordIndex.build, chunks)
            await asyncio.to_thread(new_keyword.save)

            # Hot-swap into self and global state
            self.corpus_index = new_corpus
            self.keyword_index = new_keyword

            from app.core.state import state
            state.corpus_index = new_corpus
            state.keyword_index = new_keyword
            logger.info("Corpus index hot-swapped with %d vectors.", len(chunks))

        except Exception as e:
            logger.warning("Failed to rebuild corpus index: %s", e)

    def _read_manifest(self) -> list[dict]:
        if not MANIFEST_PATH.exists():
            return []
        docs = []
        for line in MANIFEST_PATH.read_text(encoding="utf-8").splitlines():
            if line.strip():
                docs.append(json.loads(line))
        return docs

    def _write_manifest(self, docs: list[dict]) -> None:
        MANIFEST_PATH.write_text(
            "\n".join(json.dumps(d) for d in docs), encoding="utf-8"
        )

    async def ingest_file(self, file: UploadFile, doc_id: str = None) -> dict:
        content = await file.read()
        filename = file.filename
        ext = filename.split(".")[-1].lower() if "." in filename else ""
        
        doc_id = doc_id or str(uuid.uuid4())
        text = ""

        try:
            if ext == "pdf":
                reader = PdfReader(BytesIO(content))
                text = "\n".join(page.extract_text() for page in reader.pages if page.extract_text())
            elif ext in ("doc", "docx"):
                doc = Document(BytesIO(content))
                text = "\n".join(p.text for p in doc.paragraphs)
            elif ext == "csv":
                decoded = content.decode("utf-8", errors="replace")
                reader = csv.reader(decoded.splitlines())
                text = "\n".join(", ".join(row) for row in reader)
            else:
                text = content.decode("utf-8", errors="replace")
                
            chunks = _chunk_text(text, doc_id=doc_id, source=filename, title=filename)
            
            # Save chunks visibly to the data folder
            chunks_path = UPLOADS_DIR / f"{doc_id}_chunks.json"
            chunks_path.write_text(json.dumps(chunks, indent=2), encoding="utf-8")
            
            # Append chunks to seed corpus
            with open(SEED_CORPUS_PATH, "a", encoding="utf-8") as f:
                for chunk in chunks:
                    f.write(json.dumps(chunk) + "\n")
            
            # Update indexes (in-memory hot-add for immediate effect)
            if self.corpus_index:
                await asyncio.to_thread(self.corpus_index.add_chunks, chunks)
                await asyncio.to_thread(self.corpus_index.save)
            else:
                # No index loaded yet — build from full corpus
                await self._rebuild_index_from_corpus()
                
            if self.keyword_index:
                await asyncio.to_thread(self.keyword_index.rebuild)
                await asyncio.to_thread(self.keyword_index.save)

            # Extract graph entities if LLM and Graph are available
            if self.llm_client and self.graph_driver:
                try:
                    graph_data = await self.llm_client.extract_graph_entities(text)
                    await self._write_to_neo4j(graph_data)
                except Exception as e:
                    logger.warning(f"Graph extraction failed for {filename}: {e}")

            # Update manifest
            docs = self._read_manifest()
            doc_record = {
                "doc_id": doc_id,
                "name": filename,
                "size": len(content),
                "status": "indexed",
                "chunk_count": len(chunks),
                "uploaded_at": datetime.utcnow().isoformat()
            }
            docs = [d for d in docs if d["doc_id"] != doc_id]
            docs.append(doc_record)
            self._write_manifest(docs)
            
            return doc_record

        except Exception as e:
            logger.exception("Failed to ingest file %s", filename)
            raise e

    async def ingest_url(self, url: str) -> dict:
        """Securely fetches content from a URL and ingests it.
        
        HuggingFace dataset URLs are processed as background jobs (returns
        immediately with a job_id; poll GET /ingest/jobs/{job_id}).
        Regular URLs are processed synchronously with streaming up to 50MB.
        """
        parsed_url = urllib.parse.urlparse(url)
        
        if parsed_url.scheme not in ("http", "https"):
            raise ValueError("Only HTTP and HTTPS URLs are allowed.")
            
        if not url.startswith("https://huggingface.co/datasets/"):
            raise ValueError("Only Hugging Face dataset URLs (https://huggingface.co/datasets/...) are allowed.")
            
        try:
            ip = ipaddress.ip_address(parsed_url.hostname)
            if ip.is_private or ip.is_loopback:
                raise ValueError("Local and private network URLs are strictly prohibited for security reasons.")
        except ValueError:
            pass

        if url.startswith("https://huggingface.co/datasets/"):
            job_id = str(uuid.uuid4())
            from app.core.state import state
            state.job_registry[job_id] = {
                "job_id": job_id,
                "status": "processing",
                "url": url,
                "chunk_count": 0,
                "error": None,
                "created_at": datetime.utcnow().isoformat(),
            }
            asyncio.create_task(self._process_hf_dataset_background(job_id, url))
            return {"job_id": job_id, "status": "processing", "message": "Dataset ingestion started. Poll GET /ingest/jobs/" + job_id + " for progress."}
        
        return await self._process_regular_url(url, parsed_url)

    async def _process_hf_dataset_background(self, job_id: str, url: str) -> None:
        """Background worker: stream-download parquet via httpx, read in batches, chunk, rebuild index."""
        import tempfile
        import pyarrow.parquet as pq
        from app.core.state import state

        try:
            dataset_name = url.replace("https://huggingface.co/datasets/", "")
            config_name = 'documents' if 'EnterpriseRAG-Bench' in dataset_name else None

            parquet_url = (
                f"https://huggingface.co/datasets/{dataset_name}/resolve/main/"
                f"data/{config_name or 'default'}/test.parquet"
            )

            state.job_registry[job_id]["chunk_count"] = 0
            state.job_registry[job_id]["status"] = "downloading"

            tmp = tempfile.NamedTemporaryFile(suffix=".parquet", delete=False)
            async with httpx.AsyncClient(timeout=120.0, follow_redirects=True) as client:
                async with client.stream("GET", parquet_url) as resp:
                    resp.raise_for_status()
                    async for chunk in resp.aiter_bytes(chunk_size=65536):
                        tmp.write(chunk)
            tmp.close()

            state.job_registry[job_id]["status"] = "processing"

            all_chunks: list[dict] = []
            per_source_count: dict[str, int] = {}
            MAX = MAX_URL_CHUNKS
            PER_SRC = MAX_URL_CHUNKS_PER_SOURCE

            pf = pq.ParquetFile(tmp.name)
            for batch in pf.iter_batches(batch_size=200):
                if len(all_chunks) >= MAX:
                    break
                table = batch.to_pydict()
                nrows = len(table[list(table.keys())[0]])

                for i in range(nrows):
                    if len(all_chunks) >= MAX:
                        break
                    row = {k: table[k][i] for k in table}
                    src = row.get("source_type") or url
                    if per_source_count.get(src, 0) >= PER_SRC:
                        continue

                    text_content = row.get('text') or row.get('content') or json.dumps(row, default=str)
                    title = row.get('title') or f"row_{i}"
                    doc_id_row = str(row.get('doc_id') or uuid.uuid4())

                    row_chunks = _chunk_text(str(text_content), doc_id=doc_id_row, source=src, title=str(title))
                    for rc in row_chunks:
                        if len(all_chunks) >= MAX or per_source_count.get(src, 0) >= PER_SRC:
                            break
                        all_chunks.append(rc)
                        per_source_count[src] = per_source_count.get(src, 0) + 1

                state.job_registry[job_id]["chunk_count"] = len(all_chunks)
                logger.info("HF ingest progress: %d chunks...", len(all_chunks))

            pf = None
            import os; os.unlink(tmp.name)

            state.job_registry[job_id]["chunk_count"] = len(all_chunks)

            if not all_chunks:
                state.job_registry[job_id]["status"] = "completed"
                return

            doc_id = str(uuid.uuid4())
            filename = f"hf_dataset_{dataset_name.replace('/', '_')}"

            with open(SEED_CORPUS_PATH, "a", encoding="utf-8") as f:
                for chunk in all_chunks:
                    f.write(json.dumps(chunk) + "\n")

            chunks_path = UPLOADS_DIR / f"{doc_id}_chunks.json"
            chunks_path.write_text(json.dumps(all_chunks, indent=2), encoding="utf-8")

            if self.corpus_index:
                await asyncio.to_thread(self.corpus_index.add_chunks, all_chunks)
                await asyncio.to_thread(self.corpus_index.save)
            else:
                await self._rebuild_index_from_corpus()

            if self.keyword_index:
                await asyncio.to_thread(self.keyword_index.rebuild)
                await asyncio.to_thread(self.keyword_index.save)

            docs = self._read_manifest()
            docs.append({
                "doc_id": doc_id,
                "name": filename,
                "size": 0,
                "status": "indexed",
                "chunk_count": len(all_chunks),
                "uploaded_at": datetime.utcnow().isoformat(),
            })
            self._write_manifest(docs)

            state.job_registry[job_id]["status"] = "completed"
            logger.info("Background HF ingest completed: %d chunks from %s", len(all_chunks), url)

        except Exception as e:
            logger.exception("Background HF ingest failed for %s", url)
            state.job_registry[job_id]["status"] = "failed"
            state.job_registry[job_id]["error"] = str(e)

    async def _process_regular_url(self, url: str, parsed_url) -> dict:
        """Synchronous streaming download for non-HuggingFace URLs (up to 50MB)."""
        try:
            async with httpx.AsyncClient(timeout=60.0, follow_redirects=True) as client:
                async with client.stream("GET", url) as response:
                    response.raise_for_status()
                    
                    content_length = response.headers.get("Content-Length")
                    if content_length and int(content_length) > MAX_URL_SIZE:
                        raise ValueError(f"File exceeds maximum allowed size ({MAX_URL_SIZE // (1024*1024)}MB).")
                        
                    content_bytes = bytearray()
                    async for chunk in response.aiter_bytes():
                        content_bytes.extend(chunk)
                        if len(content_bytes) > MAX_URL_SIZE:
                            raise ValueError(f"File stream exceeded maximum allowed size ({MAX_URL_SIZE // (1024*1024)}MB).")
                            
            soup = BeautifulSoup(content_bytes.decode('utf-8', errors='replace'), "html.parser")
            text = soup.get_text(separator="\n", strip=True)
            
            if not text:
                raise ValueError("Could not extract readable text from the provided URL.")
                
            filename = f"url_{parsed_url.hostname}.txt"
            doc_id = str(uuid.uuid4())
            chunks = _chunk_text(text, doc_id=doc_id, source=url, title=filename)

            chunks_path = UPLOADS_DIR / f"{doc_id}_chunks.json"
            chunks_path.write_text(json.dumps(chunks, indent=2), encoding="utf-8")
            
            with open(SEED_CORPUS_PATH, "a", encoding="utf-8") as f:
                for chunk in chunks:
                    f.write(json.dumps(chunk) + "\n")
            
            if self.corpus_index:
                await asyncio.to_thread(self.corpus_index.add_chunks, chunks)
                await asyncio.to_thread(self.corpus_index.save)
            else:
                await self._rebuild_index_from_corpus()
                
            if self.keyword_index:
                await asyncio.to_thread(self.keyword_index.rebuild)
                await asyncio.to_thread(self.keyword_index.save)

            docs = self._read_manifest()
            doc_record = {
                "doc_id": doc_id,
                "name": filename,
                "size": len(content_bytes),
                "status": "indexed",
                "chunk_count": len(chunks),
                "uploaded_at": datetime.utcnow().isoformat(),
            }
            docs = [d for d in docs if d["doc_id"] != doc_id]
            docs.append(doc_record)
            self._write_manifest(docs)
            
            return doc_record

        except httpx.RequestError as e:
            logger.exception("HTTP Request failed for URL %s", url)
            raise ValueError(f"Failed to fetch URL: {e}")

    async def _write_to_neo4j(self, data: dict) -> None:
        """Writes the extracted JSON graph directly into Neo4j."""
        if not self.graph_driver:
            return

        # 1. Merge People
        for p in data.get("people", []):
            if "name" in p:
                await self.graph_driver.run(
                    "MERGE (n:Person {name: $name}) SET n.title = $title",
                    {"name": p["name"], "title": p.get("title", "")}
                )
                
        # 2. Merge Projects
        for p in data.get("projects", []):
            if "name" in p:
                await self.graph_driver.run(
                    "MERGE (n:Project {name: $name})",
                    {"name": p["name"]}
                )
                
        # 3. Create Reports To
        for r in data.get("reports_to", []):
            if "person" in r and "manager" in r:
                await self.graph_driver.run(
                    "MATCH (p:Person {name: $person}), (m:Person {name: $manager}) "
                    "MERGE (p)-[:REPORTS_TO]->(m)",
                    {"person": r["person"], "manager": r["manager"]}
                )
                
        # 4. Create Owns
        for o in data.get("owns", []):
            if "person" in o and "project" in o:
                await self.graph_driver.run(
                    "MATCH (p:Person {name: $person}), (proj:Project {name: $project}) "
                    "MERGE (p)-[:OWNS]->(proj)",
                    {"person": o["person"], "project": o["project"]}
                )
                
        # 5. Create Works On
        for w in data.get("works_on", []):
            if "person" in w and "project" in w:
                await self.graph_driver.run(
                    "MATCH (p:Person {name: $person}), (proj:Project {name: $project}) "
                    "MERGE (p)-[:WORKS_ON]->(proj)",
                    {"person": w["person"], "project": w["project"]}
                )
                
        # 6. Create Collaborates With
        for c in data.get("collaborates_with", []):
            if "person_a" in c and "person_b" in c:
                await self.graph_driver.run(
                    "MATCH (a:Person {name: $person_a}), (b:Person {name: $person_b}) "
                    "MERGE (a)-[:COLLABORATES_WITH]->(b)",
                    {"person_a": c["person_a"], "person_b": c["person_b"]}
                )

    async def delete_document(self, doc_id: str) -> bool:
        try:
            # Remove visible chunks file
            chunks_path = UPLOADS_DIR / f"{doc_id}_chunks.json"
            if chunks_path.exists():
                chunks_path.unlink()
                
            removed = 0
            if self.corpus_index:
                removed = await asyncio.to_thread(self.corpus_index.delete_chunks_by_doc_id, doc_id)
                await asyncio.to_thread(self.corpus_index.save)
                
            if self.keyword_index:
                await asyncio.to_thread(self.keyword_index.rebuild)
                await asyncio.to_thread(self.keyword_index.save)
                
            docs = self._read_manifest()
            docs = [d for d in docs if d["doc_id"] != doc_id]
            self._write_manifest(docs)
            
            return True
        except Exception:
            logger.exception("Failed to delete document %s", doc_id)
            return False

    async def get_documents(self) -> list[dict]:
        return self._read_manifest()
