import json
from groq import AsyncGroq
from app.core.config import settings
from app.core.observability import logger

class LLMClient:
    def __init__(self):
        api_key = settings.llm_api_key or "dummy_key_replace_in_env"
        
        self.client = AsyncGroq(
            api_key=api_key
        )
        # Using Llama 3.3 70B Versatile on Groq for reliable reasoning and JSON output
        self.model = "llama-3.3-70b-versatile"

    async def complete(self, query: str, messages: list[dict], context: str) -> str:
        prompt = (
            "You are a knowledgeable internal assistant. Answer directly and concisely.\n"
            "Extract facts from the context chunks below. Each chunk is from a real company document "
            "(emails, meeting notes, tickets, playbooks).\n\n"
            "Rules:\n"
            "- Answer the question directly. No preamble like 'Based on the context...' or 'To determine...'\n"
            "- Synthesize across chunks. If multiple projects are mentioned, compare them.\n"
            "- If performance/status data is in the chunks, state it. If not explicitly stated, "
            "infer from context (e.g. 'on track', 'blocked', 'ahead of schedule', risk flags).\n"
            "- Be specific: name projects, people, dates, metrics.\n"
            "- Only refuse if the context is completely empty or unrelated.\n\n"
            f"CONTEXT:\n{context}"
        )
        
        # Build message list from history
        api_messages = [{"role": "system", "content": prompt}]
        for msg in messages:
            api_messages.append({
                "role": msg.get("role", "user"),
                "content": msg.get("content", "")
            })
            
        api_messages.append({"role": "user", "content": query})
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=api_messages,
                temperature=0.0
            )
            return response.choices[0].message.content or ""
        except Exception as e:
            logger.exception("LLM generation failed")
            return f"[LLM Error: {str(e)}]"

    async def extract_graph_entities(self, text: str) -> dict:
        """
        Extracts people, projects, and relationships from the text to populate Neo4j.
        Returns a dictionary matching the structure of graph_seed.json.
        """
        system_prompt = (
            "You are a data extraction pipeline. Your job is to extract organizational entities "
            "and relationships from the given text.\n\n"
            "Extract the following entities:\n"
            "- People (include their name and title if available)\n"
            "- Projects (include their name)\n\n"
            "Extract the following relationships:\n"
            "- reports_to (person reports to manager)\n"
            "- works_on (person works on project)\n"
            "- owns (person owns/leads/manages a project)\n"
            "- collaborates_with (person_a collaborates with person_b)\n\n"
            "Respond STRICTLY in JSON format with exactly the following schema. "
            "Do not include any markdown formatting, backticks, or extra text outside the JSON.\n\n"
            "{\n"
            '  "people": [{"name": "string", "title": "string"}],\n'
            '  "projects": [{"name": "string"}],\n'
            '  "reports_to": [{"person": "string", "manager": "string"}],\n'
            '  "owns": [{"person": "string", "project": "string"}],\n'
            '  "works_on": [{"person": "string", "project": "string"}],\n'
            '  "collaborates_with": [{"person_a": "string", "person_b": "string"}]\n'
            "}"
        )
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"TEXT TO EXTRACT FROM:\n{text[:10000]}"}
                ],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            
            content = response.choices[0].message.content or "{}"
            # Clean up if the LLM still wrapped it in markdown despite instructions
            if content.startswith("```json"):
                content = content[7:-3].strip()
            elif content.startswith("```"):
                content = content[3:-3].strip()
                
            return json.loads(content)
        except Exception as e:
            logger.exception("LLM graph extraction failed")
            return {
                "people": [], "projects": [],
                "reports_to": [], "owns": [], "works_on": [], "collaborates_with": []
            }

    async def generate_cypher(self, query: str) -> str | None:
        """
        Dynamically translates a natural language query into a Neo4j Cypher query based on the schema.
        """
        system_prompt = (
            "You are a Neo4j Cypher expert. Your job is to translate the user's natural language question "
            "into a valid Cypher query.\n\n"
            "The graph database has the following schema:\n"
            "Nodes:\n"
            "- (:Person {name: string, title: string})\n"
            "- (:Project {name: string})\n\n"
            "Relationships:\n"
            "- (Person)-[:REPORTS_TO]->(Person)\n"
            "- (Person)-[:WORKS_ON]->(Project)\n"
            "- (Person)-[:OWNS]->(Project)\n"
            "- (Person)-[:COLLABORATES_WITH]-(Person)\n\n"
            "RULES:\n"
            "1. ONLY use the node labels and relationship types defined above.\n"
            "2. Use `text`, `id`, `score`, and `source` as the returned aliases.\n"
            "3. The `text` alias should be a human-readable sentence explaining the match.\n"
            "4. The `score` alias should be exactly `1.0`.\n"
            "5. The `source` alias should be exactly `'graph:dynamic'`.\n"
            "6. Example return clause: `RETURN p.name + ' reports to ' + m.name AS text, p.name+'_reports_to_'+m.name AS id, 1.0 AS score, 'graph:dynamic' AS source`\n"
            "7. Do NOT include any markdown formatting, backticks, or explanation. Output ONLY the raw Cypher query string.\n"
            "8. Use `(?i)` or `toLower()` for case-insensitive matching if necessary.\n"
            "9. If the question cannot be answered by this schema, respond exactly with: NONE"
        )
        
        try:
            response = await self.client.chat.completions.create(
                model=self.model,
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": query}
                ],
                temperature=0.0
            )
            
            content = response.choices[0].message.content.strip()
            
            if content.upper() == "NONE" or not content.upper().startswith("MATCH"):
                return None
                
            # Clean up if the LLM still wrapped it in markdown
            if content.startswith("```cypher"):
                content = content[9:-3].strip()
            elif content.startswith("```"):
                content = content[3:-3].strip()
                
            return content
        except Exception as e:
            logger.exception("LLM Cypher generation failed")
            return None
