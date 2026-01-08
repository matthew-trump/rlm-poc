import docker
import json
from pathlib import Path
from typing import Optional

class REPLSession:
    """Manages a sandboxed Python REPL for document exploration"""

    def __init__(self, document_path: str):
        self.client = docker.from_env()
        self.document_path = document_path
        self.container = None
        self.init_code = """
import json
import re
from collections import Counter

# Load the document
with open('/doc.json') as f:
    doc = json.load(f)

"""
        
    def start(self):
        """Spin up isolated container with document mounted"""
        print(f"Starting REPL session with document: {self.document_path}")
        
        # Resolve absolute path
        abs_path = str(Path(self.document_path).resolve())
        
        self.container = self.client.containers.run(
            'python:3.11-slim',
            command='sleep infinity',  # Keep container alive
            detach=True,
            mem_limit='512m',
            cpu_quota=50000,  # 50% of one CPU
            network_disabled=True,  # No network access
            volumes={
                abs_path: {'bind': '/doc.json', 'mode': 'ro'}
            }
        )

        print("✓ REPL session initialized")
        
    def execute(self, code: str, timeout: int = 10) -> dict:
        """Execute code in the REPL and return output"""
        if not self.container:
            raise RuntimeError("Session not started")

        # Prepend initialization code to ensure doc is available
        full_code = self.init_code + code

        try:
            result = self.container.exec_run(
                cmd=['python', '-c', full_code],
                stdout=True,
                stderr=True,
                demux=True  # Separate stdout and stderr
            )
            
            stdout = result.output[0].decode() if result.output[0] else ""
            stderr = result.output[1].decode() if result.output[1] else ""
            
            return {
                'success': result.exit_code == 0,
                'stdout': stdout,
                'stderr': stderr,
                'exit_code': result.exit_code
            }
            
        except Exception as e:
            return {
                'success': False,
                'stdout': '',
                'stderr': str(e),
                'exit_code': -1
            }
    
    def cleanup(self):
        """Stop and remove the container"""
        if self.container:
            try:
                self.container.stop()
                self.container.remove()
                print("✓ REPL session cleaned up")
            except Exception as e:
                print(f"Warning: Cleanup error: {e}")


class SimpleRLM:
    """Simplified RLM that generates exploration code"""
    
    def __init__(self, api_key: str):
        import anthropic
        self.client = anthropic.Anthropic(api_key=api_key)
        
    def generate_exploration_code(self, query: str, conversation_history: list) -> str:
        """Generate Python code to explore the document"""
        
        # Build context from previous explorations
        history_text = "\n".join([
            f"Code: {h['code']}\nOutput: {h['output']}"
            for h in conversation_history[-3:]  # Last 3 iterations
        ])
        
        system_prompt = """You are helping explore a JSON document loaded as 'doc' in a Python REPL.

Generate concise Python code to explore the document and answer the user's query.
- The document is already loaded as 'doc'
- Available imports: json, re, Counter
- Always print() your findings
- Keep code simple and focused
- If you need to explore structure first, do that

Output ONLY executable Python code, no explanations."""

        user_message = f"""User query: {query}

Previous explorations:
{history_text if history_text else "None yet"}

Generate Python code to continue exploring:"""

        message = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=1000,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}]
        )
        
        code = message.content[0].text.strip()
        
        # Clean up markdown code blocks if present
        if code.startswith('```python'):
            code = code.split('```python')[1].split('```')[0].strip()
        elif code.startswith('```'):
            code = code.split('```')[1].split('```')[0].strip()
            
        return code
    
    def formulate_answer(self, query: str, conversation_history: list) -> str:
        """Generate final answer based on exploration results"""
        
        history_text = "\n".join([
            f"Code: {h['code']}\nOutput: {h['output']}"
            for h in conversation_history
        ])
        
        message = self.client.messages.create(
            model="claude-sonnet-4-20250514",
            max_tokens=500,
            messages=[{
                "role": "user",
                "content": f"""Based on this document exploration:

{history_text}

Original query: {query}

Provide a clear, concise answer to the user's query."""
            }]
        )
        
        return message.content[0].text.strip()